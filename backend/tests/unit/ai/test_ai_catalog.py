from __future__ import annotations

import pytest

from backend.app.ai import (
    AICapabilityLabel,
    AIProvider,
    AIProviderCatalog,
    AIProviderCatalogError,
    AIProviderStatus,
    AIServiceWrite,
    AIValidationStatus,
)
from backend.app.ai.validation import AIValidationResult


class FakeAIValidator:
    def validate(self, **kwargs):
        if not kwargs["has_api_key"]:
            return AIValidationResult(AIValidationStatus.MISSING_CREDENTIALS, "missing")
        return AIValidationResult(AIValidationStatus.VALID, "ok")


def test_ai_crud_validation_default_and_disable(tmp_path) -> None:
    catalog = AIProviderCatalog(store_path=tmp_path / "ai_catalog.json", validator=FakeAIValidator())
    groq = catalog.create_service(
        AIServiceWrite(name="Groq Fast", provider=AIProvider.GROQ, api_key="gsk_valid_key", capability_label=AICapabilityLabel.FAST)
    )
    assert catalog.list_services().services == (groq,)
    edited = catalog.update_service(
        groq.id,
        AIServiceWrite(name="Groq Reasoning", provider=AIProvider.GROQ, capability_label=AICapabilityLabel.REASONING),
    )
    assert edited.capability_label == AICapabilityLabel.REASONING
    validated = catalog.validate_service(groq.id)
    assert validated.status == AIProviderStatus.VALID
    assert catalog.set_default(groq.id).is_default is True
    assert catalog.disable_service(groq.id).status == AIProviderStatus.DISABLED
    with pytest.raises(AIProviderCatalogError):
        catalog.set_default(groq.id)


def test_ai_missing_key_and_invalid_default(tmp_path) -> None:
    catalog = AIProviderCatalog(store_path=tmp_path / "ai_catalog.json", validator=FakeAIValidator())
    groq = catalog.create_service(AIServiceWrite(name="Groq", provider=AIProvider.GROQ))
    assert catalog.validate_service(groq.id).validation_status == AIValidationStatus.MISSING_CREDENTIALS
    with pytest.raises(AIProviderCatalogError, match="invalid service"):
        catalog.set_default(groq.id)
