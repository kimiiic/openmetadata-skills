from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolPlan:
    primary_tool: str
    arguments: dict[str, Any]
    fallback_tool: str | None = None
    entity_type: str = "table"
    enrich: bool = True
    reason: str = ""
    cleaned_query: str = ""
    query_filter: dict[str, Any] | None = None
    unsupported_constraints: list[str] = field(default_factory=list)
    needs_entity_type: bool = False
    entity_type_options: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Constraint:
    """A single metadata constraint extracted from a natural language question.

    The AI (Claude) produces these; Python maps them to OpenSearch DSL clauses.
    """

    field: str  # e.g. "dataProducts.name", "tier.tagFQN", "columns.name"
    operator: str  # "exists" | "eq" | "match" | "prefix"
    value: str | None = None  # None only for "exists"


@dataclass
class IntentSpec:
    """Structured intent extracted by AI from a natural language discovery question.

    Claude interprets the user's question and fills this out. Python then builds
    the correct OpenSearch DSL queryFilter deterministically — the AI never
    generates raw DSL.
    """

    entity_type: str = "table"
    constraints: list[Constraint] = field(default_factory=list)
    query_text: str = ""  # optional free-text part of the query
    needs_clarification: bool = False


@dataclass
class DiscoveryOptions:
    limit: int = 10
    enrich: bool = True
    enrich_limit: int = 3
    entity_type: str | None = None
    threshold: float = 0.0
    debug: bool = False
