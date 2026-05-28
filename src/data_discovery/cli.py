from __future__ import annotations

import argparse
import json
import sys

from data_discovery import discover_data
from data_discovery.models import Constraint, IntentSpec


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover OpenMetadata / Collate metadata assets.")
    parser.add_argument("slash_question", nargs="*", help="Slash-style discovery question.")
    parser.add_argument("--question", "-q", help="Discovery question.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-enrich", action="store_true")
    parser.add_argument("--entity-type")
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--enrich-limit", type=int, default=3)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--intent", help="JSON IntentSpec for AI-driven discovery (bypasses regex router).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    question = args.question or " ".join(args.slash_question).strip()
    intent: IntentSpec | None = None

    if args.intent:
        try:
            raw = json.loads(args.intent)
            constraints = [Constraint(**c) for c in raw.get("constraints", [])]
            intent = IntentSpec(
                entity_type=raw.get("entity_type", "table"),
                constraints=constraints,
                query_text=raw.get("query_text", question),
                needs_clarification=raw.get("needs_clarification", False),
            )
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"Invalid --intent JSON: {exc}", file=sys.stderr)
            return 2

    if not question and not intent:
        print("Provide --question, --intent, or slash-style positional input.", file=sys.stderr)
        return 2

    try:
        result = discover_data(
            question or intent.query_text or "*",
            limit=args.limit,
            enrich=not args.no_enrich,
            enrich_limit=args.enrich_limit,
            entity_type=args.entity_type,
            threshold=args.threshold,
            debug=args.debug,
            intent=intent,
        )
    except Exception as exc:
        print(f"Discovery failed: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(result["answer"])
        if args.debug and "debug" in result:
            print("\nDebug")
            print(json.dumps(result["debug"], indent=2))
    return 0
