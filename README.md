# Data Discovery Skill

Discover governed metadata assets (tables, dashboards, pipelines, topics, metrics, glossary terms, ML models) from an OpenMetadata / Collate instance. No MCP server setup required.

## Quickstart

```bash
npx skills@latest add kimiiic/openmetadata-skills --skill data-discovery
```

Restart your agent, then just ask:

```
/find tables with email column tagged as PII
/show tier 1 dashboards owned by marketing
/what glossary terms cover customer data
```

The skill activates automatically when you ask to find, search, or discover data assets.

## How it works

The skill uses a local CLI that calls the Collate Data AI SDK, which connects to your remote OpenMetadata / Collate MCP endpoint. Claude interprets your question into structured constraints, and Python maps them to OpenSearch DSL — the AI never generates raw query DSL.

```
your question → IntentSpec (Claude) → OpenSearch DSL (Python) → OpenMetadata (MCP)
```

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **OpenMetadata / Collate credentials** set as environment variables:

```bash
export AI_SDK_HOST="https://your-instance.collate.ai"
export AI_SDK_TOKEN="your-token"
```

## Usage

Once installed, the skill handles everything — just talk to your agent. You can also run the CLI directly:

```bash
# Broad semantic search
npx data-discovery-skill "order fulfillment"

# Column lookup
npx data-discovery-skill "find tables with column name work_order_id"

# Tier-filtered dashboards
npx data-discovery-skill "show tier 1 dashboards owned by marketing"

# With structured intent (JSON)
npx data-discovery-skill --intent '{"entity_type":"table","constraints":[{"field":"columns.name","operator":"match","value":"email"}]}' --limit 5
```

First run installs Python dependencies automatically via `uv`. Subsequent runs are instant.

## Local Development

```bash
git clone https://github.com/kimiiic/openmetadata-skills.git
cd openmetadata-skills
uv sync
cp .env.example .env  # set AI_SDK_HOST and AI_SDK_TOKEN

# Run via node
node bin/cli.js "find tables with customer_id"

# Or via Python directly
uv run discover-data "find tables with customer_id"
```

## Tests

```bash
uv run python -m unittest discover -s tests
```
