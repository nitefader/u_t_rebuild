"""Pre-runtime Program promotion validation.

PromotionGateService is the account-scoped required precondition service for
any future BROKER_LIVE deployment creation flow. It evaluates supplied evidence
only; it does not create, start, or mutate deployments.
"""

from .models import (
    PaperRunEvidence,
    PortfolioGovernorReadiness,
    PromotionEvaluationContext,
    PromotionResult,
    SimulationPromotionEvidence,
)
from .service import PromotionGateService

__all__ = [
    "PaperRunEvidence",
    "PortfolioGovernorReadiness",
    "PromotionEvaluationContext",
    "PromotionGateService",
    "PromotionResult",
    "SimulationPromotionEvidence",
]
