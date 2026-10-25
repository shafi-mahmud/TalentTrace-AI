"""Request-scoped CV provider routing. Both extraction and matching share one choice."""
from fastapi import HTTPException
from pydantic import SecretStr
from app.integrations.llm.selection import MODELS, OllamaClient, installed_models
from app.integrations.llm.candidate_profile import GroqCandidateProfileExtractor
from app.integrations.llm.screening import GroqSemanticRequirementMatcher
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.services.candidate_profile import CandidateProfileService
from app.services.batch_screening import BatchScreeningService


async def selected_screening(request, configuration):
    provider = request.headers.get("x-talenttrace-ai-provider", "")
    if provider == "groq":
        if request.headers.get("x-talenttrace-external-processing") != "confirmed":
            raise HTTPException(422, "Confirm sending CV text and derived qualifications to Groq first.")
        if not configuration.groq_api_key or not configuration.groq_api_key.get_secret_value().strip():
            raise HTTPException(503, "Selected CV provider unavailable.")
        config, factory = configuration, None
        model = configuration.llm_model
    else:
        model = provider.removeprefix("ollama:")
        if provider != "ollama:" + model or model not in MODELS:
            raise HTTPException(422, "Select an available CV AI provider.")
        if not configuration.ollama_enabled or model not in await installed_models():
            raise HTTPException(503, "Selected local CV model unavailable.")
        # The fixed loopback transport never uses or transmits this compatibility sentinel.
        config = configuration.model_copy(update={"groq_api_key": SecretStr("local-only-no-api-key")})
        factory = lambda **kwargs: OllamaClient(model, **kwargs)
    options = {"client_factory": factory} if factory else {}
    profiles = CandidateProfileService(config, extractor=GroqCandidateProfileExtractor(config, **options))
    workflow = CandidateScreeningWorkflow(GroqSemanticRequirementMatcher(config, **options))
    service = BatchScreeningService(profiles=profiles, workflow=workflow)
    service.ai_provenance = {"provider": "groq" if provider == "groq" else "ollama", "model": model,
        "external_processing_confirmed": provider == "groq"}
    return service
