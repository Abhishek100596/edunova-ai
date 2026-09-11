"""Evidence source helpers — never invent URLs; official requires official types."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.research import EVIDENCE_SOURCE_TYPES, EvidenceSource

OFFICIAL_SOURCE_TYPES = frozenset(
    {"official_careers", "gov", "onet", "bls", "docs"}
)


def is_official_source_type(source_type: str | None) -> bool:
    return (source_type or "").strip().lower() in OFFICIAL_SOURCE_TYPES


def validate_official_flag(
    *, is_official: bool, source_type: str | None, url: str | None
) -> tuple[bool, list[str]]:
    """
    Return (adjusted_is_official, warnings).

    Official may only be True when source_type is in the official set and a
    non-empty real URL is provided. Never invent or fabricate URLs.
    """
    warnings: list[str] = []
    st = (source_type or "").strip().lower()
    url_s = (url or "").strip()

    if is_official:
        if st not in OFFICIAL_SOURCE_TYPES:
            warnings.append(
                f"is_official requires source_type in {sorted(OFFICIAL_SOURCE_TYPES)}; "
                f"got {st!r} — marking unofficial."
            )
            is_official = False
        if not url_s:
            warnings.append(
                "is_official requires a real URL; empty URL — marking unofficial."
            )
            is_official = False
        elif not (
            url_s.startswith("https://") or url_s.startswith("http://")
        ):
            warnings.append(
                "is_official requires an http(s) URL — marking unofficial."
            )
            is_official = False
    return is_official, warnings


def serialize_evidence(source: EvidenceSource | None) -> dict[str, Any] | None:
    if source is None:
        return None
    accessed = source.accessed_at
    verified = source.last_verified_at
    return {
        "id": source.id,
        "title": source.title,
        "url": source.url,
        "source_type": source.source_type,
        "publisher": source.publisher,
        "is_official": bool(source.is_official),
        "published_date": source.published_date,
        "accessed_at": accessed.isoformat() if isinstance(accessed, datetime) else None,
        "jurisdiction": source.jurisdiction,
        "role_category": source.role_category,
        "excerpt": source.excerpt,
        "verification_status": source.verification_status,
        "confidence": float(source.confidence or 0.0),
        "last_verified_at": (
            verified.isoformat() if isinstance(verified, datetime) else None
        ),
        "source_priority": int(source.source_priority or 0),
        "notes": source.notes,
    }


def evidence_dict_from_fields(
    *,
    title: str,
    url: str | None = None,
    source_type: str = "other",
    publisher: str | None = None,
    is_official: bool = False,
    published_date: str | None = None,
    jurisdiction: str | None = None,
    role_category: str | None = None,
    excerpt: str | None = None,
    verification_status: str = "unverified",
    confidence: float = 0.0,
    source_priority: int = 50,
    notes: str | None = None,
    last_verified_at: str | None = None,
) -> dict[str, Any]:
    """Build a serializable evidence dict without inventing URLs."""
    st = (source_type or "other").strip().lower()
    if st not in EVIDENCE_SOURCE_TYPES:
        st = "other"
    official, warnings = validate_official_flag(
        is_official=is_official, source_type=st, url=url
    )
    url_out = (url or "").strip() or None
    conf = max(0.0, min(1.0, float(confidence)))
    return {
        "title": title,
        "url": url_out,
        "source_type": st,
        "publisher": publisher,
        "is_official": official,
        "published_date": published_date,
        "jurisdiction": jurisdiction,
        "role_category": role_category,
        "excerpt": excerpt,
        "verification_status": verification_status,
        "confidence": conf,
        "source_priority": int(source_priority),
        "notes": notes,
        "last_verified_at": last_verified_at,
        "validation_warnings": warnings,
    }
