"""Opt-in real PostgreSQL, cross-process proof using the actual Screening graph."""
import asyncio
import json
import logging
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.screening import checkpointed
from app.agents.screening.checkpoint_state import decode_state
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.db.checkpointer import open_checkpointer
from app.db.workflow_threads import WorkflowThread
from app.schemas.candidate_profile import CandidateQualifications, CandidateWorkHistory, GroundedAttribute, SourceReference
from app.schemas.screening import ScreeningInput, ScreeningCriterion, SemanticMatchingResponse


def synthetic_input():
    return ScreeningInput(job_reference="TT-JOB-0123456789ABCDEF",
        upload_id=UUID("edb5a89e-a6f2-4d20-aa60-635c138a5b30"), parsing_status="parsed",
        qualifications=CandidateQualifications(education=[], skills=[], work_history=[CandidateWorkHistory(
            employer=None, role_title=None, date_or_period=None, location=None,
            responsibilities_or_achievements=[GroundedAttribute(value="Built REST APIs using Django",
                source=SourceReference(kind="page", number=1, method="ocr"))])]),
        criteria=(ScreeningCriterion(criterion_id="python-web", category="skill",
            description="Python web development", is_hard=True),))


async def verify(action, thread_id):
    identity = WorkflowThread.from_thread_id(thread_id)
    supplied = synthetic_input()
    semantic_calls, direct_calls = [], []
    class ProofMatcher:
        async def match(self, criteria, facts):
            semantic_calls.append(True)
            if action == "resume":
                raise AssertionError("Completed semantic matching was repeated")
            return SemanticMatchingResponse.model_validate_json(json.dumps({"results": [{
                "criterion_id": "python-web", "match_status": "supported", "evidence": [{
                    "fact_id": facts[0].fact_id, "value": facts[0].value}]}]}))
    class ProofWorkflow(CandidateScreeningWorkflow):
        def _match_direct_evidence(self, state):
            direct_calls.append(True)
            if action == "resume":
                raise AssertionError("Completed direct matching was repeated")
            return super()._match_direct_evidence(state)
    checkpointed.CandidateScreeningWorkflow = ProofWorkflow
    if action == "pause":
        run = await checkpointed.start_checkpointed_screening(supplied, thread=identity,
            semantic_matcher=ProofMatcher(), pause_before_evaluation=True)
        assert run.result is None and run.pending_nodes == ("evaluate_hard_requirements",)
        assert len(semantic_calls) == 1 and len(direct_calls) == 1
        # The start context has closed. Read actual committed PostgreSQL state through another connection.
        async with open_checkpointer() as saver:
            config = {"configurable": {"thread_id": identity.thread_id}}
            saved = await saver.aget_tuple(config)
            assert saved is not None
            # Graph snapshots omit LangGraph's internal routing channels.
            snapshot = await CandidateScreeningWorkflow(checkpointer=saver).graph.aget_state(config)
            assert snapshot.next == ("evaluate_hard_requirements",)
            state = decode_state(snapshot.values)
            assert state["matching_result"].status == "matching_complete"
            assert state["matching_result"].matches[0].match_method == "semantic"
            assert "hard_evaluation" not in state
        return {"status": "paused", "semantic_calls": 1, "direct_calls": 1}
    if action == "resume":
        run = await checkpointed.resume_checkpointed_screening(supplied, thread=identity, semantic_matcher=ProofMatcher())
        assert not run.pending_nodes and run.result.screening_decision == "eligible"
        assert not semantic_calls and not direct_calls
        assert run.result.matching_result.matches[0].evidence[0].source.method == "ocr"
        return {"status": "resumed", "semantic_calls": 0, "direct_calls": 0, "decision": "eligible"}
    raise ValueError("Unknown proof action")


def main():
    logging.disable(logging.CRITICAL)
    try:
        if len(sys.argv) != 3:
            raise ValueError("Invalid proof arguments")
        with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
            result = asyncio.run(verify(sys.argv[1], sys.argv[2]),
                loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    except Exception:
        print("Screening PostgreSQL recovery proof failed; details withheld.")
        return 1
    print(json.dumps({**result, "process_id": os.getpid()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
