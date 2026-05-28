# Constraint Field Schema

Use ONLY these fields and operators when building constraints for `IntentSpec`. Claude produces `Constraint` objects; Python maps them to OpenSearch DSL.

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

## Supported operators

- **`exists`** — field has a non-null value (value must be `null`/omitted)
- **`eq`** — exact term match
- **`match`** — text match (partial/fuzzy)
- **`prefix`** — prefix match

## Important rules

- **Never generate raw OpenSearch DSL.** Claude outputs `IntentSpec` (field + operator + value). Python maps to DSL.
- Only use fields from this schema. If a constraint doesn't map to any field, use semantic_search instead.
- All constraints in the list are ANDed together.
- Set `query_text` to any free-text part of the question that isn't captured by structured constraints (e.g. for "find customer tables with email column", `query_text` might be "customer").
- Column constraints (`columns.name`) are routed through the `query` parameter as `columns.name:<value>` syntax, not through `queryFilter`. The remote tool discards column-level queryFilter clauses.
