from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import strategies
from backend.app.deployments.models import Deployment
from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain import CandidateSide, ConditionNode, ConditionOperator, IntentType, SignalRule, StrategyVersion
from backend.app.strategies import StrategyService, StrategyWriteRequest
from backend.app.strategies.models import StrategyVersionStatus
from backend.app.strategies.persistence import StrategyRepository


def _payload(strategy_id, *, version_id=None, version: int = 1, name: str = "Route Strategy") -> StrategyVersion:
    rule = SignalRule(
        name="entry-rule",
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        condition=ConditionNode(
            left_feature="close",
            operator=ConditionOperator.GT,
            right_value=10.0,
        ),
    )
    return StrategyVersion(
        id=version_id or uuid4(),
        strategy_id=strategy_id,
        version=version,
        name=name,
        feature_refs=["close"],
        entry_rules=[rule],
    )


def _client(tmp_path: Path) -> tuple[TestClient, StrategyService]:
    db_path = tmp_path / "ut.db"
    service = StrategyService(
        repository=StrategyRepository(db_path),
        deployment_repository=DeploymentRepository(db_path),
    )
    app = FastAPI()
    app.include_router(strategies.router)
    app.dependency_overrides[strategies.get_strategy_service] = lambda: service
    return TestClient(app), service


def _attach_deployment(tmp_path: Path, strategy_version_id) -> None:
    DeploymentRepository(tmp_path / "ut.db").save_deployment(
        Deployment(
            name="Verification Deployment",
            strategy_version_id=strategy_version_id,
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )
    )


def test_strategy_routes_edit_draft_version_and_reject_frozen(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    strategy = service.create_strategy(StrategyWriteRequest(name="Editable"))
    version = service.add_version(strategy.strategy_id, _payload(strategy.strategy_id))
    edited_payload = _payload(
        strategy.strategy_id,
        version_id=version.strategy_version_id,
        version=99,
        name="Edited Draft",
    )

    edit_response = client.patch(
        f"/api/v1/strategies/{strategy.strategy_id}/versions/{version.strategy_version_id}",
        json=edited_payload.model_dump(mode="json"),
    )

    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["strategy_version_id"] == str(version.strategy_version_id)
    assert edited["payload"]["name"] == "Edited Draft"
    assert edited["payload"]["version"] == 1

    blocked_freeze_response = client.post(
        f"/api/v1/strategies/{strategy.strategy_id}/versions/{version.strategy_version_id}/freeze",
        headers={"X-Operator-Session-Id": "operator-session-7"},
    )
    assert blocked_freeze_response.status_code == 400
    assert blocked_freeze_response.json()["detail"] == "strategy_version can only be frozen after it is attached to a deployment"

    _attach_deployment(tmp_path, version.strategy_version_id)
    freeze_response = client.post(
        f"/api/v1/strategies/{strategy.strategy_id}/versions/{version.strategy_version_id}/freeze",
        headers={"X-Operator-Session-Id": "operator-session-7"},
    )
    assert freeze_response.status_code == 200
    frozen = freeze_response.json()
    assert frozen["status"] == StrategyVersionStatus.FROZEN.value
    assert frozen["frozen_by"] == "operator-session-7"

    rejected = client.patch(
        f"/api/v1/strategies/{strategy.strategy_id}/versions/{version.strategy_version_id}",
        json=edited_payload.model_dump(mode="json"),
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "strategy_version is frozen and cannot be edited"
