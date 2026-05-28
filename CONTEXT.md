# Data Discovery Skill

This context defines the language for a Python-first skill that helps users discover governed metadata assets through a hosted OpenMetadata or Collate environment.

Implementation guidance lives in `docs/data-discovery-reference.md`.

## Language

**Data Discovery Skill**:
A reusable assistant capability that turns a user's discovery question into metadata search activity against a governed metadata catalogue.
_Avoid_: App, bot, agent, local MCP server

**Discovery Question**:
A natural-language request for data, metadata, ownership, meaning, or usefulness. A discovery question may be broad and business-oriented or narrow and technical.
_Avoid_: Query, prompt, search string

**Slash Discover**:
The user-facing invocation pattern for starting a discovery question from an assistant or IDE workflow.
_Avoid_: Slash command, command, endpoint

**Discovery CLI**:
The command-line interface a user runs to invoke the Data Discovery Skill when direct MCP tool use is not available in GitHub Copilot.
_Avoid_: Local MCP server, GitHub Copilot MCP tool call

**Hosted Metadata Environment**:
The approved OpenMetadata or Collate instance that owns the metadata catalogue and exposes metadata capabilities to the skill.
_Avoid_: Local server, local MCP server, database

**Hosted Metadata Tool**:
A callable capability exposed by the hosted metadata environment for searching, inspecting, or enriching metadata assets.
_Avoid_: Local tool, plugin, API route

**Remote MCP Endpoint**:
The hosted MCP-compatible endpoint reached through the approved Data AI SDK package. It is remote infrastructure, not a local server registered with GitHub Copilot.
_Avoid_: Local MCP server, direct Copilot MCP tool

**Metadata Asset**:
A governed catalogue object that may be discovered, inspected, and recommended, such as a table, dashboard, topic, pipeline, or data product.
_Avoid_: Dataset when the asset type is unknown, file, record

**Semantic Search**:
Discovery based on the meaning and business intent of a discovery question rather than exact field names or technical identifiers.
_Avoid_: Keyword search, fuzzy search

**Metadata Lookup**:
Discovery based on explicit technical clues such as names, identifiers, tags, owners, schemas, columns, tiers, or fully qualified names.
_Avoid_: Semantic search, exact search

**Entity Enrichment**:
Follow-up inspection of a candidate metadata asset to add details such as description, ownership, tags, columns, lineage, quality signals, or related assets.
_Avoid_: Hydration, expansion, detail fetch

**Tool Plan**:
The skill's explicit interpretation of a discovery question into intent, chosen hosted metadata tools, and payloads.
_Avoid_: Chain of thought, execution plan

**Intent Confidence**:
The skill's confidence that a discovery question contains enough technical information to choose a precise metadata lookup instead of semantic search.
_Avoid_: Certainty, model confidence

**Business Discovery Answer**:
A concise answer that explains the most relevant metadata assets in terms a business user can evaluate.
_Avoid_: Raw response, technical dump, JSON result

**Displayed Metadata Signal**:
A metadata attribute shown in the business discovery answer because it helps the user judge relevance or trust, such as tier, owner, tags, description, or catalogue link.
_Avoid_: Debug field, raw metadata

**Candidate Result**:
A metadata asset returned by an initial search step before the skill has decided whether it is relevant enough to recommend.
_Avoid_: Final result, answer

**Recommended Result**:
A metadata asset the skill presents as useful for the discovery question after search and any necessary enrichment.
_Avoid_: Candidate, hit

## Example Dialogue

Dev: "When someone types `/discover data order fulfillment`, is that a metadata lookup?"

Domain Expert: "No. That is a discovery question for semantic search because the user is describing a business need, not naming a table, tag, owner, or column."

Dev: "If they ask for `snowflake.analytics.finance.invoices`, what is that?"

Domain Expert: "That is a metadata lookup. The fully qualified name is an explicit technical clue, so the skill should find the metadata asset directly and then perform entity enrichment."

Dev: "What should the user see after enrichment?"

Domain Expert: "A business discovery answer: a short explanation of the recommended results, why they match the discovery question, and the strongest metadata signals behind the recommendation."
