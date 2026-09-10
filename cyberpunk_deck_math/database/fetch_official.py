"""Ingestion from the official Cyberpunk TCG card database.

Design notes
------------
The official site (https://cyberpunktcg.com/cards) is the authoritative source.
Its JSON endpoint is *configured*, not guessed: pass ``--source-url``, set
``CYBERPUNK_TCG_CARDS_URL``, or hand the command a JSON file you exported from
the site with ``--source-file``.  The candidate endpoints below are tried in
order and are only a convenience; if none respond, the command fails loudly
with instructions instead of fabricating card data.

Whatever the source, the pipeline is the same:

1. fetch  ->  2. restrict to released Beta + Beta starter exclusives  ->
3. normalize  ->  4. write the local cache.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ..config import DEFAULT_CARD_CACHE
from .cache import CardDatabase
from .normalize import normalize_records, unwrap_payload
from .validate_pool import PoolFilterResult, filter_pool

OFFICIAL_SITE = "https://cyberpunktcg.com/cards"

#: Tried in order when no explicit source is configured.
CANDIDATE_ENDPOINTS: tuple[str, ...] = (
    "https://cyberpunktcg.com/api/cards",
    "https://cyberpunktcg.com/api/v1/cards",
    "https://cyberpunktcg.com/cards.json",
)

USER_AGENT = "cyberpunk-deck-math/1.0 (+local deck analysis tool)"
ENV_URL = "CYBERPUNK_TCG_CARDS_URL"


class FetchError(RuntimeError):
    """Raised when no card data could be retrieved."""


@dataclass
class FetchReport:
    source: str = ""
    raw_records: int = 0
    normalized: int = 0
    kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    updated_at: str = ""
    cache_path: Optional[Path] = None
    carried_interpretations: int = 0

    def render(self) -> str:
        lines = [
            f"Source:            {self.source}",
            f"Raw records:       {self.raw_records}",
            f"Normalized:        {self.normalized}",
            f"Kept (Beta pool):  {self.kept}",
        ]
        for reason, count in sorted(self.dropped.items()):
            lines.append(f"  dropped {count:>4}  {reason}")
        if self.carried_interpretations:
            lines.append(
                f"Carried over {self.carried_interpretations} human-verified interpretations"
            )
        for warning in self.warnings[:20]:
            lines.append(f"  warning: {warning}")
        if len(self.warnings) > 20:
            lines.append(f"  ... {len(self.warnings) - 20} more warnings")
        if self.cache_path:
            lines.append(f"Cache written:     {self.cache_path}")
        return "\n".join(lines)


def _http_get(url: str, timeout: float = 30.0) -> Any:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def fetch_payload(
    source_url: Optional[str] = None,
    source_file: Optional[str | Path] = None,
    timeout: float = 30.0,
) -> tuple[Any, str]:
    """Return ``(payload, source description)``.

    Order of preference: explicit file, explicit URL, ``$CYBERPUNK_TCG_CARDS_URL``,
    then the candidate endpoints.
    """
    if source_file:
        path = Path(source_file)
        return json.loads(path.read_text(encoding="utf-8")), f"file://{path}"

    urls: list[str] = []
    if source_url:
        urls.append(source_url)
    elif os.environ.get(ENV_URL):
        urls.append(os.environ[ENV_URL])
    else:
        urls.extend(CANDIDATE_ENDPOINTS)

    failures: list[str] = []
    for url in urls:
        try:
            return _http_get(url, timeout=timeout), url
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as exc:
            failures.append(f"{url}: {exc}")
    raise FetchError(
        "could not retrieve the official card database.\n"
        + "\n".join(f"  - {f}" for f in failures)
        + f"\n\nFix one of the following and re-run:\n"
        f"  * pass --source-url <json endpoint> (find it on {OFFICIAL_SITE})\n"
        f"  * export {ENV_URL}=<json endpoint>\n"
        "  * export the card list from the official site and pass --source-file <path>"
    )


def update_cards(
    cache_path: str | Path = DEFAULT_CARD_CACHE,
    source_url: Optional[str] = None,
    source_file: Optional[str | Path] = None,
    json_path: Optional[str] = None,
    set_codes: Optional[Sequence[str]] = None,
    keep_all: bool = False,
    timeout: float = 30.0,
) -> tuple[CardDatabase, FetchReport]:
    """Fetch, restrict, normalize and cache the Beta card pool."""
    payload, source = fetch_payload(source_url, source_file, timeout)
    if json_path:
        for part in json_path.split("."):
            payload = payload[part]
    records: list[Mapping[str, Any]] = unwrap_payload(payload)
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cards, warnings = normalize_records(
        records, source_url=source, updated_at=updated_at, provenance="official"
    )
    if keep_all:
        filtered = PoolFilterResult(kept=cards)
    else:
        extra = list(set_codes or [])
        filtered = filter_pool(cards, extra_set_codes=extra)

    database = CardDatabase(
        cards=filtered.kept,
        source_url=source,
        updated_at=updated_at,
        data_provenance="official",
        notes=[
            f"Ingested from {source}",
            "Restricted to released Beta cards and Beta starter exclusives"
            if not keep_all
            else "Pool filtering disabled (--keep-all)",
        ],
    )

    report = FetchReport(
        source=source,
        raw_records=len(records),
        normalized=len(cards),
        kept=len(filtered.kept),
        dropped=filtered.dropped_reasons(),
        warnings=warnings,
        updated_at=updated_at,
    )

    cache = Path(cache_path)
    if cache.exists():
        try:
            report.carried_interpretations = database.merge_interpretations(
                CardDatabase.load(cache)
            )
        except (ValueError, KeyError) as exc:
            report.warnings.append(f"could not merge previous interpretations: {exc}")
    report.cache_path = database.save(cache)
    return database, report
