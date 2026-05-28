from __future__ import annotations

import json
from typing import Any

from data_discovery.client import CollateAIClient, MetadataClient
from data_discovery.formatter import (
    _extract_ssot_table_fqn,
    format_answer,
    format_entity_type_prompt,
    merge_details,
    normalize_results,
    rank_results,
    to_jsonable,
)
from data_discovery.models import DiscoveryOptions, IntentSpec
from data_discovery.router import build_tool_plan, build_tool_plan_from_intent, semantic_fallback_arguments
from data_discovery.tools import call_planned_tool, call_tool, get_entity_details


def discover_data(
    question: str,
    limit: int = 10,
    *,
    client: MetadataClient | None = None,
    enrich: bool = True,
    enrich_limit: int = 3,
    entity_type: str | None = None,
    threshold: float = 0.0,
    debug: bool = False,
    intent: IntentSpec | None = None,
) -> dict[str, Any]:
    options = DiscoveryOptions(
        limit=limit,
        enrich=enrich,
        enrich_limit=min(max(int(enrich_limit), 0), 5),
        entity_type=entity_type,
        threshold=threshold,
        debug=debug,
    )
    if intent is not None:
        plan = build_tool_plan_from_intent(intent, limit=options.limit)
    else:
        plan = build_tool_plan(question, options)
    if plan.needs_entity_type:
        answer = format_entity_type_prompt(question, plan.cleaned_query)
        output = {
            "question": question,
            "tool_plan": {
                "primary_tool": plan.primary_tool,
                "fallback_tool": plan.fallback_tool,
                "arguments": plan.arguments,
                "entity_type": plan.entity_type,
                "reason": plan.reason,
                "query_filter": plan.query_filter,
                "needs_entity_type": True,
                "entity_type_options": plan.entity_type_options,
            },
            "results": [],
            "answer": answer,
        }
        if debug:
            output["debug"] = {
                "question": question,
                "cleaned_query": plan.cleaned_query,
                "primary_tool": plan.primary_tool,
                "reason": plan.reason,
                "entity_type_options": plan.entity_type_options,
            }
        return to_jsonable(output)

    client = client or CollateAIClient.from_env()
    notes: list[str] = []
    debug_info: dict[str, Any] = {
        "question": question,
        "cleaned_query": plan.cleaned_query,
        "primary_tool": plan.primary_tool,
        "fallback_tool": plan.fallback_tool,
        "entity_type": plan.entity_type,
        "payload": plan.arguments,
        "unsupported_constraints": plan.unsupported_constraints,
    }

    if plan.unsupported_constraints:
        notes.append("I could not apply the requested structured filter, so I searched semantically instead.")

    response = _call_with_fallback(client, plan, notes, debug_info)
    results = normalize_results(response)

    if plan.primary_tool == "search_metadata" and not results:
        notes.append("No exact metadata matches were found; here are broader semantic matches.")
        fallback_response = call_tool(client, "semantic_search", semantic_fallback_arguments(plan))
        debug_info["no_result_fallback_response"] = fallback_response
        results = normalize_results(fallback_response)

    enriched_details: list[dict[str, Any]] = []
    ssot_tables: list[dict[str, Any]] = []
    if enrich and plan.enrich:
        for result in results[: options.enrich_limit]:
            entity = result.get("entityType")
            fqn = result.get("fullyQualifiedName")
            if entity and fqn:
                try:
                    detail = get_entity_details(client, str(entity), str(fqn))
                    enriched_details.append(detail)
                except Exception as exc:
                    debug_info.setdefault("enrichment_errors", []).append(str(exc))

        # Resolve SSOT tables from enriched results (e.g. glossary terms
        # that reference their source-of-truth table).
        ssot_tables = _resolve_ssot_tables(client, enriched_details, debug_info)

    merged = merge_details(results, enriched_details)
    if ssot_tables:
        merged.extend(ssot_tables)
    ranked = rank_results(merged, plan.cleaned_query)

    # SSOT tables are always included; don't let the limit trim them out
    ssot_ranked = [r for r in ranked if r.get("_ssot_source")]
    direct_ranked = [r for r in ranked if not r.get("_ssot_source")]
    ranked = ssot_ranked + direct_ranked[: max(0, options.limit - len(ssot_ranked))]
    answer = format_answer(question, plan.cleaned_query, ranked, notes)
    debug_info["result_count"] = len(ranked)
    debug_info["enrichment_count"] = len(enriched_details)

    output = {
        "question": question,
        "tool_plan": {
            "primary_tool": plan.primary_tool,
            "fallback_tool": plan.fallback_tool,
            "arguments": plan.arguments,
            "entity_type": plan.entity_type,
            "reason": plan.reason,
            "query_filter": plan.query_filter,
        },
        "results": ranked,
        "answer": answer,
    }
    if debug:
        output["debug"] = debug_info
    return to_jsonable(output)


def _call_with_fallback(client: MetadataClient, plan: Any, notes: list[str], debug_info: dict[str, Any]) -> dict[str, Any]:
    try:
        response = call_planned_tool(client, plan)
        if _is_error_response(response) and plan.primary_tool == "semantic_search" and plan.fallback_tool:
            notes.append("Semantic search was unavailable, so I used metadata search instead.")
            fallback_args = {
                "query": plan.cleaned_query or "*",
                "entityType": plan.entity_type,
                "size": plan.arguments.get("size", 5),
                "from": 0,
                "includeDeleted": False,
                "fields": "columns,owners,tags,domains,dataProducts",
            }
            if plan.query_filter:
                fallback_args["queryFilter"] = json.dumps(plan.query_filter)
            debug_info["fallback_payload"] = fallback_args
            return call_tool(client, plan.fallback_tool, fallback_args)
        return response
    except Exception as exc:
        debug_info["primary_error"] = str(exc)
        if not plan.fallback_tool:
            raise
        notes.append(f"{plan.primary_tool} failed, so I used {plan.fallback_tool} instead.")
        if plan.fallback_tool == "semantic_search":
            fallback_args = semantic_fallback_arguments(plan)
        else:
            fallback_args = {
                "query": plan.cleaned_query or "*",
                "entityType": plan.entity_type,
                "size": plan.arguments.get("size", 5),
                "from": 0,
                "includeDeleted": False,
                "fields": "columns,owners,tags,domains,dataProducts",
            }
            if plan.query_filter:
                fallback_args["queryFilter"] = json.dumps(plan.query_filter)
        debug_info["fallback_payload"] = fallback_args
        return call_tool(client, plan.fallback_tool, fallback_args)


def _is_error_response(response: dict[str, Any]) -> bool:
    text = " ".join(str(response.get(key, "")) for key in ("error", "message")).lower()
    return "error" in response or "not enabled" in text or "failed" in text


def _resolve_ssot_tables(
    client: MetadataClient,
    enriched_details: list[dict[str, Any]],
    debug_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Follow SSOT references from enriched results to surface their source tables.

    For example, a glossary term may reference its source-of-truth table via
    the `references` field. This fetches those tables so they appear in results.
    """
    seen_fqns: set[str] = set()
    ssot_tables: list[dict[str, Any]] = []

    for detail in enriched_details:
        table_fqn = _extract_ssot_table_fqn(detail)
        if not table_fqn or table_fqn in seen_fqns:
            continue
        seen_fqns.add(table_fqn)

        glossary_fqn = detail.get("fullyQualifiedName", "")
        glossary_name = detail.get("displayName") or detail.get("name", "")

        try:
            table_detail = get_entity_details(client, "table", table_fqn)
        except Exception as exc:
            debug_info.setdefault("ssot_errors", []).append(str(exc))
            continue

        # Normalize and annotate with the glossary source
        normalized = normalize_results({"results": [table_detail]})
        if normalized:
            normalized[0]["_ssot_source"] = {
                "glossary_fqn": glossary_fqn,
                "glossary_name": glossary_name,
            }
            ssot_tables.append(normalized[0])

    debug_info["ssot_table_count"] = len(ssot_tables)
    return ssot_tables
