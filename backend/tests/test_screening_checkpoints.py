"""Strict serialization and real-graph tests; memory storage is a test fixture only."""
import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.agents.screening import checkpointed
from app.agents.screening.checkpoint_state import decode_state, encode_state
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.core.config import Settings, settings
from app.db.checkpointer import CheckpointerError
from app.db.workflow_threads import WorkflowThread
from test_screening_matching import (
    FakeMatcher, criterion, request, semantic_result, education_record, educational_request,
)
from test_screening_decisions import scenario


def strict_serializer():
    return JsonPlusSerializer(allowed_msgpack_modules=None, allowed_json_modules=None, pickle_fallback=False)


def thread():
    return WorkflowThread(workflow_kind="screening", instance_id=uuid4())


def semantic_request():
    return request(criteria=(criterion("Python web development"),))


@pytest.fixture
def test_saver(monkeypatch):
    saver = InMemorySaver(serde=strict_serializer())
    calls = []
    @asynccontextmanager
    async def opened(configuration=None):
        calls.append("open")
        try:
            yield saver
        finally:
            calls.append("close")
    monkeypatch.setattr(checkpointed, "open_checkpointer", opened)
    return saver, calls


def primitive(value):
    if isinstance(value, dict):
        return all(isinstance(k, str) and primitive(v) for k, v in value.items())
    if isinstance(value, list):
        return all(primitive(v) for v in value)
    return value is None or type(value) in (str, bool, int, float)


@pytest.mark.parametrize("method", ["prepare", "match", "screen"])
def test_direct_methods_reject_checkpoint_mode_before_graph_invocation(test_saver, monkeypatch, method):
    saver, lifecycle = test_saver
    matcher = FakeMatcher(error=AssertionError("Provider must not be called"))
    workflow = CandidateScreeningWorkflow(matcher, checkpointer=saver)
    async def forbidden(*args, **kwargs):
        pytest.fail("Domain input must not reach the checkpoint-enabled graph")
    monkeypatch.setattr(workflow.graph, "ainvoke", forbidden)
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(getattr(workflow, method)(semantic_request()))
    assert str(exc.value) == (
        "Direct prepare(), match() and screen() calls require non-checkpointed mode; "
        "use start_checkpointed_screening() or resume_checkpointed_screening()."
    )
    assert not matcher.calls and not lifecycle
    assert not saver.storage


@pytest.mark.parametrize("method,status", [
    ("prepare", "ready_for_matching"), ("match", "matching_complete"), ("screen", "decision_complete"),
])
def test_direct_methods_remain_compatible_without_checkpointer(method, status):
    matcher = FakeMatcher(error=AssertionError("Exact matching must not call provider"))
    result = asyncio.run(getattr(CandidateScreeningWorkflow(matcher), method)(request()))
    assert result.status == status
    assert not matcher.calls


def test_native_state_not_restored_as_domain_models_by_strict_serializer():
    supplied = request()
    state = asyncio.run(CandidateScreeningWorkflow().graph.ainvoke({"request": supplied, "operation": "screen"}))
    serde = strict_serializer()
    try:
        restored = serde.loads_typed(serde.dumps_typed(state))
    except Exception:
        return
    assert type(restored["request"]) is not type(supplied)


def test_actual_complete_state_primitive_roundtrip_and_provenance():
    state = asyncio.run(CandidateScreeningWorkflow().graph.ainvoke({"request": request(), "operation": "screen"}))
    encoded = encode_state(state)
    assert primitive(encoded)
    serde = strict_serializer()
    restored = serde.loads_typed(serde.dumps_typed(encoded))
    assert decode_state(restored) == state
    assert decode_state(restored)["result"].screening_decision == "eligible"
    assert serde.pickle_fallback is False and serde._allowed_msgpack_modules is None
    assert serde._allowed_json_modules is None


@pytest.mark.parametrize("bad", [
    {"api_key": "PRIVATE_MARKER"}, {"request": {"contact": "PRIVATE_MARKER"}},
    {"operation": "publish"}, {"matching_error": "PRIVATE_MARKER"},
    {"facts": [{"fact_id": "fact:9999", "value": "PRIVATE_MARKER"}]},
])
def test_invalid_restored_state_fails_without_payload_echo(bad):
    with pytest.raises(CheckpointerError) as exc:
        decode_state(bad)
    assert "PRIVATE_MARKER" not in str(exc.value)


def test_restore_does_not_relax_strict_domain_validation():
    encoded = encode_state({"request": request()})
    encoded["request"]["criteria"][0]["is_hard"] = "true"
    with pytest.raises(CheckpointerError, match="restored safely"):
        decode_state(encoded)


@pytest.mark.parametrize("evidence_status,outcome", [
    ("supported", "eligible"), ("not_found", "excluded"), ("ambiguous", "insufficient_evidence"),
])
def test_checkpointed_policy_outcomes_unchanged(test_saver, evidence_status, outcome):
    supplied, matcher = scenario((("requirement", evidence_status, True),))
    run = asyncio.run(checkpointed.start_checkpointed_screening(supplied, semantic_matcher=matcher))
    assert run.result.screening_decision == outcome


def test_resume_requires_explicit_thread(test_saver):
    with pytest.raises(CheckpointerError, match="valid screening workflow thread"):
        asyncio.run(checkpointed.resume_checkpointed_screening(request(), thread=None))
    assert not test_saver[1]


def test_clients_and_arbitrary_state_fields_cannot_be_encoded():
    with pytest.raises(CheckpointerError):
        encode_state({"client": object()})


def test_pause_close_reopen_resume_preserves_completed_semantic_matching(test_saver, monkeypatch):
    saver, lifecycle = test_saver
    identity = thread()
    supplied = semantic_request()
    first_matcher = FakeMatcher([semantic_result()])
    forbidden_matcher = FakeMatcher(error=AssertionError("Completed semantic operation repeated"))
    async def execute():
        paused = await checkpointed.start_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=first_matcher, pause_before_evaluation=True)
        assert paused.result is None and paused.pending_nodes == ("evaluate_hard_requirements",)
        assert lifecycle == ["open", "close"]
        workflow = CandidateScreeningWorkflow(forbidden_matcher, checkpointer=saver)
        snapshot = await workflow.graph.aget_state({"configurable": {"thread_id": identity.thread_id}})
        assert primitive(snapshot.values)
        restored = decode_state(snapshot.values)
        assert restored["matching_result"].status == "matching_complete"
        assert restored["matching_result"].matches[0].match_method == "semantic"
        assert "hard_evaluation" not in snapshot.values
        class RecoveryWorkflow(CandidateScreeningWorkflow):
            def _match_direct_evidence(self, state):
                pytest.fail("Completed deterministic matching must not repeat")
        monkeypatch.setattr(checkpointed, "CandidateScreeningWorkflow", RecoveryWorkflow)
        return await checkpointed.resume_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=forbidden_matcher)
    resumed = asyncio.run(execute())
    assert resumed.result.screening_decision == "eligible" and resumed.pending_nodes == ()
    assert len(first_matcher.calls) == 1 and not forbidden_matcher.calls
    assert lifecycle == ["open", "close", "open", "close"]


def test_default_checkpointed_start_has_no_mandatory_pause_and_allocates_thread(test_saver):
    run = asyncio.run(checkpointed.start_checkpointed_screening(request()))
    assert run.thread.workflow_kind == "screening" and run.thread.instance_id.version == 4
    assert run.result.screening_decision == "eligible" and not run.pending_nodes
    assert test_saver[1] == ["open", "close"]


def test_resume_preserves_education_associations_and_ocr_provenance(test_saver):
    supplied = educational_request((education_record("Bachelor's", "History", 1, 2),
        education_record("Master's", "Computer Science", 3, 4)))
    identity = thread()
    matcher = FakeMatcher([semantic_result(evidence=[
        {"fact_id": "fact:0001", "value": "Bachelor's"},
        {"fact_id": "fact:0004", "value": "Computer Science"},
    ])])
    forbidden = FakeMatcher(error=AssertionError("Completed matching repeated"))
    async def execute():
        await checkpointed.start_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=matcher, pause_before_evaluation=True)
        snapshot = await CandidateScreeningWorkflow(checkpointer=test_saver[0]).graph.aget_state(
            {"configurable": {"thread_id": identity.thread_id}})
        state = decode_state(snapshot.values)
        assert [fact.record_group for fact in state["facts"]] == [
            "education:01", "education:01", "education:02", "education:02"]
        return await checkpointed.resume_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=forbidden)
    run = asyncio.run(execute())
    assert run.result.screening_decision == "insufficient_evidence"
    match = run.result.matching_result.matches[0]
    assert match.match_status == "ambiguous"
    assert [item.source.number for item in match.evidence] == [1, 4]
    assert match.evidence[1].source.method == "ocr"
    assert len(matcher.calls) == 1 and not forbidden.calls


@pytest.mark.parametrize("kind", ["jd", "copilot", "evaluation"])
def test_wrong_thread_namespace_rejected_before_storage(test_saver, kind):
    with pytest.raises(CheckpointerError, match="valid screening workflow thread"):
        asyncio.run(checkpointed.start_checkpointed_screening(request(),
            thread=WorkflowThread(workflow_kind=kind, instance_id=uuid4())))
    assert test_saver[1] == []


@pytest.mark.parametrize("change", ["candidate", "job", "criteria", "qualifications"])
def test_resume_rejects_changed_snapshot(test_saver, change):
    supplied, identity = semantic_request(), thread()
    async def execute():
        await checkpointed.start_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=FakeMatcher([semantic_result()]), pause_before_evaluation=True)
        data = supplied.model_dump()
        if change == "candidate": data["upload_id"] = uuid4()
        if change == "job": data["job_reference"] = "TT-JOB-FFFFFFFFFFFFFFFF"
        if change == "criteria": data["criteria"] = (criterion("Other requirement"),)
        if change == "qualifications": data["qualifications"]["skills"][0]["value"] = "Other skill"
        changed = type(supplied).model_validate(data)
        await checkpointed.resume_checkpointed_screening(changed, thread=identity,
            semantic_matcher=FakeMatcher(error=AssertionError("Must not call")))
    with pytest.raises(CheckpointerError, match="does not match"):
        asyncio.run(execute())


@pytest.mark.parametrize("paused", [False, True])
def test_start_cannot_reuse_existing_thread(test_saver, paused):
    supplied, identity = semantic_request(), thread()
    async def execute():
        await checkpointed.start_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=FakeMatcher([semantic_result()]), pause_before_evaluation=paused)
        await checkpointed.start_checkpointed_screening(request(), thread=identity)
    with pytest.raises(CheckpointerError, match="already exists"):
        asyncio.run(execute())


@pytest.mark.parametrize("completed", [False, True])
def test_resume_requires_existing_pending_execution(test_saver, completed):
    supplied, identity = request(), thread()
    async def execute():
        if completed:
            await checkpointed.start_checkpointed_screening(supplied, thread=identity)
        await checkpointed.resume_checkpointed_screening(supplied, thread=identity)
    with pytest.raises(CheckpointerError, match="No pending"):
        asyncio.run(execute())


def test_missing_real_configuration_sanitized_and_no_fallback():
    config = Settings(_env_file=None, database_url=None, langgraph_checkpoint_database_url=None)
    with pytest.raises(CheckpointerError, match="not configured"):
        asyncio.run(checkpointed.start_checkpointed_screening(request(), configuration=config))


@pytest.mark.parametrize("failure_stage", ["open", "get", "write", "close"])
def test_storage_failures_sanitized_never_candidate_exclusion(test_saver, monkeypatch, failure_stage):
    saver = test_saver[0]
    @asynccontextmanager
    async def failed(configuration=None):
        if failure_stage == "open": raise RuntimeError("PRIVATE_CREDENTIALS_STATE")
        try:
            yield saver
        finally:
            if failure_stage == "close": raise RuntimeError("PRIVATE_CREDENTIALS_STATE")
    monkeypatch.setattr(checkpointed, "open_checkpointer", failed)
    async def fail(*args, **kwargs): raise RuntimeError("PRIVATE_CREDENTIALS_STATE")
    if failure_stage == "get": monkeypatch.setattr(saver, "aget_tuple", fail)
    if failure_stage == "write": monkeypatch.setattr(saver, "aput", fail)
    with pytest.raises(CheckpointerError) as exc:
        asyncio.run(checkpointed.start_checkpointed_screening(request()))
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.parametrize("status", ["source_unavailable", "parsing_failed"])
def test_checkpointed_source_failure_preserves_no_decision(test_saver, status):
    run = asyncio.run(checkpointed.start_checkpointed_screening(request(status=status),
        semantic_matcher=FakeMatcher(error=AssertionError("No provider"))))
    assert run.result.status == "source_unavailable" and run.result.screening_decision is None


def test_checkpointed_matching_failure_preserves_no_decision(test_saver):
    run = asyncio.run(checkpointed.start_checkpointed_screening(semantic_request(),
        semantic_matcher=FakeMatcher(error=RuntimeError("PRIVATE_PROVIDER_RESPONSE"))))
    assert run.result.status == "matching_failed" and run.result.screening_decision is None


def test_live_postgres_cross_process_screening_recovery():
    if os.environ.get("TALENTTRACE_RUN_SCREENING_CHECKPOINT_LIVE") != "1":
        pytest.skip("Live PostgreSQL screening proof requires explicit opt-in and checkpoint configuration.")
    if settings.langgraph_checkpoint_database_url is None:
        pytest.skip("Local PostgreSQL checkpoint configuration is missing.")
    identity = thread()
    helper = Path(__file__).with_name("screening_resume_worker.py")
    outputs = []
    for action in ("pause", "resume"):
        result = subprocess.run([sys.executable, str(helper), action, identity.thread_id],
            cwd=helper.parents[1], env=dict(os.environ), capture_output=True, timeout=60, text=True)
        assert result.returncode == 0, "Live PostgreSQL screening proof failed; subprocess details withheld."
        assert not result.stderr, "Unexpected subprocess diagnostics withheld."
        outputs.append(json.loads(result.stdout))
    assert outputs[0]["process_id"] != outputs[1]["process_id"]
    assert outputs[0]["semantic_calls"] == 1 and outputs[1]["semantic_calls"] == 0
    assert outputs[1]["decision"] == "eligible"
