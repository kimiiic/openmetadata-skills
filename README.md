# Data Discovery Skill

Discover governed metadata assets from an OpenMetadata / Collate instance via npx. No MCP server setup required.

## Quick Start

```bash
npx data-discovery-skill "find tables with email column" --limit 5
```

First run installs Python dependencies automatically via `uv`. Subsequent runs are instant.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- OpenMetadata / Collate credentials set as environment variables:
  ```bash
  export AI_SDK_HOST="https://your-instance.collate.ai"
  export AI_SDK_TOKEN="your-token"
  ```

## Usage

```bash
# Broad semantic search
npx data-discovery-skill "order fulfillment"

# Column lookup
npx data-discovery-skill "find tables with column name work_order_id"

# Tier-filtered dashboards
npx data-discovery-skill "show tier 1 dashboards owned by marketing"

# Data product filter
npx data-discovery-skill "tables that have a data product"
```

`npx disover-data-skill` is also available as an alias.

## Local Development

```bash
git clone <repo-url>
cd collate-skills
uv sync
cp .env.example .env  # set AI_SDK_HOST and AI_SDK_TOKEN

# Run directly via node (no npm publish needed)
node bin/cli.js "find tables with customer_id"

# Or via Python directly
uv run discover-data "find tables with customer_id"
```

## Tests

```bash
uv run python -m unittest discover -s tests
```
