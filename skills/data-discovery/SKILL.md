---
name: data-discovery
description: Discovers governed metadata assets (tables, dashboards, pipelines, topics, metrics, glossary terms, ML models) from OpenMetadata / Collate. Use when the user asks to find, search, or discover data assets, tables, dashboards, or metadata. Do NOT use for mutating metadata, creating assets, editing tags/owners/descriptions, or retrieving production data records.
---

# Data Discovery

Discover metadata assets from an OpenMetadata / Collate instance through a local CLI that calls remote MCP tools via the Collate Data AI SDK. No local MCP server required.

## Prerequisites

Set two environment variables pointing at your Collate / OpenMetadata instance:

```bash
export AI_SDK_HOST=https://your-instance.collate.ai
export AI_SDK_TOKEN_KEY=your-api-token
```

Or create a `.env` file in your project root:

```env
AI_SDK_HOST=https://your-instance.collate.ai
AI_SDK_TOKEN_KEY=your-api-token
```

Find your API token in the Collate / OpenMetadata UI under **Settings → API Tokens**.

## Quick Start

Run the CLI via npx (handles bootstrapping automatically):

```bash
npx data-discovery-skill "user's question" --limit 10
```

Or with structured intent:

```bash
npx data-discovery-skill --intent '{"entity_type":"table","constraints":[{"field":"columns.name","operator":"match","value":"email"}]}' --limit 10
```

If you have the repo cloned locally, you can also use `uv run` directly:

```bash
uv run discover-data "user's question" --limit 10
```

## Workflow

### Step 1 — Classify the question

Read the user's question. Determine whether it has **structured metadata constraints** or is a **broad business discovery**.

- **Structured constraints**: column names, tiers, owners, tags, service names, database/schema names, FQN, domains, data products. When present, build an `IntentSpec` (Step 2).
- **Broad/ambiguous**: business questions like "customer complaints" or "order fulfillment" with no technical metadata clues. Route to semantic search (Step 3).

When you need the full constraint schema or entity type mappings, read:
- `references/constraint-schema.md` — all available fields, operators, and rules
- `references/entity-types.md` — how user wording maps to OpenMetadata entity types
- `references/intent-examples.md` — worked examples of natural language to IntentSpec

### Step 2 — Build an IntentSpec for structured queries

When the question has structured constraints, build an `IntentSpec` and call `discover_data()`:

```python
from data_discovery import discover_data
from data_discovery.models import IntentSpec, Constraint

intent = IntentSpec(
    entity_type="table",
    constraints=[
        Constraint(field="columns.name", operator="match", value="email"),
    ],
    query_text="customer",  # optional free-text part
)
result = discover_data("user's original question", intent=intent, limit=10)
print(result["answer"])
```

Or pass the intent as JSON via the CLI:

```bash
npx data-discovery-skill --intent '{"entity_type":"table","constraints":[...]}' --limit 10
```

### Step 3 — Semantic search for broad questions

When no structured constraints are present, use semantic search by calling the CLI without an intent:

```bash
npx data-discovery-skill "customer complaints" --limit 10
```

The CLI's regex router handles entity type inference and tool selection automatically.

### Step 4 — Interpret and present results

Results come back as a formatted table. Present them to the user with:

- The matching table FQN, owner, domain, and tier
- For SSOT (Single Source of Truth) results: highlight the glossary term that links to the authoritative table
- When table results are noisy or incomplete, proactively suggest searching glossary terms — glossary terms often have SSOT references to the authoritative table

### Step 5 — Follow up when appropriate

After presenting results, offer natural follow-ups:
- "Want me to get column details on any of these?"
- "Should I search glossary terms for SSOT references?"
- "Would you like to filter by tier or domain?"

## Safety Rules

- Read-only tools only — never call mutation tools (patch_entity, create_lineage, create_glossary, etc.)
- Do not invent metadata
- Do not expose tokens or credentials
- Do not connect directly to source databases
- Do not retrieve production data records
