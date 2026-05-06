# RAG Retrieval Layer Design

## Scope

This design is bounded by `openspec/changes/add-rag-retrieval-layer/proposal.md` and the `conversation-retrieval` spec delta. The first implementation delivers a lightweight, traceable retrieval layer for conversation agents. It does not implement long-term memory extraction, external vector databases, document upload UI, knowledge-management APIs, frontend management screens, or turn-selection policy changes.

## Architecture

Add `backend/conversation/services/retrieval.py` as the single retrieval boundary for agent generation:

```text
facilitator_plan.retrieval_requirement
        |
        v
agent.py
        |
        v
retrieval.retrieve(query, session, user, sources, top_k)
        |
        +-- web source -> wraps existing web_search.py
        +-- session source -> searches current ConversationSession TurnRecord
        +-- knowledge source -> searches KnowledgeSnippet
        +-- memory source -> returns not-configured trace
        |
        v
RetrievedContext
        |
        +-- rendered prompt block -> agent_shared.txt
        +-- trace metadata -> persisted after TurnRecord is saved
```

`agent.py` should no longer directly branch on `wants_web_search()`. It should map facilitator retrieval intent into source sets, call `retrieve(...)`, pass `RetrievedContext.rendered_context` into prompt rendering, and persist trace metadata after the generated `TurnRecord` exists.

`web_search.py` remains responsible for the existing web search request and formatting behavior. The retrieval layer wraps it rather than rewriting it.

## Source Mapping

Use this first-version mapping:

| `retrieval_requirement` | Sources | Behavior |
| --- | --- | --- |
| `web_search` | `web`, `knowledge` | Retrieve external web context and local knowledge snippets. |
| `memory` | `memory`, `session`, `knowledge` | Return memory `not-configured`, search current session history, and search local knowledge. |
| `exemplar` | none | Record skipped status because exemplar retrieval is not in this proposal's first implementation. |
| `none` / empty | none | Return a prompt-safe no-retrieval message. |
| unsupported value | none | Record skipped status. |

This mapping avoids adding a new facilitator enum while still using the local knowledge base for factual/history-like retrieval paths.

## Data Models

Add `KnowledgeSnippet` for Django admin-managed knowledge snippets:

```python
title
content
source_uri
source_label
is_active
metadata = JSONField(default=dict, blank=True)
created_at / updated_at
```

`title` is the primary citation label. `source_uri` stores the original URL or internal identifier. `source_label` can hold a document, course, site, or collection name. `metadata` leaves room for page, section, tag, or import metadata without another migration.

Add `TurnRetrieval` to persist retrieval trace data for generated agent turns:

```python
turn = ForeignKey(TurnRecord)
query
requested_sources = JSONField
source_statuses = JSONField
items = JSONField
rendered_context = TextField
error_message = TextField(blank=True)
created_at / updated_at
```

Do not add `UserMemoryItem`, embedding/vector models, serializers, APIs, or frontend management screens in this change.

## Retrieval Behavior

`session` retrieval searches historical `TurnRecord` rows in the current `ConversationSession`. It may exclude the most recent three turn indexes because they are already part of short-term prompt history. First-version ranking can use case-insensitive keyword matching, with score based on matched term count and a small recency boost. Returned items include `speaker`, `turn_index`, `excerpt`, and provenance pointing to the turn.

`knowledge` retrieval searches active `KnowledgeSnippet` rows. First-version ranking can match query terms against `title`, `content`, and `source_label`, with title matches weighted higher. Returned items include `title`, `source_uri`, `source_label`, `excerpt`, `KnowledgeSnippet` id, and citation metadata.

`web` retrieval calls existing web search behavior and preserves disabled, empty, and failed-request fallback messages.

`memory` retrieval does not query a long-term memory model in this version. It returns `not-configured` status and does not block other sources.

Apply `top_k`, per-item excerpt limits, rendered context length limits, and user ownership checks where relevant. The first implementation uses lexical/simple scoring only; vector ranking remains a later enhancement behind the same interface.

## Prompt Formatting

`RetrievedContext` should provide a stable `rendered_context` block for `agent_shared.txt`. The block should label each result by source type and include citation/provenance fields when available. If all requested sources are empty, skipped, unavailable, or failed, the block should clearly tell the agent to continue using conversation context only and not invent retrieved facts or citations.

## Error Handling

Retrieval must not interrupt the live conversation loop. Use source statuses:

```text
success
no-results
skipped
not-configured
failed
```

One source failure must not prevent other sources from returning results. Unsupported sources are skipped. `memory` is `not-configured`. Empty `knowledge` and `session` results are `no-results`. Disabled web search is skipped or not configured. Failed web search is `failed`.

Persist source statuses and any compact error message into `TurnRetrieval`.

## Testing

Add backend tests for:

- `retrieval.py` no-retrieval, unsupported source, empty result, fallback, and rendered context behavior.
- `memory` returning `not-configured`.
- `knowledge` no-results and successful citation metadata.
- `session` retrieval finding an earlier `TurnRecord`.
- web search behavior remaining compatible with existing `test_web_search.py`.
- agent integration mapping `web_search`, `memory`, and `none` to the expected retrieval behavior.
- `TurnRetrieval` persistence after agent turn creation, including failed or skipped source statuses.

Suggested verification:

```bash
pytest backend/conversation/tests/test_retrieval.py
pytest backend/conversation/tests/test_web_search.py
pytest backend/conversation/tests/test_agent_retrieval.py
make pytest
```

If local Docker or external web search configuration is unavailable, record skipped verification. Unit tests for retrieval should not depend on external services.

## Approved First-Version Decisions

- Do not implement long-term memory models or memory extraction.
- Implement `KnowledgeSnippet` as a database model managed only through Django admin.
- Implement `TurnRetrieval` as a related trace model rather than storing trace JSON directly on `TurnRecord`.
- Use lexical/simple scoring, not embeddings or vector search.
- Keep all work inside the retrieval proposal scope.
