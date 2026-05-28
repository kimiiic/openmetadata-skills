# Entity Type Detection

Map user wording to OpenMetadata entity types. Default is `table`.

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

If the entity type is genuinely ambiguous, set `needs_clarification: true` on the IntentSpec. The CLI will prompt the user to choose from emoji-labelled options.
