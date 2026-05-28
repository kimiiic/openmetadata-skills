from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityTypeDef:
    """Canonical definition for a supported OpenMetadata entity type."""

    entity_type: str
    label: str
    emoji: str
    prompt_label: str = ""  # User-facing category description for entity-type prompts
    keywords: tuple[str, ...] = ()  # NLP trigger words; empty = only selectable via prompt

    def __post_init__(self):
        if not self.prompt_label:
            object.__setattr__(self, "prompt_label", f"{self.label}s")


ENTITY_TYPE_REGISTRY: list[EntityTypeDef] = [
    EntityTypeDef("table", "Table", "📊", prompt_label="Tables / datasets", keywords=("dataset", "datasets", "table", "tables", "data product", "data products", "asset", "assets")),
    EntityTypeDef("dashboard", "Dashboard", "📈", prompt_label="Dashboards / reports", keywords=("dashboard", "dashboards", "report", "reports", "visualisation", "visualisations", "visualization", "visualizations")),
    EntityTypeDef("pipeline", "Pipeline", "🔄", prompt_label="Pipelines / jobs", keywords=("pipeline", "pipelines", "dag", "dags", "airflow", "job", "jobs")),
    EntityTypeDef("topic", "Topic / stream", "📡", prompt_label="Topics / streams", keywords=("kafka", "topic", "topics", "stream", "streams")),
    EntityTypeDef("metric", "Metric", "🎯", prompt_label="Metrics / KPIs", keywords=("metric", "metrics", "kpi", "kpis", "measure", "measures")),
    EntityTypeDef("glossaryTerm", "Glossary term", "📚", prompt_label="Glossary terms", keywords=("glossary", "business term", "business terms", "term", "terms")),
    EntityTypeDef("tag", "Tag / classification", "🏷️", prompt_label="Tags / classifications"),
    EntityTypeDef("mlmodel", "ML model", "🤖", prompt_label="ML models"),
    EntityTypeDef("container", "Storage container", "🗄️", prompt_label="Storage containers"),
    EntityTypeDef("dataProduct", "Data product", "📦", prompt_label="Data products"),
]

# Derived views — single source of truth, different formats for different consumers.
ENTITY_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    d.entity_type: d.keywords for d in ENTITY_TYPE_REGISTRY if d.keywords
}

ENTITY_TYPE_OPTIONS: list[dict[str, str]] = [
    {"entityType": d.entity_type, "label": d.label, "emoji": d.emoji}
    for d in ENTITY_TYPE_REGISTRY
]

ENTITY_TYPE_PROMPT_OPTIONS: list[tuple[str, str, str]] = [
    (d.emoji, d.entity_type, d.prompt_label) for d in ENTITY_TYPE_REGISTRY
]


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
