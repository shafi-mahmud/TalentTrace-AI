"""JSON-safe graph boundaries, not a checkpoint serializer or storage system."""
import json
from uuid import UUID

from pydantic import BaseModel, JsonValue, TypeAdapter
from typing import Annotated, Literal, TypedDict, Union, get_args, get_origin
from types import UnionType

from app.db.checkpointer import CheckpointerError
from app.schemas.screening import (
    HardRequirementEvaluation, MatchingErrorCode, QualificationFact, RequirementContext,
    RequirementMatch, ScreeningCriterion, ScreeningDecisionResult, ScreeningInput,
    ScreeningMatchingResult, ScreeningPreparationResult, SemanticMatchingResponse,
)


TYPES = {
    "operation": Literal["prepare", "match", "screen"],
    "request": ScreeningInput,
    "requirement_context": RequirementContext,
    "source_readiness": Literal["ready", "unavailable"],
    "facts": tuple[QualificationFact, ...],
    "deterministic_results": tuple[RequirementMatch, ...],
    "unresolved_criteria": tuple[ScreeningCriterion, ...],
    "semantic_response": SemanticMatchingResponse,
    "validated_matches": tuple[RequirementMatch, ...],
    "matching_error": MatchingErrorCode,
    "matching_result": ScreeningMatchingResult,
    "hard_evaluation": HardRequirementEvaluation,
}
ADAPTERS = {key: TypeAdapter(schema) for key, schema in TYPES.items()}
PrimitiveScreeningWorkflowState = TypedDict("PrimitiveScreeningWorkflowState",
    {key: JsonValue for key in (*TYPES, "result")}, total=False)

# Existing strict models use a wildcard before-validator, so JSON array -> tuple
# conversion must occur explicitly before Python validation (strict=False is not used).
def _domain_values(value, schema):
    origin, args = get_origin(schema), get_args(schema)
    if origin is Annotated:
        return _domain_values(value, args[0])
    if origin in (Union, UnionType):
        choices = [choice for choice in args if choice is not type(None)]
        if value is not None and len(choices) == 1:
            return _domain_values(value, choices[0])
        return value
    if isinstance(schema, type) and issubclass(schema, BaseModel) and isinstance(value, dict):
        fields = schema.model_fields
        return schema.model_validate({key: _domain_values(item, fields[key].annotation)
            if key in fields else item for key, item in value.items()}, strict=True)
    if origin in (tuple, list) and isinstance(value, list):
        items = [_domain_values(item, args[0]) for item in value]
        return tuple(items) if origin is tuple else items
    if schema is UUID and isinstance(value, str):
        identity = UUID(value)
        if str(identity) != value:
            raise ValueError("Invalid stored identifier.")
        return identity
    return value


def _result_type(value):
    if "matching_result" in value:
        return ScreeningDecisionResult
    if "matches" in value:
        return ScreeningMatchingResult
    return ScreeningPreparationResult


def encode_state(state: dict) -> dict:
    """Only explicitly registered fields and JSON primitives reach the saver."""
    try:
        encoded = {}
        for key, value in state.items():
            if key == "result":
                value = value.model_dump(mode="json", warnings=False)
                schema = _result_type(value)
                adapter = TypeAdapter(schema)
            else:
                adapter = ADAPTERS[key]
                schema = TYPES[key]
                value = adapter.dump_python(value, mode="json", warnings=False)
            json.dumps(value, allow_nan=False)
            adapter.validate_python(_domain_values(value, schema), strict=True)
            encoded[key] = value
        return encoded
    except Exception:
        raise CheckpointerError("Screening checkpoint state could not be encoded safely.") from None


def decode_state(state: dict) -> dict:
    """Reconstruct validated domain models without module-based deserialization."""
    try:
        state = json.loads(json.dumps(state, allow_nan=False))
        decoded = {}
        for key, value in state.items():
            schema = _result_type(value) if key == "result" else TYPES[key]
            decoded[key] = TypeAdapter(schema).validate_python(_domain_values(value, schema), strict=True)
        return decoded
    except Exception:
        raise CheckpointerError("Screening checkpoint state could not be restored safely.") from None
