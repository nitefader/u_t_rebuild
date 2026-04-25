from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path

from .service import ServicesCenterService


def create_services_center_service_from_environment() -> ServicesCenterService:
    db_path = get_runtime_db_path()
    return ServicesCenterService(store_path=db_path.with_name("services_catalog.json"))
