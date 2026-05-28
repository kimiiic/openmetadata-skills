from __future__ import annotations

import json
import re
from typing import Any

from data_discovery.models import Constraint, DiscoveryOptions, IntentSpec, ToolPlan


FQN_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+){2,}\b")

COMMAND_PREFIXES = (
    "/discover data",
    "/discover",
    "discover data",
    "find data for",
    "find datasets for",
    "find",
    "show me",
    "please",
    "can you",
    "could you",
)

ENTITY_TYPE_WORDS = {
    "table": ("dataset", "datasets", "table", "tables", "data product", "data products", "asset", "assets"),
    "dashboard": ("dashboard", "dashboards", "report", "reports", "visualisation", "visualisations", "visualization", "visualizations"),
    "pipeline": ("pipeline", "pipelines", "dag", "dags", "airflow", "job", "jobs"),
    "topic": ("kafka", "topic", "topics", "stream", "streams"),
    "glossaryTerm": ("glossary", "business term", "business terms", "term", "terms"),
    "metric": ("metric", "metrics", "kpi", "kpis", "measure", "measures"),
}

ENTITY_TYPE_OPTIONS = [
    {"entityType": "table", "label": "Table", "emoji": "📊"},
    {"entityType": "dashboard", "label": "Dashboard", "emoji": "📈"},
    {"entityType": "pipeline", "label": "Pipeline", "emoji": "🔄"},
    {"entityType": "topic", "label": "Topic / stream", "emoji": "📡"},
    {"entityType": "metric", "label": "Metric", "emoji": "🎯"},
    {"entityType": "glossaryTerm", "label": "Glossary term", "emoji": "📚"},
    {"entityType": "tag", "label": "Tag / classification", "emoji": "🏷️"},
    {"entityType": "mlmodel", "label": "ML model", "emoji": "🤖"},
    {"entityType": "container", "label": "Storage container", "emoji": "🗄️"},
    {"entityType": "dataProduct", "label": "Data product", "emoji": "📦"},
]

TECHNICAL_SERVICE_PREFIXES = ("starburst.", "snowflake.", "bigquery.", "postgres.", "mysql.")
LOOKUP_FILLER_WORDS = {
    "/discover",
    "find",
    "search",
    "lookup",
    "look",
    "list",
    "get",
    "show",
    "me",
    "for",
    "about",
    "related",
    "relating",
    "matching",
    "match",
    "matches",
    "containing",
    "contains",
    "like",
    "named",
    "name",
    "names",
    "called",
    "with",
    "in",
    "of",
    "by",
    "the",
    "a",
    "an",
    "all",
    "any",
    "please",
}
METADATA_OPERATOR_WORDS = {
    "owner",
    "owners",
    "owned",
    "tag",
    "tags",
    "tagged",
    "tier",
    "schema",
    "database",
    "service",
    "column",
    "columns",
    "fqn",
    "fully",
    "qualified",
    "data product",
    "data products",
    "dataproduct",
    "dataproducts",
}

# Fields that Claude can use when building an IntentSpec.
# Maps field -> list of supported operators, with a short description.
CONSTRAINT_FIELD_SCHEMA: dict[str, dict[str, object]] = {
    "dataProducts.name": {
        "operators": ["exists", "eq", "match"],
        "description": "Data product association — use 'exists' for 'has a data product', 'eq'/'match' for a specific named data product",
    },
    "tier.tagFQN": {
        "operators": ["eq"],
        "description": "Tier classification — use 'eq' with values like 'Tier.Tier1', 'Tier.Tier2', etc.",
    },
    "owners.name": {
        "operators": ["match", "prefix"],
        "description": "Owner name — use 'match' for partial/fuzzy owner name matching, 'prefix' for starts-with",
    },
    "tags.tagFQN": {
        "operators": ["eq", "match", "prefix"],
        "description": "Tag classification — use 'eq' for exact tag FQN, 'match' for partial, 'prefix' for starts-with",
    },
    "columns.name": {
        "operators": ["match", "prefix"],
        "description": "Column name — use 'match' to find tables containing a column with this name, 'prefix' for starts-with",
    },
    "service.name": {
        "operators": ["eq", "match", "prefix"],
        "description": "Service name — e.g. 'snowflake', 'bigquery', 'redshift'",
    },
    "database.name": {
        "operators": ["eq", "match", "prefix"],
        "description": "Database name — use 'eq' for exact match, 'prefix' for starts-with",
    },
    "databaseSchema.name": {
        "operators": ["eq", "match", "prefix"],
        "description": "Schema name — use 'eq' for exact match, 'prefix' for starts-with",
    },
    "fullyQualifiedName": {
        "operators": ["eq"],
        "description": "Exact fully-qualified name — e.g. 'snowflake.analytics.finance.invoices'",
    },
    "domains": {
        "operators": ["exists", "match"],
        "description": "Domain assignment — use 'exists' for 'has a domain', 'match' for a specific domain name",
    },
}

# Operator -> OpenSearch DSL builder.
# Each builder takes (field, value) and returns the DSL clause dict.
_OPERATOR_DSL: dict[str, object] = {
    "exists": lambda field, _value: {"exists": {"field": field}},
    "eq": lambda field, value: {"term": {field: value}},
    "match": lambda field, value: {"match": {field: value}},
    "prefix": lambda field, value: {"prefix": {field: value}},
}


def clean_query(question: str) -> str:
    cleaned = " ".join(str(question or "").strip().split())
    lower = cleaned.lower()
    for prefix in COMMAND_PREFIXES:
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
            lower = cleaned.lower()
            break
    return cleaned


def infer_entity_type(cleaned_query: str, override: str | None = None) -> tuple[str, bool]:
    if override:
        return override, True

    q = cleaned_query.lower()
    for entity_type, words in ENTITY_TYPE_WORDS.items():
        if any(_contains_phrase(q, word) for word in words):
            return entity_type, True

    if FQN_PATTERN.search(cleaned_query) or any(prefix in q for prefix in TECHNICAL_SERVICE_PREFIXES):
        return "table", True

    return "table", False


def build_tool_plan(question: str, options: DiscoveryOptions | None = None) -> ToolPlan:
    options = options or DiscoveryOptions()
    limit = _clamp_int(options.limit, 1, 50)
    threshold = _clamp_float(options.threshold, 0.0, 1.0)
    cleaned = clean_query(question)
    entity_type, has_entity_type_clue = infer_entity_type(cleaned, options.entity_type)
    constraints = extract_metadata_constraints(cleaned, entity_type)
    has_metadata_clue = bool(
        constraints["filters"]
        or constraints["fqn"]
        or constraints.get("column_filters")
        or constraints["free_text_metadata_clue"]
        or (has_entity_type_clue and options.entity_type is None and constraints["entity_scoped_lookup"])
    )

    if not has_entity_type_clue and has_metadata_clue:
        return ToolPlan(
            primary_tool="clarify_entity_type",
            fallback_tool=None,
            arguments={},
            entity_type="",
            enrich=False,
            reason="No entity type keyword found in the query, but a short technical name was detected.",
            cleaned_query=cleaned,
            needs_entity_type=True,
            entity_type_options=ENTITY_TYPE_OPTIONS,
        )

    if not has_entity_type_clue and _needs_entity_type_clarification(cleaned, has_metadata_clue):
        return ToolPlan(
            primary_tool="clarify_entity_type",
            fallback_tool=None,
            arguments={},
            entity_type="",
            enrich=False,
            reason="The query has a lookup clue but no clear OpenMetadata entity type.",
            cleaned_query=cleaned,
            needs_entity_type=True,
            entity_type_options=ENTITY_TYPE_OPTIONS,
        )

    if constraints["unsupported"]:
        return _semantic_plan(
            cleaned,
            entity_type,
            limit,
            threshold,
            reason="A structured metadata constraint was unsupported, so semantic search is safer.",
            unsupported_constraints=constraints["unsupported"],
        )

    if has_entity_type_clue and has_metadata_clue:
        query_filter = build_query_filter(entity_type, constraints["filters"])
        column_filters: list[str] = constraints.get("column_filters", [])
        # Route column constraints through the `query` parameter instead of
        # `queryFilter` — the remote tool discards column-level queryFilter clauses.
        if column_filters:
            column_query = " AND ".join(f"columns.name:{c}" for c in column_filters)
            query_text = f"{column_query} {constraints['query_text'] or cleaned}".strip()
        else:
            query_text = constraints["query_text"] or cleaned or "*"
        arguments: dict[str, Any] = {
            "query": query_text,
            "entityType": entity_type,
            "size": limit,
            "from": 0,
            "includeDeleted": False,
            "fields": "columns,owners,tags,domains,dataProducts",
        }
        if query_filter:
            arguments["queryFilter"] = json.dumps(query_filter)

        return ToolPlan(
            primary_tool="search_metadata",
            fallback_tool="semantic_search",
            arguments=arguments,
            entity_type=entity_type,
            enrich=True,
            reason="Entity type and metadata clues were both present.",
            cleaned_query=cleaned,
            query_filter=query_filter,
        )

    return _semantic_plan(
        cleaned,
        entity_type,
        limit,
        threshold,
        reason="Intent was broad or ambiguous, so semantic search is safer.",
    )


def extract_metadata_constraints(cleaned_query: str, entity_type: str) -> dict[str, Any]:
    q = cleaned_query.lower()
    filters: list[dict[str, Any]] = []
    unsupported: list[str] = []
    fqn = _find_fqn(cleaned_query)

    if fqn:
        filters.append({"term": {"fullyQualifiedName": fqn}})

    # Column constraints go into the `query` parameter, not `queryFilter`,
    # because the remote search_metadata MCP tool silently discards
    # queryFilter clauses on nested `columns.name` fields.
    column_filters: list[str] = []
    column = _extract_after_patterns(cleaned_query, (r"\bcolumns?\s+(?:named\s+)?([A-Za-z0-9_.-]+)", r"\bwith\s+([A-Za-z0-9_]+_id)\b"))
    if column:
        column_filters.append(column)

    owner = _extract_after_patterns(cleaned_query, (r"\bowned by\s+(.+?)(?:\s+tagged|\s+tier|\s+with|\s+in\s+schema|\s+in\s+database|$)", r"\bowner\s+(.+?)(?:\s+tagged|\s+tier|\s+with|$)"))
    if owner:
        filters.append({"match": {"owners.name": owner}})

    tag = _extract_after_patterns(cleaned_query, (r"\btagged as\s+(.+?)(?:\s+owned|\s+tier|\s+with|$)", r"\btag\s+(.+?)(?:\s+owned|\s+tier|\s+with|$)"))
    if tag:
        filters.append({"match": {"tags.tagFQN": _normalize_tag(tag)}})

    tier = _extract_tier(q)
    if tier:
        filters.append({"term": {"tier.tagFQN": tier}})

    service = _extract_after_patterns(
        cleaned_query,
        (
            r"\bservice\s+name\s+([A-Za-z0-9_.-]+)",
            r"\bin service\s+([A-Za-z0-9_.-]+)",
            r"\bservice:\s*([A-Za-z0-9_.-]+)",
        ),
    )
    if service:
        filters.append({"match": {"service.name": service}})

    database = _extract_after_patterns(cleaned_query, (r"\bdatabase\s+([A-Za-z0-9_.-]+)",))
    if database:
        filters.append({"match": {"database.name": database}})

    schema = _extract_after_patterns(cleaned_query, (r"\bschema\s+([A-Za-z0-9_.-]+)", r"\bin schema\s+([A-Za-z0-9_.-]+)"))
    if schema:
        filters.append({"match": {"databaseSchema.name": schema}})

    data_product = _extract_data_product(cleaned_query)
    if data_product:
        filters.append({"match": {"dataProducts.name": data_product}})
    elif _has_any_data_product_constraint(q):
        filters.append({"exists": {"field": "dataProducts.name"}})

    free_text_metadata_clue = any(
        clue in q
        for clue in (
            "table name",
            "dashboard name",
            "fqn",
            "fully qualified",
            "tier",
            "owner",
            "owned by",
            "tagged",
            "tag ",
            "schema",
            "database",
            "service name",
            "service:",
        )
    ) or _looks_like_name_lookup(cleaned_query, entity_type)

    if any(word in q for word in ("partition", "sample data", "row count")):
        unsupported.extend([word for word in ("partition", "sample data", "row count") if word in q])

    query_text = _extract_lookup_query(cleaned_query, entity_type) or cleaned_query
    clue_tokens = _lookup_clue_tokens(cleaned_query)
    return {
        "filters": filters,
        "column_filters": column_filters,
        "unsupported": unsupported,
        "fqn": fqn,
        "free_text_metadata_clue": free_text_metadata_clue,
        "entity_scoped_lookup": 0 < len(clue_tokens) <= 3,
        "query_text": query_text,
    }


def build_query_filter(entity_type: str, filters: list[dict[str, Any]]) -> dict[str, Any] | None:
    must = [{"term": {"entityType": entity_type}}]
    must.extend(filters)
    if len(must) == 1:
        return None
    return {"bool": {"must": must}}


def semantic_fallback_arguments(plan: ToolPlan) -> dict[str, Any]:
    return {
        "query": plan.cleaned_query,
        "filters": {"entityType": [plan.entity_type]},
        "size": plan.arguments.get("size", 5),
        "from": 0,
        "k": 100,
        "threshold": 0.0,
    }


def build_tool_plan_from_intent(intent: IntentSpec, limit: int = 10) -> ToolPlan:
    """Build a ToolPlan from AI-extracted structured intent.

    This is the primary path when invoked through Claude Code: Claude extracts
    an IntentSpec from the user's natural language question, and this function
    deterministically builds the correct OpenSearch DSL queryFilter.

    The AI never generates raw DSL — it only fills out the IntentSpec fields.
    Python handles the mapping to OpenSearch query syntax.
    """
    entity_type = intent.entity_type or "table"
    cleaned = intent.query_text or ""
    limit = _clamp_int(limit, 1, 50)

    if intent.needs_clarification:
        return ToolPlan(
            primary_tool="clarify_entity_type",
            fallback_tool=None,
            arguments={},
            entity_type="",
            enrich=False,
            reason="AI could not determine the entity type from the question.",
            cleaned_query=cleaned,
            needs_entity_type=True,
            entity_type_options=ENTITY_TYPE_OPTIONS,
        )

    if not intent.constraints:
        return _semantic_plan(
            cleaned,
            entity_type,
            limit,
            0.0,
            reason="AI found no structured constraints — broad discovery via semantic search.",
        )

    # Separate column constraints — they go into the `query` parameter
    # because the remote search_metadata MCP tool silently discards
    # queryFilter clauses on nested `columns.name` fields.
    column_constraints = [c for c in intent.constraints if c.field == "columns.name"]
    other_constraints = [c for c in intent.constraints if c.field != "columns.name"]

    dsl_clauses: list[dict[str, Any]] = []
    unsupported: list[str] = []

    for constraint in other_constraints:
        schema = CONSTRAINT_FIELD_SCHEMA.get(constraint.field)
        if schema is None:
            unsupported.append(constraint.field)
            continue

        allowed = schema.get("operators", [])
        if isinstance(allowed, list) and constraint.operator not in allowed:
            unsupported.append(f"{constraint.field}:{constraint.operator}")
            continue

        builder = _OPERATOR_DSL.get(constraint.operator)  # type: ignore[ assignment]
        if builder is None:
            unsupported.append(f"{constraint.field}:{constraint.operator}")
            continue

        if constraint.operator == "exists":
            dsl_clauses.append(builder(constraint.field, None))  # type: ignore[call-arg]
        elif constraint.value is not None:
            dsl_clauses.append(builder(constraint.field, constraint.value))  # type: ignore[call-arg]
        else:
            unsupported.append(f"{constraint.field}:{constraint.operator} (missing value)")

    if unsupported:
        return _semantic_plan(
            cleaned,
            entity_type,
            limit,
            0.0,
            reason=f"Unsupported constraints: {', '.join(unsupported)}",
            unsupported_constraints=unsupported,
        )

    # Build the queryFilter from non-column constraints only.
    filter_clauses: list[dict[str, Any]] = [{"term": {"entityType": entity_type}}, *dsl_clauses]

    # Build query text: column constraints use field:value syntax in the
    # `query` parameter; text search goes in queryFilter.should when there
    # are non-column constraints, or in `query` when there are only columns.
    column_query_parts = [f"columns.name:{c.value}" for c in column_constraints if c.value]
    column_query = " AND ".join(column_query_parts)
    has_semantic_query = bool(cleaned) and cleaned != "*"
    has_non_column_constraints = len(filter_clauses) > 1

    if column_query:
        # Column constraints go into `query`; optional semantic text appended.
        query_text = f"{column_query} {cleaned}".strip() if cleaned else column_query
        if has_non_column_constraints:
            query_filter = {"bool": {"must": filter_clauses}}
        else:
            query_filter = None
    elif has_non_column_constraints and has_semantic_query:
        # No column constraints — original behavior: text in queryFilter.should,
        # query is "*" so the remote tool uses queryFilter exclusively.
        query_text = "*"
        query_filter = {
            "bool": {
                "filter": filter_clauses,
                "should": [
                    {
                        "multi_match": {
                            "query": cleaned,
                            "fields": [
                                "fullyQualifiedName^3",
                                "name^2.5",
                                "displayName^2.5",
                                "description",
                            ],
                        }
                    }
                ],
            }
        }
    elif has_non_column_constraints:
        query_text = "*"
        query_filter = {"bool": {"must": filter_clauses}}
    else:
        # Only entityType filter — no constraints at all. Shouldn't reach here
        # since non-empty intent.constraints was already checked, but handle it.
        query_text = cleaned or "*"
        query_filter = None

    # Derive fields from constraint fields.
    constraint_fields = {c.field.split(".")[0] for c in intent.constraints}
    extra_fields = {"dataProducts", "domains"} | constraint_fields
    fields = ",".join(sorted(extra_fields))

    arguments: dict[str, Any] = {
        "query": query_text,
        "entityType": entity_type,
        "size": limit,
        "from": 0,
        "includeDeleted": False,
        "fields": fields,
    }
    if query_filter is not None:
        arguments["queryFilter"] = json.dumps(query_filter)

    return ToolPlan(
        primary_tool="search_metadata",
        fallback_tool="semantic_search",
        arguments=arguments,
        entity_type=entity_type,
        enrich=True,
        reason="AI extracted structured constraints from the question.",
        cleaned_query=query_text,
        query_filter=query_filter,
    )


def _semantic_plan(
    cleaned: str,
    entity_type: str,
    limit: int,
    threshold: float,
    reason: str,
    unsupported_constraints: list[str] | None = None,
) -> ToolPlan:
    return ToolPlan(
        primary_tool="semantic_search",
        fallback_tool="search_metadata",
        arguments={
            "query": cleaned,
            "filters": {"entityType": [entity_type]},
            "size": limit,
            "from": 0,
            "k": 100,
            "threshold": threshold,
        },
        entity_type=entity_type,
        enrich=True,
        reason=reason,
        cleaned_query=cleaned,
        unsupported_constraints=unsupported_constraints or [],
    )


def _find_fqn(text: str) -> str | None:
    match = FQN_PATTERN.search(text)
    return match.group(0) if match else None


def _extract_after_patterns(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip('"').strip("'")
            return value.rstrip(".,") if value else None
    return None


def _extract_tier(q: str) -> str | None:
    match = re.search(r"\btier[.\s-]*(\d)\b", q)
    if match:
        return f"Tier.Tier{match.group(1)}"
    return None


def _extract_data_product(q: str) -> str | None:
    patterns = [
        r"\bdata products?\s+([A-Za-z0-9_.\s-]+?)(?:\s+in\s+|\s+owned|\s+tagged|\s+tier|\s+with|\s+in\s+schema|\s+in\s+database|$)",
        r"\bdataproducts?\s+([A-Za-z0-9_.\s-]+?)(?:\s+in\s+|\s+owned|\s+tagged|\s+tier|\s+with|\s+in\s+schema|\s+in\s+database|$)",
        r"\bdp[_]?([A-Za-z0-9_.\s-]+?)(?:\s+in\s+|\s+owned|\s+tagged|\s+tier|\s+with|\s+in\s+schema|\s+in\s+database|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip('"').strip("'").rstrip(".,")
    return None


def _has_any_data_product_constraint(q: str) -> bool:
    return bool(re.search(r"\b(?:any|have|has|with|having)\s+data\s*products?\b", q, flags=re.IGNORECASE))


def _normalize_tag(tag: str) -> str:
    tag = " ".join(tag.split()).strip()
    if "." in tag:
        return tag
    return tag


def _looks_like_name_lookup(text: str, entity_type: str) -> bool:
    if entity_type not in {"table", "dashboard", "pipeline", "topic", "metric", "glossaryTerm"}:
        return False
    clue_tokens = _lookup_clue_tokens(text)
    if any(re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]|[_-]", token) for token in clue_tokens):
        return True
    return len(clue_tokens) == 1 and len(clue_tokens[0]) <= 16


def _needs_entity_type_clarification(cleaned_query: str, has_metadata_clue: bool) -> bool:
    clue_tokens = _lookup_clue_tokens(cleaned_query)
    if has_metadata_clue:
        return True
    if len(clue_tokens) == 1:
        return True
    return False


def _extract_lookup_query(text: str, entity_type: str) -> str:
    fqn = _find_fqn(text)
    if fqn:
        return fqn

    clue_tokens = _lookup_clue_tokens(text)

    technical_tokens = [
        token
        for token in clue_tokens
        if re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]|[_-]", token)
    ]
    if technical_tokens:
        return " ".join(technical_tokens)

    if entity_type and clue_tokens and len(clue_tokens) <= 3:
        return " ".join(clue_tokens)
    return ""


def _lookup_clue_tokens(text: str) -> list[str]:
    text = _remove_multi_word_entity_phrases(text)
    tokens = [token.strip(".,:;\"'()[]{}") for token in re.split(r"\s+", text.strip()) if token.strip()]
    return [token for token in tokens if _is_lookup_clue_token(token)]


def _is_lookup_clue_token(token: str) -> bool:
    lower = token.lower()
    if lower in LOOKUP_FILLER_WORDS or lower in METADATA_OPERATOR_WORDS:
        return False
    if _is_entity_word(lower):
        return False
    return True


def _is_entity_word(lower_token: str) -> bool:
    for words in ENTITY_TYPE_WORDS.values():
        for word in words:
            if " " not in word and lower_token == word:
                return True
    return False


def _remove_multi_word_entity_phrases(text: str) -> str:
    result = text
    multi_word_aliases = [word for words in ENTITY_TYPE_WORDS.values() for word in words if " " in word]
    for alias in sorted(multi_word_aliases, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(alias)}\b", " ", result, flags=re.IGNORECASE)
    return result


def _contains_phrase(text: str, phrase: str) -> bool:
    if " " in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return min(max(int(value), minimum), maximum)


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)
