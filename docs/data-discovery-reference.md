# Context: Python Data Discovery Skill for GitHub Copilot IDE

## Purpose

Build a Python-first **data discovery skill** that can be used from a CLI while GitHub Copilot IDE acts as a coding/context aid.

The skill must **not** start or expose a local MCP server.

The skill should call the remote OpenMetadata / Collate MCP-compatible endpoints through the approved Data AI SDK package.

The goal is to let a user ask something like:

```text
/discover data order fulfillment
```

The skill should translate the natural language question into a structured tool plan, call the correct hosted OpenMetadata / Collate MCP tool, enrich the result where useful, and return a concise business-friendly discovery answer.

---

## Enterprise Constraint

Do not build a local MCP server.

The enterprise environment does not allow local MCP servers to be registered inside VS Code / GitHub Copilot.

Correct pattern:

```text
User
    ↓ runs Discovery CLI
Local Python wrapper skill
    ↓ Data AI SDK
Hosted OpenMetadata / Collate MCP endpoint
    ↓
OpenMetadata / Collate metadata tools
```

Incorrect pattern:

```text
GitHub Copilot IDE
    ↓ direct MCP tool call
Local MCP server
    ↓
OpenMetadata / Collate
```

GitHub Copilot may help author or explain the Python code, but it must not be the runtime interface to MCP tools.

---

## Recommended Project Structure

Use this structure:

```text
data-discovery-skill/
├── context.md
├── SKILL.md
├── README.md
├── requirements.txt
├── .env.example
├── scripts/
│   └── discover_data.py
└── src/
    └── data_discovery/
        ├── __init__.py
        ├── config.py
        ├── client.py
        ├── router.py
        ├── tools.py
        ├── rdf_tools.py
        ├── formatter.py
        └── models.py
```

---

## Required Python Behaviour

The Python wrapper should expose one main entry point:

```python
discover_data(question: str, limit: int = 5) -> dict
```

This function should:

1. Accept the user’s raw question.
2. Clean the question.
3. Infer intent.
4. Select the right hosted MCP tool.
5. Build the tool payload.
6. Call the hosted OpenMetadata / Collate MCP tool via AI SDK.
7. Optionally enrich top results using `get_entity_details`.
8. Return:
   - original question
   - tool plan
   - raw or normalized results
   - formatted business answer

---

## Environment Variables

Use environment variables.

```bash
AI_SDK_HOST="https://your-openmetadata-or-collate-host"
AI_SDK_TOKEN="your-bot-or-user-jwt-token"
```

Optional environment variables supported by the Collate AI SDK:

```bash
AI_SDK_TIMEOUT="120"
AI_SDK_VERIFY_SSL="true"
AI_SDK_MAX_RETRIES="3"
AI_SDK_RETRY_DELAY="1.0"
```

Do not hardcode tokens.

Do not print tokens.

Do not commit `.env`.

## Collate AI SDK Integration

The official Python package is:

```bash
pip install data-ai-sdk
```

The Python import path is:

```python
from ai_sdk import AISdk, AISdkConfig
```

Initialize the client from environment variables:

```python
config = AISdkConfig.from_env()
client = AISdk.from_config(config)
```

List available remote MCP tools dynamically:

```python
tools = client.mcp.list_tools()
```

Call remote MCP tools through the SDK:

```python
result = client.mcp.call_tool(
    "search_metadata",
    {
        "query": "customers",
        "entity_type": "table",
        "limit": 5,
    },
)
```

Source: <https://docs.getcollate.io/sdk/ai-sdk>

Important: the SDK documentation shows a simple Python example using `entity_type` and `limit`, but the OpenMetadata MCP source implementation reads camelCase tool parameters such as `entityType`, `size`, `from`, `queryFilter`, `includeDeleted`, `upstreamDepth`, and `downstreamDepth`. Prefer the runtime schema returned by `client.mcp.list_tools()` and use the source-backed camelCase payloads below when calling the discovery tools.

Source: <https://github.com/open-metadata/OpenMetadata/tree/main/openmetadata-mcp>

Runtime note: the installed Collate SDK may expect `client.mcp.call_tool(...)` to receive an `ai_sdk.mcp.models.MCPTool` enum, not a plain string. The MCP endpoint may also return `text/event-stream` responses containing `data: {...}` JSON-RPC events. The local `CollateAIClient` adapter handles both details.

---

## Core Hosted MCP Tools

Version 1 should focus on these tools:

```text
semantic_search
search_metadata
get_entity_details
```

Optional later tools:

```text
get_entity_lineage
```

Optional RDF / Knowledge Graph tools if available in the hosted OpenMetadata / Collate environment:

```text
SparqlQueryTool
EntityNeighborhoodTool
FindByTagTool
OntologyDescribeTool
ShaclValidateTool
```

The actual MCP tool names may be lower snake case depending on the tool schema returned by MCP `list_tools`.

Always detect available tools dynamically if possible.

---

## Tool Routing Rules

### Default discovery behaviour

For `/discover data` style requests, default to `semantic_search`.

Examples:

```text
/discover data order fulfillment
Find data related to broadband availability
Which datasets are useful for churn analysis?
What data products relate to appointment delays?
```

Use:

```text
semantic_search
```

Then enrich top results using:

```text
get_entity_details
```

---

## Three-Tool Discovery Plan

The first version should orchestrate three read-only hosted metadata tools:

```text
semantic_search
search_metadata
get_entity_details
```

Optional lineage can be added later with:

```text
get_entity_lineage
```

### Tool 1: `semantic_search`

Use this for business-intent discovery when the user describes meaning, use case, domain, or analytical need.

Example questions:

```text
/discover data order fulfillment
Which datasets help with churn analysis?
Find data about appointment delays
```

Payload:

```python
{
    "query": cleaned_query,
    "filters": {
        "entityType": [entity_type],
    },
    "size": limit,
    "from": 0,
    "k": 100,
    "threshold": threshold,
}
```

Capability notes from source:

- `query` is required.
- `size` defaults to 10 and is capped at 50.
- `k` defaults to 100 and is capped at 10,000.
- `threshold` defaults to 0.0 and is clamped between 0.0 and 1.0.
- The response tells callers to use the exact returned `entityType` and `fullyQualifiedName` values for `get_entity_details`.
- The tool returns a clear error when vector embeddings are not enabled.

### Tool 2: `search_metadata`

Use this for exact metadata lookup when the user gives technical clues such as a column, owner, tag, tier, service, schema, database, table name, dashboard name, or fully qualified name.

Example questions:

```text
Find tables with customer_id
Find table snowflake.analytics.finance.invoices
Find assets owned by Finance Team
Find Tier 1 datasets
```

Basic payload:

```python
{
    "query": cleaned_query or "*",
    "entityType": entity_type,
    "size": limit,
    "from": 0,
    "includeDeleted": False,
    "fields": "columns,owners,tags,domains,dataProducts",
}
```

Structured lookup payload:

```python
{
    "query": "*",
    "entityType": entity_type,
    "size": limit,
    "from": 0,
    "includeDeleted": False,
    "queryFilter": json.dumps(open_search_query),
    "fields": "columns,owners,tags,domains,dataProducts",
}
```

Capability notes from source:

- `query` defaults to `"*"`.
- `entityType` maps to the correct OpenMetadata search index; no `entityType` searches the broader data asset index.
- `size` defaults to 10 and is capped at 50.
- `from` supports pagination.
- `includeDeleted` defaults to `false`.
- `fields` is a comma-separated list of extra fields; essential fields are always included.
- `queryFilter` is accepted as an OpenSearch JSON string and wrapped under `query` if needed.

### Field-Constrained Metadata Lookup

When the user gives an explicit field constraint, build an OpenSearch DSL `queryFilter` instead of relying only on the free-text `query` parameter.

Examples of field constraints:

```text
owned by Finance
tagged as Critical Data Element
Tier 1
column customer_id
schema customer
database analytics
service snowflake
```

Use Python dictionaries first, then serialize with `json.dumps()`.

Example:

```python
query_filter = {
    "bool": {
        "must": [
            {"term": {"entityType": "table"}},
            {"match": {"columns.name": "customer_id"}},
            {"term": {"tier.tagFQN": "Tier.Tier1"}},
        ]
    }
}

payload = {
    "query": "*",
    "entityType": "table",
    "size": limit,
    "from": 0,
    "includeDeleted": False,
    "queryFilter": json.dumps(query_filter),
    "fields": "columns,owners,tags,domains,dataProducts",
}
```

Use free-text `query` for recall when the user provides names or concepts, but use `queryFilter` for explicit field constraints.

For short name-like lookups, strip command and entity filler before calling `search_metadata`.

Example:

```text
find s18 tables -> query="s18", entityType="table"
find data quality tables -> query="data quality", entityType="table"
show dashboard sales_kpi -> query="sales_kpi", entityType="dashboard"
find pipeline daily_ingest -> query="daily_ingest", entityType="pipeline"
find kafka topic orders-v1 -> query="orders-v1", entityType="topic"
```

V1 field-constraint allowlist:

```text
columns.name
tags.tagFQN
tier.tagFQN
owners.name
service.name
database.name
databaseSchema.name
entityType
fullyQualifiedName
```

Add more fields only after testing actual examples against the platform search index.

Unsupported field constraints:

- In normal CLI output, fall back to `semantic_search` and include a short note that the structured filter could not be applied.
- In `--debug` output, show the unsupported field, intended filter, and fallback route.
- Do not silently drop a structured filter and continue as if it was applied.

### Tool 3: `get_entity_details`

Use this only after `semantic_search` or `search_metadata` returns candidate results. Do not guess the fully qualified name.

Payload:

```python
{
    "entityType": result["entityType"],
    "fqn": result["fullyQualifiedName"],
}
```

Capability notes from source:

- The tool reads `entityType` and `fqn`.
- It retrieves the entity by name with all fields, then removes verbose fields to keep the response suitable for an LLM context.
- Enrich only the top 3 candidate results by default, or 5 at most.
- The Discovery CLI should support `--enrich-limit`, defaulting to `3`, with a recommended maximum of `5`.

### Optional Tool: `get_entity_lineage`

Use lineage only when the user explicitly asks about upstream, downstream, dependency, impact, provenance, or lineage.

Payload:

```python
{
    "entityType": result["entityType"],
    "fqn": result["fullyQualifiedName"],
    "upstreamDepth": 3,
    "downstreamDepth": 3,
}
```

Capability notes from source:

- `entityType` and `fqn` are required.
- `upstreamDepth` and `downstreamDepth` default to 3.
- Depth is capped at 10 to avoid explosive lineage responses.

### Default Orchestration

Routing policy:

```text
Ambiguous intent -> semantic_search
Clear entity type plus technical clues -> search_metadata
```

Use `semantic_search` when the user's intent is broad, business-oriented, exploratory, or ambiguous.

For short lookup-style questions with no clear entity type, do not silently assume `table`. Return a clarification prompt asking which OpenMetadata entity type to search.

Prompt options should include emoji labels:

```text
📊 table
📈 dashboard
🔄 pipeline
📡 topic
🎯 metric
📚 glossaryTerm
🏷️ tag
🤖 mlmodel
🗄️ container
📦 dataProduct
```

Use `search_metadata` only when the skill has enough technical information to identify the likely entity type and lookup dimensions, such as exact names, FQN-like patterns, columns, owners, tags, tiers, services, databases, schemas, or dashboard/report/table wording.

`search_metadata` requires both:

1. An entity-type clue.
2. A metadata clue.

The `--entity-type` CLI flag supplies or overrides the entity-type clue, but it does not force `search_metadata` by itself. Intent routing still depends on whether the question has a metadata clue.

Examples:

| Question | Entity-type clue | Metadata clue | Route |
|---|---|---|---|
| `tables with customer_id` | `table` | column `customer_id` | `search_metadata` |
| `dashboards owned by Finance` | `dashboard` | owner `Finance` | `search_metadata` |
| `snowflake.analytics.finance.invoices` | inferred `table` | FQN-like pattern | `search_metadata` |
| `Tier 1 customer datasets` | `table` | tier `Tier1` | `search_metadata` |
| `customer complaints` | none | business concept only | `semantic_search` |
| `--entity-type dashboard customer complaints` | CLI flag supplies `dashboard` | business concept only | `semantic_search` |
| `--entity-type dashboard owned by Finance` | CLI flag supplies `dashboard` | owner `Finance` | `search_metadata` |

For broad discovery:

```text
clean question
-> semantic_search
-> normalize candidate results
-> get_entity_details for top 3
-> rank and format business discovery answer
```

For exact lookup:

```text
clean question
-> search_metadata
-> normalize candidate results
-> get_entity_details for top 3
-> rank and format business discovery answer
```

For semantic search failure caused by disabled vector embeddings:

```text
semantic_search
-> detect error
-> fallback to search_metadata
-> explain that semantic search was unavailable
```

---

### Exact metadata lookup behaviour

Use `search_metadata` when the user gives exact or technical clues.

Examples:

```text
Find tables with customer_id
Find table snowflake.analytics.finance.invoices
Find assets tagged as Critical Data Element
Find assets owned by Finance Team
Find dashboards with complaint in the name
Find tables in schema customer
Find Tier 1 datasets
```

Use:

```text
search_metadata
```

Then enrich top results using:

```text
get_entity_details
```

---

### Entity enrichment behaviour

Use `get_entity_details` only after a search tool returns candidate results.

Always pass:

```json
{
  "entityType": "<entityType from search result>",
  "fqn": "<fullyQualifiedName from search result>"
}
```

Do not manually construct or guess the FQN.

Use `fullyQualifiedName` returned by `semantic_search` or `search_metadata`.

---

## Semantic Search

Use `semantic_search` for meaning-based discovery.

### Basic payload

```json
{
  "query": "customer complaints service assurance",
  "size": 10
}
```

### Recommended payload

```json
{
  "query": "customer complaints service assurance",
  "filters": {
    "entityType": ["table"]
  },
  "size": 10,
  "from": 0,
  "k": 100,
  "threshold": 0.0
}
```

### Parameter guidance

| Parameter | Meaning |
|---|---|
| `query` | Natural language discovery query |
| `filters` | Optional narrowing, e.g. entity type |
| `size` | Number of results to return |
| `from` | Pagination offset |
| `k` | Vector candidate pool size |
| `threshold` | Minimum similarity score |

Recommended defaults:

```python
size = 10
from_ = 0
k = 100
threshold = 0.0
```

Use a higher threshold only when the user asks for strong or high-confidence matches.

Suggested threshold values:

```text
0.0 = exploratory
0.3 = moderate
0.5 = stronger matches
0.7 = strict
```

---

## Search Metadata

Use `search_metadata` for exact or structured metadata lookup.

### Simple payload

```json
{
  "query": "tables with customer_id",
  "entityType": "table",
  "size": 10,
  "from": 0,
  "includeDeleted": false
}
```

### Advanced `queryFilter` payload

`queryFilter` is an OpenSearch DSL JSON string.

Build it as a Python dictionary first, then serialize it using `json.dumps()`.

Do not manually escape JSON strings unless absolutely necessary.

Example Python:

```python
import json

query_filter = {
    "bool": {
        "must": [
            {"term": {"entityType": "table"}},
            {"match": {"columns.name": "customer_id"}},
            {"term": {"tier.tagFQN": "Tier.Tier1"}}
        ]
    }
}

payload = {
    "queryFilter": json.dumps(query_filter),
    "entityType": "table",
    "size": 10,
    "from": 0,
    "includeDeleted": False,
    "fields": "columns,owners,tags,domain,dataProducts"
}
```

### Important field guidance

Use:

```text
entityType
fullyQualifiedName
columns.name
tags.tagFQN
tier.tagFQN
owners.name
service.name
database.name
databaseSchema.name
```

Notes:

- Use singular `entityType`, not `entityTypes`.
- Owners are nested in the search index, so owner queries may require a nested query.
- Columns are not nested, so use `columns.name` directly.
- Tier format is usually like `Tier.Tier1`.

---

## Get Entity Details

Use `get_entity_details` to enrich search results.

Payload:

```json
{
  "entityType": "table",
  "fqn": "snowflake.analytics.finance.invoices"
}
```

Python helper:

```python
def get_entity_details(client, entity_type: str, fqn: str) -> dict:
    return client.mcp.call_tool(
        "get_entity_details",
        {
            "entityType": entity_type,
            "fqn": fqn
        }
    )
```

Do not call `get_entity_details` for too many results.

Recommended enrichment limit:

```python
max_enrichment = 3
```

or at most:

```python
max_enrichment = 5
```

---

## RDF / Knowledge Graph Optional Mode

OpenMetadata PR #28042 introduces RDF / Knowledge Graph capabilities, including:

```text
SparqlQueryTool
EntityNeighborhoodTool
FindByTagTool
OntologyDescribeTool
ShaclValidateTool
```

Treat this as an optional future capability unless the hosted environment exposes these tools.

The skill should not depend on RDF tools being available.

Add capability detection:

```python
def detect_rdf_enabled(available_tools: set[str]) -> bool:
    rdf_tool_candidates = {
        "sparql_query",
        "SparqlQueryTool",
        "entity_neighborhood",
        "EntityNeighborhoodTool",
        "find_by_tag",
        "FindByTagTool",
        "ontology_describe",
        "OntologyDescribeTool",
        "shacl_validate",
        "ShaclValidateTool",
    }

    return bool(available_tools.intersection(rdf_tool_candidates))
```

Use RDF / KG mode only for ontology-style questions.

Examples:

```text
Find assets connected to this business concept through glossary relationships
Find neighbouring entities around this dataset
Describe this ontology concept
Find related concepts broader or narrower than Service Assurance
Find shortest semantic path between two assets
Validate RDF/SHACL conformance
```

Do not use RDF as the default discovery path.

Default path remains:

```text
semantic_search / search_metadata → get_entity_details
```

---

## RDF Safety Rules

If RDF/SPARQL is enabled:

1. Prefer allowlisted SPARQL templates.
2. Do not execute arbitrary user-authored SPARQL in production.
3. Only allow read-only SPARQL.
4. Block mutation keywords:
   - `INSERT`
   - `DELETE`
   - `UPDATE`
   - `LOAD`
   - `CLEAR`
   - `CREATE`
   - `DROP`
   - `COPY`
   - `MOVE`
   - `ADD`
5. Limit result size.
6. Apply timeouts.
7. Use federation allowlists.
8. Do not expose internal RDF endpoints or credentials.

---

## Intent Router Requirements

Implement a deterministic router in Python.

The router should produce a `ToolPlan`.

Suggested model:

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ToolPlan:
    primary_tool: str
    arguments: Dict[str, Any]
    fallback_tool: Optional[str] = None
    entity_type: str = "table"
    enrich: bool = True
    reason: str = ""
```

Suggested routing:

```python
def build_tool_plan(question: str, limit: int = 10) -> ToolPlan:
    cleaned = clean_query(question)
    q = cleaned.lower()
    entity_type = infer_entity_type(q)

    if has_rdf_intent(q):
        return ToolPlan(
            primary_tool="rdf_optional",
            arguments={"query": cleaned, "limit": limit},
            entity_type=entity_type,
            enrich=False,
            reason="User asked an ontology or knowledge-graph style question."
        )

    if has_exact_metadata_clue(q):
        return ToolPlan(
            primary_tool="search_metadata",
            fallback_tool="semantic_search",
            arguments={
                "query": cleaned,
                "entityType": entity_type,
                "size": limit,
                "from": 0,
                "includeDeleted": False
            },
            entity_type=entity_type,
            enrich=True,
            reason="User provided exact or technical metadata clues."
        )

    return ToolPlan(
        primary_tool="semantic_search",
        fallback_tool="search_metadata",
        arguments={
            "query": cleaned,
            "filters": {
                "entityType": [entity_type]
            },
            "size": limit,
            "from": 0,
            "k": 100,
            "threshold": 0.0
        },
        entity_type=entity_type,
        enrich=True,
        reason="User asked a broad business discovery question."
    )
```

---

## Entity Type Inference

Infer entity type from user wording.

| User wording | Entity type |
|---|---|
| dataset, table, data product, asset | `table` |
| dashboard, report, visualisation | `dashboard` |
| pipeline, DAG, Airflow, job | `pipeline` |
| Kafka, topic, stream | `topic` |
| glossary, business term, term | `glossaryTerm` |
| metric, KPI, measure | `metric` |

Default:

```python
entity_type = "table"
```

---

## Exact Metadata Clues

Return `True` from `has_exact_metadata_clue()` if the question contains:

```text
column
owner
tag
tier
schema
database
service
table name
dashboard name
fqn
fully qualified
starburst.
snowflake.
bigquery.
postgres.
mysql.
```

Also detect technical FQN-like patterns:

```python
import re

FQN_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+){2,}\b")
```

---

## Query Cleaning

Remove command-like phrases:

```text
/discover data
discover data
find data for
find datasets for
show me
please
can you
could you
```

Example:

```text
/discover data order fulfillment
```

Becomes:

```text
customer complaints service assurance
```

---

## Fallback Behaviour

If `semantic_search` fails:

```text
fallback to search_metadata
```

If `search_metadata` fails:

```text
fallback to semantic_search
```

If `search_metadata` succeeds but returns no results for a structured filter:

```text
fallback to semantic_search
```

In the business discovery answer, preserve the distinction:

```text
No exact metadata matches were found; here are broader semantic matches.
```

If both fail:

```text
return a clear no-result/error message
```

Do not hide failures entirely. Return enough diagnostic context for a developer to debug, but do not expose secrets.

---

## Result Normalisation

Normalize tool responses into this shape:

```python
{
    "entityType": "...",
    "fullyQualifiedName": "...",
    "name": "...",
    "displayName": "...",
    "description": "...",
    "owners": [],
    "tags": [],
    "tier": None,
    "domains": [],
    "href": "...",
    "similarityScore": None,
}
```

Search tools may return slightly different shapes. The wrapper should be tolerant.

---

## Ranking Guidance

Rank higher if an asset has:

1. Higher semantic similarity score.
2. Higher trusted tier.
3. Clear owner.
4. Clear description.
5. Relevant tags or glossary terms.
6. Relevant domain.
7. Matching entity type.
8. Catalogue link.
9. Richer metadata.

Do not over-promote assets with no owner, no description, and no tags.

Tiering is a first-class ranking boost, not a hard filter. When two candidate results are otherwise similarly relevant, prefer the asset with the stronger tier signal.

Default tier order:

```text
Tier.Tier1 Tier 1 > Tier.Tier2 Tier 2 > Tier.Tier3 Tier 3 > Tier.Tier4 Tier 4 > Tier.Tier5 Tier5 > no tier
```

`--threshold` applies only to `semantic_search`. Tier ranking applies after candidate results are returned from either `semantic_search` or `search_metadata`.

The exact scoring weights are provisional for v1 and should be calibrated later against real platform datasets and user feedback.

Even when the user explicitly asks for a tier, treat tier as a ranking boost rather than an exclusion filter. Always display each recommended result's tier when available so the user can judge the trade-off.

Tier tag source of truth from the platform:

| Tag FQN | Label | Ranking meaning |
|---|---|---|
| `Tier.Tier1` | Tier 1 | Highest boost; critical source-of-truth business data assets |
| `Tier.Tier2` | Tier 2 | Important business datasets, not as critical as Tier 1 |
| `Tier.Tier3` | Tier 3 | Department or group-level datasets |
| `Tier.Tier4` | Tier 4 | Team-level, typically non-business or internal system datasets |
| `Tier.Tier5` | Tier5 | Lowest boost; private or unused assets with no impact beyond individual users |

The implementation should read tier from either a direct `tier` field or from tags containing `Tier.TierN`.

---

## Output Format

Return both structured result and formatted answer.

Structured result:

```python
{
    "question": question,
    "tool_plan": tool_plan,
    "results": normalized_results,
    "answer": formatted_answer
}
```

Formatted answer style:

```text
Found 5 candidate metadata assets for:
"customer complaints service assurance"

| Table FQN | Display Name | Tier | Domain | Owner |
| --- | --- | --- | --- | --- |
| snowflake.analytics.finance.invoice_summary | Customer Complaint Summary | Tier.Tier1 - Tier 1 | Customer | Finance Domain |
```

CLI output policy:

- Default output is the formatted business discovery answer for human reading.
- Human-readable results use a compact table view with `Table FQN`, `Display Name`, `Tier`, `Domain`, and `Owner`.
- `--json` prints the structured result for automation and debugging.
- `discover_data()` always returns the structured dictionary; CLI rendering is a presentation concern.

---

## No Result Behaviour

If no results are found:

```text
I could not find matching metadata assets for this question.

Try refining the query with:
- a business domain
- a glossary term
- a table or dashboard name
- an owner
- a known column name
- a system or service name
```

Do not invent metadata.

---

## Governance Rules

The skill is read-only.

Do not call mutation tools:

```text
patch_entity
create_lineage
create_glossary
create_glossary_term
create_test_case
create_metric
```

Do not:

1. Invent metadata.
2. Claim an asset is certified unless metadata confirms it.
3. Claim an owner exists unless metadata confirms it.
4. Expose raw tokens or credentials.
5. Connect directly to source databases.
6. Retrieve production data records.
7. Execute unrestricted SPARQL.
8. Use write tools.

Allowed default read tools:

```text
semantic_search
search_metadata
get_entity_details
```

Optional read tools:

```text
get_entity_lineage
RDF / KG read tools if available and guarded
```

---

## Lineage Disclaimer

If lineage support is added later and the user asks about column-level lineage, include:

```text
Column-level lineage may be incomplete. For full visual lineage, open the Data Catalogue UI.
```

---

## Trust / Data Quality Disclaimer

When answering whether a dataset is trusted or safe to use, avoid absolute claims unless metadata confirms certification or authoritative status.

Use:

```text
Based on the available catalogue metadata, this asset appears to be a stronger candidate because it has an owner, description, and relevant tags.
```

Avoid:

```text
This is definitely the correct source of truth.
```

---

## Suggested Implementation Tasks for GitHub Copilot

Build in this order:

1. Create project structure.
2. Add `requirements.txt`.
3. Add `.env.example`.
4. Implement `config.py`.
5. Implement `models.py`.
6. Implement `router.py`.
7. Implement `client.py`.
8. Implement `tools.py`.
9. Implement `formatter.py`.
10. Implement `scripts/discover_data.py`.
11. Add basic CLI tests.
12. Add mock tests for routing.
13. Add RDF optional detection only after core flow works.

---

## Suggested `requirements.txt`

Start minimal:

```text
python-dotenv
pydantic
requests
```

Add the official AI SDK package used in the environment, for example:

```text
data-ai-sdk
```

Confirm the exact import path from the installed package.

Do not assume the SDK import name until tested.

---

## Required CLI

`scripts/discover_data.py` should support:

```bash
python scripts/discover_data.py --question "order fulfillment" --limit 5
```

It should also support slash-style positional input:

```bash
python scripts/discover_data.py /discover data order fulfillment
```

Both forms should normalize into the same discovery question before routing.

Optional flags:

```bash
--debug
--no-enrich
--entity-type table
--threshold 0.3
--enrich-limit 3
--json
```

---

## Debug Output

If `--debug` is enabled, print:

```text
Question
Cleaned query
Selected primary tool
Fallback tool
Entity type
Payload without secrets
Result count
Enrichment count
```

Never print token values.

---

## Design Principle

The prompt guides behaviour.

The Python wrapper executes behaviour.

Do not rely on the LLM to manually craft escaped JSON, exact OpenSearch DSL strings, or SPARQL strings.

Use Python dictionaries and serializers.

The skill should be deterministic, testable, and safe by default.

---

## MVP Definition of Done

MVP is complete when:

1. User can run:
   ```bash
   python scripts/discover_data.py --question "order fulfillment"
   ```

2. The wrapper chooses `semantic_search`.

3. It calls hosted MCP through AI SDK.

4. It enriches top 3 results with `get_entity_details`.

5. It prints a clean business-friendly answer.

6. It does not require a local MCP server.

7. It does not call any write tools.

8. It does not expose secrets.

9. It handles no-result cases cleanly.

10. It has routing tests for:
    - broad discovery
    - exact FQN lookup
    - column lookup
    - dashboard discovery
    - RDF-style question detection

---

## Notes for Copilot

When generating code for this project:

- Prefer Python.
- Keep the local wrapper read-only.
- Do not create a local MCP server.
- Do not add FastAPI or server code unless explicitly requested.
- Do not hardcode secrets.
- Use environment variables.
- Keep MCP tool names configurable.
- Use capability detection for optional RDF tools.
- Keep search and RDF routing separate.
- Keep code modular and easy to test.
- Use clear error messages.
- Avoid overengineering v1.
