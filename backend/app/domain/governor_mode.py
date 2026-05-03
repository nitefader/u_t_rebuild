from __future__ import annotations

from enum import StrEnum


class GovernorMode(StrEnum):
    OFF = "off"
    ADVISORY = "advisory"
    ENFORCED = "enforced"
