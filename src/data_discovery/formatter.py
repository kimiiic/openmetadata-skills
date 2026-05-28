from __future__ import annotations

import json
import re
from typing import Any


TIER_SOURCE_OF_TRUTH = {
    "Tier.Tier1": {
        "rank": 50,
        "label": "Tier 1",
        "summary": "Critical source-of-truth business data assets.",
    },
    "Tier.Tier2": {
        "rank": 40,
        "label": "Tier 2",
        "summary": "Important business datasets, but not as critical as Tier 1.",
    },
    "Tier.Tier3": {
        "rank": 30,
        "label": "Tier 3",
        "summary": "Department or group-level datasets.",
    },
    "Tier.Tier4": {
        "rank": 20,
        "label": "Tier 4",
        "summary": "Team-level, typically non-business or internal system datasets.",
    },
    "Tier.Tier5": {
        "rank": 10,
        "label": "Tier 5",
        "summary": "Private or unused assets with no impact beyond individual users.",
    },
}

ENTITY_TYPE_PROMPT_OPTIONS = [
    ("📊", "table", "Tables / datasets"),
    ("📈", "dashboard", "Dashboards / reports"),
    ("🔄", "pipeline", "Pipelines / jobs"),
    ("📡", "topic", "Topics / streams"),
    ("🎯", "metric", "Metrics / KPIs"),
    ("📚", "glossaryTerm", "Glossary terms"),
    ("🏷️", "tag", "Tags / classifications"),
    ("🤖", "mlmodel", "ML models"),
    ("🗄️", "container", "Storage containers"),
    ("📦", "dataProduct", "Data products"),
]


def format_entity_type_prompt(question: str, cleaned_query: str) -> str:
    lines = [
        f'I need the OpenMetadata entity type before searching for "{cleaned_query or question}".',
        "",
        "Which entity type do you want to search?",
        "",
    ]
    for emoji, entity_type, label in ENTITY_TYPE_PROMPT_OPTIONS:
        lines.append(f"- {emoji} `{entity_type}` - {label}")
    lines.extend(
        [
            "",
            "Run again with `--entity-type`, for example:",
            f'`uv run disover-data --entity-type table --question "{cleaned_query or question}"`',
        ]
    )
    return "\n".join(lines)


def normalize_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = _extract_results(response)
    normalized = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "entityType": _first_present(item, "entityType", "entity_type", default=""),
                "fullyQualifiedName": _first_present(item, "fullyQualifiedName", "fqn", default=""),
                "name": _first_present(item, "name", default=""),
                "displayName": _first_present(item, "displayName", "display_name", default=""),
                "description": _first_present(item, "description", default=""),
                "owners": _as_list(_first_present(item, "owners", "owner", default=[])),
                "tags": _as_list(_first_present(item, "tags", default=[])),
                "tier": _normalize_tier(_first_present(item, "tier", default=None)),
                "domains": _as_list(_first_present(item, "domains", "domain", default=[])),
                "dataProducts": _as_list(_first_present(item, "dataProducts", "data_products", default=[])),
                "href": _first_present(item, "href", default=""),
                "similarityScore": _first_present(item, "similarityScore", "score", "_score", default=None),
                "raw": item,
            }
        )
    return normalized


def merge_details(results: list[dict[str, Any]], details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = []
    detail_by_fqn = {
        _first_present(detail, "fullyQualifiedName", "fqn", default=""): detail
        for detail in details
        if isinstance(detail, dict)
    }
    for result in results:
        detail = detail_by_fqn.get(result.get("fullyQualifiedName", "")) or {}
        combined = dict(result)
        for key in ("description", "owners", "tags", "tier", "domains", "dataProducts", "href", "displayName", "name"):
            if not _is_empty(detail.get(key)):
                combined[key] = detail[key]
        combined["details"] = detail
        merged.append(combined)
    return merged


def rank_results(results: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
    return sorted(results, key=lambda r: _ranking_score(r, query), reverse=True)


def format_answer(
    question: str,
    cleaned_query: str,
    results: list[dict[str, Any]],
    notes: list[str] | None = None,
) -> str:
    notes = notes or []
    if not results:
        note_text = "\n".join(notes)
        if note_text:
            note_text += "\n\n"
        return (
            f"{note_text}I could not find matching metadata assets for this question.\n\n"
            "Try refining the query with:\n"
            "- a business domain\n"
            "- a glossary term\n"
            "- a table or dashboard name\n"
            "- an owner\n"
            "- a known column name\n"
            "- a system or service name"
        )

    ssot_results = [r for r in results if r.get("_ssot_source")]
    direct_results = [r for r in results if not r.get("_ssot_source")]

    lines = []
    if notes:
        lines.extend(notes)
        lines.append("")

    if ssot_results:
        lines.append("SSOT tables referenced by matching glossary terms:")
        lines.append("")
        lines.extend(_format_ssot_table(ssot_results))
        lines.append("")

    lines.append(f'Found {len(direct_results)} matching metadata assets for:')
    lines.append(f'"{cleaned_query or question}"')
    lines.append("")
    lines.extend(_format_results_table(direct_results))

    # If we're showing table results without SSOT links, suggest glossary lookup
    if direct_results and not ssot_results:
        entity = direct_results[0].get("entityType", "")
        if entity == "table":
            lines.append("")
            lines.append(
                f'Tip: "{cleaned_query or question}" may also be a glossary term with a linked '
                "source-of-truth table. Try searching glossary terms to find SSOT references."
            )

    return "\n".join(lines)


def to_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _extract_results(response: dict[str, Any]) -> list[Any]:
    for key in ("results", "hits", "data"):
        value = response.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_results(value)
            if nested:
                return nested
    return []


def _ranking_score(result: dict[str, Any], query: str = "") -> float:
    score = 0.0
    similarity = result.get("similarityScore")
    if isinstance(similarity, (int, float)):
        score += float(similarity) * 100
    elif query:
        score += _text_match_boost(result, query)
    # SSOT tables are explicitly linked from glossary terms — boost them
    if result.get("_ssot_source"):
        score += 65
    tier = _extract_tier_from_result(result)
    score += TIER_SOURCE_OF_TRUTH.get(tier or "", {}).get("rank", 0)
    if result.get("owners"):
        score += 8
    if result.get("description"):
        score += 6
    if result.get("tags"):
        score += 5
    if result.get("domains"):
        score += 3
    if result.get("href"):
        score += 2
    return score


def _text_match_boost(result: dict[str, Any], query: str) -> float:
    """Score by text match when similarityScore is unavailable (queryFilter path).

    The API orders by _score internally but doesn't expose it in the response.
    This mirrors the API's multi_match boosts so client-side ranking with tier,
    owner, and domain signals can further refine the order.
    """
    q = query.lower().strip()
    if not q:
        return 0.0
    boost = 0.0
    # FQN match — strongest signal
    fqn = (result.get("fullyQualifiedName") or "").lower()
    if q in fqn:
        boost += 60
    # Name / display name match
    name = (result.get("name") or "").lower()
    display = (result.get("displayName") or "").lower()
    if q in name:
        boost += 50
    elif q in display:
        boost += 50
    # Data product name match
    for dp in _as_list(result.get("dataProducts")):
        dp_name = ""
        if isinstance(dp, dict):
            dp_name = (dp.get("name") or dp.get("displayName") or "").lower()
        if dp_name and q in dp_name:
            boost += 45
            break
    # Description match — weaker signal
    desc = (result.get("description") or "").lower()
    if q in desc:
        boost += 25
    return boost


def _first_present(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_tier(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        value = value.get("tagFQN") or value.get("name") or value.get("displayName")
    text = str(value)
    match = re.search(r"Tier\.?Tier?(\d)|Tier\s*(\d)", text, flags=re.IGNORECASE)
    if match:
        return f"Tier.Tier{match.group(1) or match.group(2)}"
    return None


def _extract_tier_from_result(result: dict[str, Any]) -> str | None:
    direct = _normalize_tier(result.get("tier"))
    if direct:
        return direct
    for tag in _as_list(result.get("tags")):
        tier = _normalize_tier(tag)
        if tier:
            return tier
    return None


def _format_tier(result: dict[str, Any]) -> str:
    tier = _extract_tier_from_result(result)
    if not tier:
        return ""
    label = TIER_SOURCE_OF_TRUTH.get(tier, {}).get("label")
    return f"{tier} - {label}" if label else tier


def _format_people(values: Any) -> str:
    items = _as_list(values)
    labels = []
    for item in items:
        if isinstance(item, dict):
            labels.append(str(item.get("displayName") or item.get("name") or item.get("fullyQualifiedName") or item))
        else:
            labels.append(str(item))
    return ", ".join(label for label in labels if label)


def _format_tags(values: Any) -> str:
    items = _as_list(values)
    labels = []
    for item in items:
        if isinstance(item, dict):
            labels.append(str(item.get("tagFQN") or item.get("name") or item.get("displayName") or item))
        else:
            labels.append(str(item))
    visible = [label for label in labels if label]
    if len(visible) > 8:
        return ", ".join(visible[:8]) + f", ... (+{len(visible) - 8} more)"
    return ", ".join(visible)


def _format_results_table(results: list[dict[str, Any]], extra_fields: set[str] | None = None) -> list[str]:
    # Always show these columns
    base_cols = ["Table FQN", "Owner", "Domain", "Tier"]
    base_keys = ["fullyQualifiedName", "owners", "domains", "_tier"]

    # Auto-detect extra fields present in results (if not explicitly provided)
    if extra_fields is None:
        extra_fields = _detect_populated_fields(results)

    extra_field_specs = EXTRA_FIELD_COLUMNS
    active_extra = [(k, v) for k, v in extra_field_specs if k in extra_fields]

    headers = base_cols.copy()
    for _, spec in active_extra:
        # Insert extra columns before Tier (last column)
        headers.insert(-1, spec["header"])

    header_row = headers
    separator = ["---"] * len(headers)

    rows = [header_row, separator]
    for result in results:
        row = [
            str(result.get("fullyQualifiedName") or ""),
        ]
        # Insert extra cell values before Tier
        for field, _spec in active_extra:
            row.append(_spec["format"](result.get(field)))
        row.extend([
            _format_people(result.get("owners")),
            _format_domains(result.get("domains")),
            _format_tier(result),
        ])
        rows.append(row)

    return ["| " + " | ".join(_escape_table_cell(cell) for cell in row) + " |" for row in rows]


def _detect_populated_fields(results: list[dict[str, Any]]) -> set[str]:
    """Find extra fields that have at least one non-empty value across results."""
    populated: set[str] = set()
    for field, _spec in EXTRA_FIELD_COLUMNS:
        for r in results:
            if not _is_empty(r.get(field)):
                populated.add(field)
                break
    return populated


# Extra columns that can appear in the table when data is present.
# Format: (result_key, {"header": "Display Header", "format": formatter_fn})
EXTRA_FIELD_COLUMNS: list[tuple[str, dict[str, Any]]] = [
    ("dataProducts", {"header": "Data Product", "format": lambda v: _format_data_products(v)}),
]


def _format_domains(values: Any) -> str:
    items = _as_list(values)
    labels = []
    for item in items:
        if isinstance(item, dict):
            labels.append(str(item.get("displayName") or item.get("name") or item.get("fullyQualifiedName") or item))
        else:
            labels.append(str(item))
    return ", ".join(label for label in labels if label)


def _format_data_products(values: Any) -> str:
    items = _as_list(values)
    labels = []
    for item in items:
        if isinstance(item, dict):
            labels.append(str(item.get("displayName") or item.get("name") or item.get("fullyQualifiedName") or item))
        else:
            labels.append(str(item))
    return ", ".join(label for label in labels if label)


def _escape_table_cell(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text.replace("|", "\\|")


def _append(lines: list[str], label: str, value: Any) -> None:
    if not _is_empty(value):
        lines.append(f"{label}: {value}")


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _shorten(value: Any, limit: int) -> str:
    if not value:
        return ""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _why_relevant(result: dict[str, Any]) -> str:
    signals = []
    if result.get("similarityScore") is not None:
        signals.append("semantic match")
    if _extract_tier_from_result(result):
        signals.append("tier signal")
    if result.get("owners"):
        signals.append("clear owner")
    if result.get("tags"):
        signals.append("relevant tags")
    if result.get("description"):
        signals.append("description available")
    return "Matched by " + ", ".join(signals) + "." if signals else "Returned by the metadata catalogue search."


def _extract_ssot_table_fqn(detail: dict[str, Any]) -> str | None:
    """Parse the SSOT table FQN from a glossary term's references."""
    references = _as_list(detail.get("references"))
    for ref in references:
        if isinstance(ref, dict):
            name = (ref.get("name") or "").lower().replace(" ", "")
            if name in ("ssot", "singlesourceoftruth"):
                endpoint = ref.get("endpoint", "")
                match = re.search(r"/table/(.+)$", endpoint)
                if match:
                    return match.group(1)
    return None


def _format_ssot_table(results: list[dict[str, Any]]) -> list[str]:
    """Format SSOT-referenced tables with their glossary source annotation."""
    base_cols = ["Table FQN", "Owner", "Domain", "Tier", "Glossary Source"]
    header = " | ".join(base_cols)
    sep = " | ".join("---" for _ in base_cols)
    rows = [header, sep]

    for r in results:
        source = r.get("_ssot_source", {})
        source_name = source.get("glossary_name", "")
        source_fqn = source.get("glossary_fqn", "")
        rows.append(
            "| "
            + " | ".join(
                _escape_table_cell(cell)
                for cell in [
                    r.get("fullyQualifiedName") or "",
                    _format_people(r.get("owners")),
                    _format_domains(r.get("domains")),
                    _format_tier(r),
                    f"{source_name} ({source_fqn})",
                ]
            )
            + " |"
        )
    return rows
