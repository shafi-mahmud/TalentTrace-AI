"""Trusted internal start/resume interface; PostgreSQL only, never implicit setup."""
from dataclasses import dataclass
from uuid import uuid4

from app.agents.screening.checkpoint_state import decode_state, encode_state
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.core.config import Settings
from app.db.checkpointer import CheckpointerError, open_checkpointer
from app.db.workflow_threads import WorkflowThread
from app.integrations.llm.screening import SemanticRequirementMatcher
from app.schemas.screening import ScreeningDecisionResult, ScreeningInput


@dataclass(frozen=True)
class CheckpointedScreeningRun:
    thread: WorkflowThread
    pending_nodes: tuple[str, ...]
    result: ScreeningDecisionResult | None


def _validated_thread(thread: WorkflowThread | None) -> WorkflowThread:
    try:
        if thread is None:
            return WorkflowThread(workflow_kind="screening", instance_id=uuid4())
        validated = WorkflowThread.from_thread_id(thread.thread_id)
        if validated.workflow_kind != "screening":
            raise ValueError
        return validated
    except Exception:
        raise CheckpointerError("A valid screening workflow thread is required.") from None


async def _run(request: ScreeningInput, thread: WorkflowThread, *, resume: bool,
               configuration: Settings | None, semantic_matcher: SemanticRequirementMatcher | None,
               pause_before_evaluation: bool = False) -> CheckpointedScreeningRun:
    try:
        request = ScreeningInput.model_validate(request.model_dump(warnings=False))
        config = {"configurable": {"thread_id": thread.thread_id}}
        async with open_checkpointer(configuration) as saver:
            workflow = CandidateScreeningWorkflow(semantic_matcher, checkpointer=saver,
                interrupt_before=("evaluate_hard_requirements",) if pause_before_evaluation else ())
            snapshot = await workflow.graph.aget_state(config)
            if resume:
                if not snapshot.values or not snapshot.next:
                    raise CheckpointerError("No pending screening execution is available for this thread.")
                restored = decode_state(snapshot.values)
                if restored.get("operation") != "screen" or restored.get("request") != request:
                    raise CheckpointerError("Screening resume input does not match the stored execution.")
                initial = None  # Static graph-boundary recovery; no new input or human-approval command.
            else:
                if snapshot.created_at is not None:
                    raise CheckpointerError("Screening thread already exists; use a new identity or deliberately resume.")
                initial = encode_state({"request": request, "operation": "screen"})
            await workflow.graph.ainvoke(initial, config, durability="sync")
            final = await workflow.graph.aget_state(config)
            restored = decode_state(final.values)
            result = None if final.next else restored.get("result")
            if not final.next and not isinstance(result, ScreeningDecisionResult):
                raise CheckpointerError("Screening recovery produced no validated decision result.")
            return CheckpointedScreeningRun(thread=thread, pending_nodes=final.next, result=result)
    except CheckpointerError:
        raise
    except Exception:
        raise CheckpointerError("Screening checkpoint execution failed; check storage availability and state compatibility.") from None


async def start_checkpointed_screening(request: ScreeningInput, *, thread: WorkflowThread | None = None,
        configuration: Settings | None = None, semantic_matcher: SemanticRequirementMatcher | None = None,
        pause_before_evaluation: bool = False) -> CheckpointedScreeningRun:
    """Start with a fresh opaque thread. Pause flag is for controlled verification only."""
    return await _run(request, _validated_thread(thread), resume=False, configuration=configuration,
        semantic_matcher=semantic_matcher, pause_before_evaluation=pause_before_evaluation)


async def resume_checkpointed_screening(request: ScreeningInput, *, thread: WorkflowThread,
        configuration: Settings | None = None,
        semantic_matcher: SemanticRequirementMatcher | None = None) -> CheckpointedScreeningRun:
    """Resume pending state with the exact original request and same opaque thread."""
    if thread is None:
        raise CheckpointerError("A valid screening workflow thread is required.")
    return await _run(request, _validated_thread(thread), resume=True, configuration=configuration,
        semantic_matcher=semantic_matcher)
