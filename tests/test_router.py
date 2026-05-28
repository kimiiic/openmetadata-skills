import json
import unittest

from data_discovery.models import Constraint, DiscoveryOptions, IntentSpec
from data_discovery.router import build_tool_plan, build_tool_plan_from_intent, clean_query


class RouterTests(unittest.TestCase):
    def test_cleans_slash_discover(self):
        self.assertEqual(clean_query("/discover data customer complaints"), "customer complaints")

    def test_broad_discovery_uses_semantic_search(self):
        plan = build_tool_plan("/discover data customer complaints for service assurance")
        self.assertEqual(plan.primary_tool, "semantic_search")
        self.assertEqual(plan.arguments["filters"]["entityType"], ["table"])

    def test_column_lookup_uses_search_metadata(self):
        plan = build_tool_plan("Find tables with customer_id")
        self.assertEqual(plan.primary_tool, "search_metadata")
        # Column constraints are routed through `query`, not `queryFilter`.
        self.assertIn("columns.name:customer_id", plan.arguments["query"])

    def test_dashboard_owner_lookup_uses_search_metadata_with_entity_override(self):
        options = DiscoveryOptions(entity_type="dashboard")
        plan = build_tool_plan("owned by Finance", options)
        self.assertEqual(plan.primary_tool, "search_metadata")
        self.assertEqual(plan.entity_type, "dashboard")

    def test_entity_type_override_does_not_force_metadata_search(self):
        options = DiscoveryOptions(entity_type="dashboard")
        plan = build_tool_plan("customer complaints", options)
        self.assertEqual(plan.primary_tool, "semantic_search")
        self.assertEqual(plan.arguments["filters"]["entityType"], ["dashboard"])

    def test_fqn_routes_to_search_metadata(self):
        plan = build_tool_plan("snowflake.analytics.finance.invoices")
        self.assertEqual(plan.primary_tool, "search_metadata")

    def test_short_technical_table_name_routes_to_search_metadata(self):
        plan = build_tool_plan("find s18 tables")
        self.assertEqual(plan.primary_tool, "search_metadata")
        self.assertEqual(plan.entity_type, "table")
        self.assertEqual(plan.arguments["query"], "s18")

    def test_strips_entity_words_for_name_lookup_variants(self):
        cases = [
            ("find s18 tables", "table", "s18"),
            ("show dashboard sales_kpi", "dashboard", "sales_kpi"),
            ("find pipeline daily_ingest", "pipeline", "daily_ingest"),
            ("find kafka topic orders-v1", "topic", "orders-v1"),
            ("find metric nps_30d", "metric", "nps_30d"),
            ("find glossary term service_assurance", "glossaryTerm", "service_assurance"),
            ("find table named customer_360", "table", "customer_360"),
            ("find data product dp_network", "table", "dp_network"),
        ]
        for question, entity_type, expected_query in cases:
            with self.subTest(question=question):
                plan = build_tool_plan(question)
                self.assertEqual(plan.primary_tool, "search_metadata")
                self.assertEqual(plan.entity_type, entity_type)
                self.assertEqual(plan.arguments["query"], expected_query)

    def test_entity_type_override_strips_entity_words(self):
        options = DiscoveryOptions(entity_type="dashboard")
        plan = build_tool_plan("find revenue_2024 dashboards", options)
        self.assertEqual(plan.primary_tool, "search_metadata")
        self.assertEqual(plan.entity_type, "dashboard")
        self.assertEqual(plan.arguments["query"], "revenue_2024")

    def test_ambiguous_short_lookup_prompts_for_entity_type(self):
        plan = build_tool_plan("/discover data find mdu")
        self.assertEqual(plan.primary_tool, "clarify_entity_type")
        self.assertTrue(plan.needs_entity_type)
        self.assertIn({"entityType": "table", "label": "Table", "emoji": "📊"}, plan.entity_type_options)
        self.assertIn({"entityType": "tag", "label": "Tag / classification", "emoji": "🏷️"}, plan.entity_type_options)

    def test_entity_type_answer_routes_short_lookup_to_search_metadata(self):
        options = DiscoveryOptions(entity_type="table")
        plan = build_tool_plan("find mdu", options)
        self.assertEqual(plan.primary_tool, "search_metadata")
        self.assertEqual(plan.arguments["query"], "mdu")

    def test_preserves_data_quality_phrase_for_table_lookup(self):
        plan = build_tool_plan("find data quality tables")
        self.assertEqual(plan.primary_tool, "search_metadata")
        self.assertEqual(plan.arguments["query"], "data quality")

    def test_data_product_filter_routes_to_search_metadata(self):
        plan = build_tool_plan("tables in data product Field Work 360")
        self.assertEqual(plan.primary_tool, "search_metadata")
        query_filter = json.loads(plan.arguments["queryFilter"])
        self.assertIn({"match": {"dataProducts.name": "Field Work 360"}}, query_filter["bool"]["must"])

    def test_dp_prefix_routes_to_search_metadata(self):
        plan = build_tool_plan("tables in dp_field_work_360")
        self.assertEqual(plan.primary_tool, "search_metadata")
        query_filter = json.loads(plan.arguments["queryFilter"])
        self.assertIn({"match": {"dataProducts.name": "field_work_360"}}, query_filter["bool"]["must"])

    def test_belongs_to_data_product_phrase(self):
        plan = build_tool_plan("tables belonging to data product Customer 360")
        self.assertEqual(plan.primary_tool, "search_metadata")
        query_filter = json.loads(plan.arguments["queryFilter"])
        self.assertIn({"match": {"dataProducts.name": "Customer 360"}}, query_filter["bool"]["must"])

    def test_any_data_product_filter_uses_exists_query(self):
        plan = build_tool_plan("tables in any data product")
        self.assertEqual(plan.primary_tool, "search_metadata")
        query_filter = json.loads(plan.arguments["queryFilter"])
        self.assertIn({"exists": {"field": "dataProducts.name"}}, query_filter["bool"]["must"])


class IntentRouterTests(unittest.TestCase):
    """Tests for AI-powered intent extraction -> ToolPlan."""

    def test_exists_constraint_builds_correct_query_filter(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="dataProducts.name", operator="exists")],
        )
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "search_metadata")
        self.assertEqual(plan.entity_type, "table")
        query_filter = json.loads(plan.arguments["queryFilter"])
        must = query_filter["bool"]["must"]
        self.assertIn({"term": {"entityType": "table"}}, must)
        self.assertIn({"exists": {"field": "dataProducts.name"}}, must)

    def test_eq_constraint_builds_term_query(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="tier.tagFQN", operator="eq", value="Tier.Tier1")],
        )
        plan = build_tool_plan_from_intent(intent)
        query_filter = json.loads(plan.arguments["queryFilter"])
        self.assertIn({"term": {"tier.tagFQN": "Tier.Tier1"}}, query_filter["bool"]["must"])

    def test_match_constraint_builds_match_query(self):
        intent = IntentSpec(
            entity_type="dashboard",
            constraints=[Constraint(field="owners.name", operator="match", value="marketing")],
        )
        plan = build_tool_plan_from_intent(intent)
        query_filter = json.loads(plan.arguments["queryFilter"])
        must = query_filter["bool"]["must"]
        self.assertIn({"term": {"entityType": "dashboard"}}, must)
        self.assertIn({"match": {"owners.name": "marketing"}}, must)

    def test_prefix_constraint_builds_prefix_query(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="service.name", operator="prefix", value="star")],
        )
        plan = build_tool_plan_from_intent(intent)
        query_filter = json.loads(plan.arguments["queryFilter"])
        self.assertIn({"prefix": {"service.name": "star"}}, query_filter["bool"]["must"])

    def test_multiple_constraints_all_in_must(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[
                Constraint(field="dataProducts.name", operator="exists"),
                Constraint(field="tier.tagFQN", operator="eq", value="Tier.Tier1"),
                Constraint(field="columns.name", operator="match", value="email"),
            ],
        )
        plan = build_tool_plan_from_intent(intent)
        # Column constraint goes into `query`, not `queryFilter`.
        self.assertIn("columns.name:email", plan.arguments["query"])
        query_filter = json.loads(plan.arguments["queryFilter"])
        must = query_filter["bool"]["must"]
        self.assertEqual(len(must), 3)  # entityType term + 2 non-column constraints
        self.assertIn({"exists": {"field": "dataProducts.name"}}, must)
        self.assertIn({"term": {"tier.tagFQN": "Tier.Tier1"}}, must)

    def test_no_constraints_falls_back_to_semantic_search(self):
        intent = IntentSpec(entity_type="table", constraints=[])
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "semantic_search")

    def test_needs_clarification_returns_prompt(self):
        intent = IntentSpec(needs_clarification=True)
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "clarify_entity_type")
        self.assertTrue(plan.needs_entity_type)

    def test_unsupported_field_falls_back_to_semantic(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="made.up.field", operator="exists")],
        )
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "semantic_search")
        self.assertIn("made.up.field", plan.unsupported_constraints[0])

    def test_unsupported_operator_falls_back_to_semantic(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="dataProducts.name", operator="gte", value="5")],
        )
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "semantic_search")

    def test_missing_value_for_non_exists_falls_back(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="tier.tagFQN", operator="eq", value=None)],
        )
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "semantic_search")

    def test_query_text_embedded_in_query_filter(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="dataProducts.name", operator="exists")],
            query_text="customer",
        )
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.primary_tool, "search_metadata")
        # query is "*" because text search is embedded in queryFilter.should
        self.assertEqual(plan.arguments["query"], "*")
        self.assertIn("queryFilter", plan.arguments)
        qf = json.loads(plan.arguments["queryFilter"])
        self.assertIn("should", qf["bool"])

    def test_defaults_query_to_star_when_empty(self):
        intent = IntentSpec(
            entity_type="table",
            constraints=[Constraint(field="dataProducts.name", operator="exists")],
        )
        plan = build_tool_plan_from_intent(intent)
        self.assertEqual(plan.arguments["query"], "*")


if __name__ == "__main__":
    unittest.main()
