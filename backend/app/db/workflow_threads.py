"""Known workflow namespaces with opaque identity; no workflow implementation."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkflowThread(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    workflow_kind: Literal["jd", "screening", "copilot", "evaluation"]
    instance_id: UUID

    @property
    def thread_id(self) -> str:
        return f"{self.workflow_kind}:{self.instance_id}"

    @classmethod
    def from_thread_id(cls, value: str) -> "WorkflowThread":
        try:
            if not isinstance(value, str) or len(value) > 47:
                raise ValueError
            kind, identity = value.split(":")
            result = cls(workflow_kind=kind, instance_id=identity)
            if result.thread_id != value:
                raise ValueError
            return result
        except (ValueError, TypeError):
            raise ValueError("A valid opaque workflow thread identifier is required.") from None
