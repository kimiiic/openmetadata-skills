# IntentSpec Example Translations

How natural language maps to structured `IntentSpec`:

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
