from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass
class Canary:
    name: str
    sql: str
    expect_min: int | None = None
    expect_max: int | None = None


@dataclass
class Config:
    dump_path: str
    dump_format: str = "custom"
    docker_image: str = "postgres:16"
    db_name: str = "restorecheck"
    db_password: str = "restorecheck"
    baseline_path: str | None = None
    row_count_threshold_pct: float = 10.0
    canaries: list[Canary] = field(default_factory=list)
    slack_webhook_url: str | None = None


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    canaries = [Canary(**c) for c in raw.pop("canaries", [])]
    known_fields = {f.name for f in Config.__dataclass_fields__.values() if f.name != "canaries"}
    unknown = set(raw) - known_fields
    if unknown:
        raise ValueError(f"Unknown config field(s): {', '.join(sorted(unknown))}")

    return Config(canaries=canaries, **raw)
