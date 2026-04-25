from __future__ import annotations

from dataclasses import dataclass

from .providers import AIProvider, AIValidationStatus


@dataclass(frozen=True)
class AIValidationResult:
    status: AIValidationStatus
    message: str


class AIProviderValidator:
    def validate(self, *, provider: AIProvider, has_api_key: bool, api_key: str | None = None) -> AIValidationResult:
        if not has_api_key:
            return AIValidationResult(AIValidationStatus.MISSING_CREDENTIALS, f"{provider.value} API key is required.")
        if provider == AIProvider.GROQ and api_key is not None and not api_key.startswith("gsk_"):
            return AIValidationResult(AIValidationStatus.INVALID, "Groq API key shape is invalid.")
        if provider not in {AIProvider.GROQ, AIProvider.CLAUDE, AIProvider.OPENAI, AIProvider.CODEX, AIProvider.FUTURE}:
            return AIValidationResult(AIValidationStatus.UNSUPPORTED_PROVIDER, "Unsupported AI provider.")
        return AIValidationResult(AIValidationStatus.VALID, f"{provider.value} credentials validated by configured validator.")
