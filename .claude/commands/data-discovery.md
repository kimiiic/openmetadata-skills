---
name: data-discovery
description: Discover governed OpenMetadata / Collate metadata assets through a local CLI that calls remote MCP-compatible tools via the Collate Data AI SDK. Use when the user asks to discover data, use `/discover data`, search Collate/OpenMetadata metadata, find tables/dashboards/assets, or route through semantic_search/search_metadata/get_entity_details without a local MCP server.
---

# Data Discovery

Use this skill to help the user discover metadata assets in OpenMetadata / Collate through the repo's Discovery CLI.

Do not create or register a local MCP server. The runtime path is:

```text
Discovery CLI -> Data AI SDK -> remote OpenMetadata / Collate MCP endpoint
```

## Quick Start

Prefer the uv console command:

```bash
uv run discover-data /discover data customer complaints
```

The alias also works:

```bash
uv run disover-data /discover data customer complaints
```

Flag form:

```bash
uv run discover-data --question "customer complaints" --limit 5
```

## Workflow

### Step 1 — Extract intent from the question (AI-driven, primary path)

Read the user's question. Determine whether it has structured metadata constraints or is a broad business discovery.

**If the question has structured constraints**, build an `IntentSpec` and call `discover_data()` with it. This lets Python deterministically construct the correct OpenSearch DSL — the AI never generates raw DSL.

**If the question is broad/ambiguous with no constraints**, use semantic_search via the standard CLI path (Step 2).

Pass the intent by calling `discover_data()` directly in Python:

```python
from data_discovery import discover_data
from data_discovery.models import IntentSpec, Constraint

intent = IntentSpec(
    entity_type="table",
    constraints=[
        Constraint(field="dataProducts.name", operator="exists"),
    ],
    query_text="",  # optional free-text part
)
result = discover_data("user's original question", intent=intent, limit=5)
print(result["answer"])
```

Or via the CLI with the `--intent` flag:

```bash
uv run discover-data --intent '{"entity_type":"table","constraints":[{"field":"dataProducts.name","operator":"exists"}]}' --limit 5
```

#### Constraint field schema

Use ONLY these fields and operators when building constraints:

| Field | Operators | Description |
|---|---|---|
| `dataProducts.name` | `exists`, `eq`, `match` | Data product association. Use `exists` for "has a data product", `eq`/`match` for a named data product |
| `tier.tagFQN` | `eq` | Tier classification. Values: `Tier.Tier1`, `Tier.Tier2`, `Tier.Tier3`, `Tier.Tier4`, `Tier.Tier5` |
| `owners.name` | `match` | Owner name (partial/fuzzy matching) |
| `tags.tagFQN` | `eq`, `match` | Tag classification. Use `eq` for exact tag FQN, `match` for partial |
| `columns.name` | `match` | Column name — find tables containing this column |
| `service.name` | `eq`, `match` | Service name (snowflake, bigquery, redshift, etc.) |
| `database.name` | `eq`, `match` | Database name |
| `databaseSchema.name` | `eq`, `match` | Schema name |
| `fullyQualifiedName` | `eq` | Exact FQN match (e.g. `snowflake.analytics.finance.invoices`) |
| `domains` | `exists`, `match` | Domain assignment. Use `exists` for "has a domain" |

Supported operators:
- **`exists`** — field has a non-null value (value must be `null`/omitted)
- **`eq`** — exact term match
- **`match`** — text match (partial/fuzzy)
- **`prefix`** — prefix match

#### Entity type detection

Map user wording to entity types:

| User says | entity_type |
|---|---|
| dataset, table, data product, asset | `table` |
| dashboard, report, visualisation | `dashboard` |
| pipeline, DAG, Airflow, job | `pipeline` |
| Kafka, topic, stream | `topic` |
| glossary, business term, term | `glossaryTerm` |
| metric, KPI, measure | `metric` |
| tag, classification | `tag` |
| ML model | `mlmodel` |
| storage container | `container` |

Default: `table`.

If the entity type is genuinely ambiguous, set `needs_clarification: true` on the IntentSpec — the skill will prompt the user to choose.

#### Example translations

```
"find tables which have data products" / "how many tables belong to a data product"
  → IntentSpec(entity_type="table", constraints=[
      Constraint(field="dataProducts.name", operator="exists")
    ])

"show tier 1 dashboards owned by marketing"
  → IntentSpec(entity_type="dashboard", constraints=[
      Constraint(field="tier.tagFQN", operator="eq", value="Tier.Tier1"),
      Constraint(field="owners.name", operator="match", value="marketing")
    ])

"tables with email column tagged as PII"
  → IntentSpec(entity_type="table", constraints=[
      Constraint(field="columns.name", operator="match", value="email"),
      Constraint(field="tags.tagFQN", operator="match", value="PII")
    ])

"find snowflake tables in the finance database"
  → IntentSpec(entity_type="table", constraints=[
      Constraint(field="service.name", operator="eq", value="snowflake"),
      Constraint(field="database.name", operator="eq", value="finance")
    ])

"tables that have a domain assigned"
  → IntentSpec(entity_type="table", constraints=[
      Constraint(field="domains", operator="exists")
    ])
```

#### Important rules

- **Never generate raw OpenSearch DSL.** Claude outputs `IntentSpec` (field + operator + value). Python maps to DSL.
- Only use fields from the schema above. If a constraint doesn't map to any field, use semantic_search instead.
- All constraints in the list are ANDed together.
- Set `query_text` to any free-text part of the question that isn't captured by structured constraints (e.g. for "find customer tables with email column", `query_text` might be "customer").

### Step 2 — Fallback: regex router (standalone CLI)

When no `IntentSpec` is provided, the CLI uses the regex-based router:

1. Use `semantic_search` for broad, ambiguous, or business-oriented questions.
2. If a short lookup has no clear entity type, prompt the user to choose an entity type with emoji-labelled options.
3. Use `search_metadata` only when both an entity-type clue and a metadata clue are present.
4. Use OpenSearch DSL `queryFilter` for explicit field constraints.
5. Enrich top candidates with `get_entity_details` using returned `entityType` and `fullyQualifiedName`.
6. Return a business discovery answer by default; use `--json` for structured output.

## Safety Rules

- Read-only tools only.
- Do not call mutation tools.
- Do not invent metadata.
- Do not expose tokens or credentials.
- Do not connect directly to source databases.
- Do not retrieve production data records.

## Verification

```bash
uv run python -m unittest discover -s tests
```

See `REFERENCE.md` for the compact implementation contract.
