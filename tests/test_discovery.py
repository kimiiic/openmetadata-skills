import unittest
from unittest.mock import patch

from data_discovery.client import load_dotenv_if_available
from data_discovery.discovery import discover_data


class FakeClient:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        return ["semantic_search", "search_metadata", "get_entity_details"]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "semantic_search":
            return {
                "results": [
                    {
                        "entityType": "table",
                        "fullyQualifiedName": "svc.db.schema.customer_complaints",
                        "name": "customer_complaints",
                        "description": "Complaint events",
                        "tier": {"tagFQN": "Tier.Tier2"},
                        "owners": [{"name": "Customer Data"}],
                    }
                ]
            }
        if name == "search_metadata":
            return {"results": []}
        if name == "get_entity_details":
            return {
                "entityType": arguments["entityType"],
                "fullyQualifiedName": arguments["fqn"],
                "displayName": "Customer Complaints",
                "tier": {"tagFQN": "Tier.Tier1"},
            }
        return {}


class DiscoveryTests(unittest.TestCase):
    def test_discovers_and_enriches_top_results(self):
        client = FakeClient()
        result = discover_data("customer complaints", client=client)
        self.assertEqual(result["tool_plan"]["primary_tool"], "semantic_search")
        self.assertIn("svc.db.schema.customer_complaints", result["answer"])
        self.assertIn("Tier.Tier1", result["answer"])
        self.assertEqual([call[0] for call in client.calls], ["semantic_search", "get_entity_details"])

    def test_metadata_no_results_falls_back_to_semantic(self):
        client = FakeClient()
        result = discover_data("tables with customer_id", client=client)
        self.assertEqual(result["tool_plan"]["primary_tool"], "search_metadata")
        self.assertIn("No exact metadata matches", result["answer"])
        self.assertEqual([call[0] for call in client.calls], ["search_metadata", "semantic_search", "get_entity_details"])

    def test_loads_dotenv_without_overriding_existing_environment(self):
        with patch("dotenv.load_dotenv") as load_dotenv:
            load_dotenv_if_available()
        load_dotenv.assert_called_once_with(override=False)

    def test_answer_uses_table_view(self):
        from data_discovery.formatter import format_answer

        answer = format_answer(
            "q",
            "q",
            [
                {
                    "displayName": "Asset",
                    "entityType": "table",
                    "fullyQualifiedName": "svc.db.schema.asset",
                    "tier": {"tagFQN": "Tier.Tier1"},
                    "domains": [{"name": "Governance"}],
                    "owners": [{"name": "Data Team"}],
                }
            ],
        )
        self.assertIn("| Table FQN | Owner | Domain | Tier |", answer)
        self.assertIn("| svc.db.schema.asset | Data Team | Governance | Tier.Tier1 - Tier 1 |", answer)

    def test_tier_tag_source_of_truth_ranks_and_labels_results(self):
        from data_discovery.formatter import format_answer, rank_results

        results = [
            {"displayName": "Low", "entityType": "table", "tags": [{"tagFQN": "Tier.Tier5"}]},
            {"displayName": "High", "entityType": "table", "tags": [{"tagFQN": "Tier.Tier1"}]},
        ]

        ranked = rank_results(results)
        self.assertEqual(ranked[0]["displayName"], "High")

        answer = format_answer("q", "q", ranked)
        self.assertIn("Tier.Tier1 - Tier 1", answer)

    def test_non_tier_tags_are_not_displayed_as_tier(self):
        from data_discovery.formatter import format_answer

        answer = format_answer(
            "q",
            "q",
            [
                {
                    "displayName": "Asset",
                    "entityType": "table",
                    "tags": [{"tagFQN": "Data Classification.Confidential"}],
                }
            ],
        )
        self.assertNotIn("Tier:", answer)

    def test_ambiguous_entity_type_returns_prompt_without_client(self):
        result = discover_data("/discover data find mdu")
        self.assertEqual(result["tool_plan"]["primary_tool"], "clarify_entity_type")
        self.assertIn("📊 `table`", result["answer"])
        self.assertIn("📈 `dashboard`", result["answer"])
        self.assertIn("🏷️ `tag`", result["answer"])


if __name__ == "__main__":
    unittest.main()
