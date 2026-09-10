"""Export analyses to JSON, CSV and Markdown.

Every export carries the assumptions that produced it: rule overrides,
sellable targets, profiles, iteration count and seed.  A number without its
assumptions is not reproducible, so the exporters refuse to drop them.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .config import AnalysisConfig
from .database.cache import CardDatabase
from .methods import Result
from .models import Deck


def analysis_metadata(
    deck: Deck,
    config: AnalysisConfig,
    database: Optional[CardDatabase] = None,
    mulligan_profile: str = "",
    playability_profile: str = "",
) -> dict[str, Any]:
    return {
        "deck_name": deck.name,
        "analysis_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "card_database_version": getattr(database, "version", None),
        "card_database_update_date": getattr(database, "updated_at", None),
        "card_database_source": getattr(database, "source_url", None),
        "card_data_provenance": getattr(database, "data_provenance", None),
        "minimum_sellable_pct": config.sellable.minimum_pct,
        "target_sellable_pct": config.sellable.target_pct,
        "target_sellable_range": list(config.sellable.target_range),
        "sellable_targets_method": config.sellable.method.value,
        "mulligan_profile": mulligan_profile,
        "playability_profile": playability_profile,
        "simulation_iterations": config.simulation_iterations,
        "simulation_seed": config.simulation_seed,
        "rule_overrides": config.rules.overrides(),
        "rules": config.rules.to_dict(),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, Result):
        return value.to_dict()
    if is_dataclass(value) and not isinstance(value, type):
        if hasattr(value, "to_dict"):
            return _plain(value.to_dict())
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def to_json(payload: Mapping[str, Any], path: Optional[str | Path] = None) -> str:
    text = json.dumps(_plain(payload), indent=2, ensure_ascii=False)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text


def flatten(payload: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in _plain(payload).items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            rows.extend(flatten(value, f"{name}."))
        elif isinstance(value, list) and value and isinstance(value[0], Mapping):
            for index, item in enumerate(value):
                rows.extend(flatten(item, f"{name}[{index}]."))
        else:
            rows.append((name, value))
    return rows


def to_csv(payload: Mapping[str, Any], path: Optional[str | Path] = None) -> str:
    rows = flatten(payload)
    lines = ["key,value"]
    for key, value in rows:
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        lines.append(f'"{key}","{text}"')
    output = "\n".join(lines)
    if path:
        Path(path).write_text(output, encoding="utf-8")
    return output


def to_markdown(
    payload: Mapping[str, Any],
    title: str = "Cyberpunk TCG deck analysis",
    path: Optional[str | Path] = None,
) -> str:
    def render(value: Any, depth: int = 2) -> list[str]:
        lines: list[str] = []
        if isinstance(value, Mapping):
            for key, inner in value.items():
                if isinstance(inner, (Mapping, list)):
                    lines.append(f"{'#' * min(depth, 6)} {key}")
                    lines.extend(render(inner, depth + 1))
                else:
                    lines.append(f"- **{key}**: {_format_scalar(inner)}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (Mapping, list)):
                    lines.extend(render(item, depth + 1))
                else:
                    lines.append(f"- {_format_scalar(item)}")
        else:
            lines.append(str(value))
        return lines

    body = [f"# {title}", ""] + render(_plain(payload))
    text = "\n".join(body) + "\n"
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text


def _format_scalar(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def export_all(payload: Mapping[str, Any], stem: str | Path) -> dict[str, Path]:
    """Write ``stem.json``, ``stem.csv`` and ``stem.md``."""
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": stem.with_suffix(".json"),
        "csv": stem.with_suffix(".csv"),
        "markdown": stem.with_suffix(".md"),
    }
    to_json(payload, paths["json"])
    to_csv(payload, paths["csv"])
    to_markdown(payload, path=paths["markdown"])
    return paths
