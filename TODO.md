# TODOs (parallelizable workstreams)

This file is derived from the current codebase state (not just the spec). It is structured so multiple developers can work in parallel with minimal file overlap.

**Recently landed (git history, highest level)**: `ConversationLLMPrompt` + admin + `init_llm_seed` prompt seeding; **user speech-act classification** in `turn_processor` (DB prompt key `speech_act_classify`); related updates to `consumers` / turn append path.

## Current baseline (what already exists)

- **Turn loop (v1)**: `backend/conversation/consumers.py` runs a `while True` loop that calls `decide_next_speaker()` and then appends turns via `append_turn()` (plus makeshift invites). It also handles `pause/resume/end_session`, `raise_hand`, and “user speaks first” selection.
- **Turn Manager (v1)**: `backend/conversation/services/turn_manager.py` implements a simple policy based on flags like `pending_forced_user_turn`, `user_override_requested`, and periodic invites.
- **Facilitator + Agent generation (v1)**: `facilitator.py` and `agent.py` load templates via `get_prompt_pair()` from the **`ConversationLLMPrompt`** model (defaults in `backend/conversation/data/conversation_llm_prompts.txt`, upserted by `python manage.py init_llm_seed`). LangChain `SystemMessage` / `HumanMessage` are built from those templates.
- **User speech-act classification (v1)**: `append_user_turn_classified()` in `backend/conversation/services/turn_processor.py` calls an LLM using the `speech_act_classify` prompt key, then `coerce_speech_act_plan()` (shared with the facilitator) before persisting `TurnRecord.speech_act` / `subtype` / `target`. The WebSocket `user_turn` handler uses this path and can pass optional `audio_url` (classifier still works on the **transcript** in `utterance`).
- **Storage**: `ConversationSession`, `AgentProfile`, `TurnRecord`, and **`ConversationLLMPrompt`** (with Django admin) exist in `backend/conversation/models.py`.
- **TTS/STT**:
  - **TTS**: `backend/conversation/services/tts.py` uses OpenAI TTS, stores audio in `MEDIA_ROOT`, returns a public URL. `AgentProfile.voice` is used (default `"alloy"` when empty).
  - **STT**: `backend/conversation/services/stt.py` + `backend/conversation/api_views.py` implement `/conversation/stt/` (multipart `audio` upload) using OpenAI Whisper.
- **Frontend**: Vue app includes `ConversationView.vue` (WebSocket turns + mic recording + STT + playback) and `ProfileView.vue` (CEFR level + OCEAN self-evaluation saved via `AuthService.updateUser()` into `UserProfile`).

---

## Workstream A — Turn Manager 2.0 (who speaks next)

**Owner**: Backend dev (turn-taking / policy)  
**Primary files**: `backend/conversation/services/turn_manager.py`, `backend/conversation/models.py`, `backend/conversation/tests/*`  
**Avoids overlap with**: prompt refactors (Workstream C), TTS work (Workstream D), UI polish (Workstream E)

### Baseline note

- User `TurnRecord` rows now store **LLM-classified** `speech_act` / `subtype` / `target` (see `append_user_turn_classified`). **`decide_next_speaker()` in v1 still does not** use that metadata; this workstream is to wire policy to those fields (and agent/makeshift targets) when choosing the next speaker.

### What’s needed

- **Spec-aligned next-speaker selection** beyond the current v1 policy:
  - Use `TurnRecord.speech_act`, `subtype`, and `target` to select the next speaker.
  - If `target` is a specific agent id, prioritize that agent.
  - If `target == "user"` and user did not volunteer, route through **makeshift invitation** (existing pattern) and set `pending_forced_user_turn=True`.
  - If `target == "everyone"` (or empty/unknown), apply fallback rules (least-recent speaker, balance participation, or trait-based tie-breakers).
- **First-turn logic consolidation**:
  - Today: “user speaks first?” is handled in the WebSocket consumer (`first_turn_choice`).
  - Needed: consolidate “first turn” behavior into a reusable component/service so it can be tested and reused by other entrypoints (API/CLI future).
- **Override semantics**:
  - Today: `user_override_requested` always routes to `makeshift`.
  - Needed: define and implement clear priority order among: termination, pause, forced user turn, override request, facilitator-targeted next speaker, fairness rules.
- **Better test coverage**:
  - Expand from `backend/conversation/tests/test_turn_engine.py` to cover targeted turns, “everyone” fallback, fairness, and override interactions.

### Acceptance criteria

- **Deterministic rules**: Given the same session state + last turns, `decide_next_speaker()` returns the same decision.
- **Coverage**: New tests cover at least:
  - targeted agent selection
  - targeted user selection via makeshift invitation flow
  - “everyone” fallback
  - override flag priority
- **Minimal coupling**: No prompt strings in the turn manager; it should only look at normalized session + turn metadata.

---

## Workstream B — Control flow management between Facilitator and Agents

**Owner**: Backend dev (orchestration / engine)  
**Primary files**: `backend/conversation/consumers.py`, new `backend/conversation/services/*engine*.py` (or similar), `backend/conversation/services/turn_processor.py`  
**Avoids overlap with**: Workstream C (classifier + agent/facilitator already use `get_prompt_pair`); this stream is about **control flow**, not prompt content.

### What’s needed

**Partial today**: `turn_processor` handles persistence, flags, and **user speech-act classification** before append; the consumer still owns the main loop.

Right now the WebSocket consumer (`ConversationConsumer._advance_loop`) owns most of the orchestration and mixes concerns:
- selecting next speaker
- picking agent
- calling facilitator
- calling agent
- calling TTS
- appending turns
- emitting UI events

Implement a **single orchestration layer** with explicit phases so control flow is predictable and easier to extend.

Recommended shape (implementation detail, not required):
- `ConversationEngine.advance(session_id, events_sink)` or `step(session) -> EngineStepResult`

Core improvements:
- **Phase separation**
  - **Turn selection** (Turn Manager decision)
  - **Planning** (Facilitator)
  - **Generation** (Agent)
  - **Post-processing** (Turn Processor)
  - **Audio** (TTS) as a separate, optionally async step
- **Explicit error handling**
  - If facilitator JSON parsing fails (currently coerced), emit an engine event and continue with a safe default.
  - If agent generation fails, append a recoverable “system” or “makeshift” turn (policy decision) and continue.
  - If TTS fails, still append the text turn and mark audio missing (already partially done).
- **Replayability**
  - Ability to re-run a step without double-appending a turn (idempotency guard).
- **WebSocket consumer becomes “thin”**
  - Consumer only handles transport + authentication + calling engine.

### Acceptance criteria

- **`ConversationConsumer._advance_loop` shrinks** to: load session, call engine step(s), send events.
- **Unit-testable engine** without WebSocket infrastructure.
- **No regressions**: pause/resume/end_session/raise_hand still work.

---

## Workstream C — Prompt management per agent (DB-backed, not hard-coded)

**Owner**: Backend dev (models + prompt templating)  
**Primary files**: `backend/conversation/models.py` (`ConversationLLMPrompt`), `backend/conversation/prompts.py`, `backend/conversation/data/conversation_llm_prompts.txt`, `backend/llm_caller/management/commands/init_llm_seed.py`, `backend/conversation/admin.py`  
**Avoids overlap with**: UI (Workstream E) except admin

### What’s already implemented (as of recent commits)

- **`ConversationLLMPrompt`** model: `key` (slug), `system_template`, `user_template`; registered in Django admin; bundled defaults seed from **`conversation_llm_prompts.txt`** (blocks `--- <key> ---` with `[SYSTEM]` / `[USER]`), upserted when running **`init_llm_seed`**.
- **Keys in use** (all loadable via `get_prompt_pair` / `seed_conversation_llm_prompts`):
  - **`agent_utterance`**: str.format in `agent.py` (`topic`, `agent_id`, `persona`, `traits`, `facilitator_plan`, `context`).
  - **`facilitator_plan`**: empty `[USER]` in file → JSON human payload at runtime in `facilitator.py`.
  - **`speech_act_classify`**: empty `[USER]` in file → JSON human (topic, utterance, `source` / `audio_url`, `previous_speaker`, `recent_turns`) in `turn_processor.py`.
- **Fallback if DB is empty** (e.g. tests, fresh checkout): `get_prompt_pair` falls back to the same bundled `.txt` file.

### What’s still needed

- **Makeshift / system strings**: `backend/conversation/services/makeshift.py` still builds the invite string in code. Move to a new prompt key (e.g. `makeshift_invite`) in `ConversationLLMPrompt` + `conversation_llm_prompts.txt` and `init_llm_seed` upsert.
- **Per-agent or per-user prompt overrides** (optional): today one shared `agent_utterance` for all agents; add override rules or extra keys if product requires distinct personas in DB.
- **Versioning / activation**: single active row per `key` today; consider history, draft vs production, or environment-specific keys if ops need it.
- **Demo / user-specific branching (optional)**: `UserProfile.is_demo_account` exists; prompt selection could branch on it once requirements are clear.

### Acceptance criteria (updated)

- [x] **DB model + admin** for conversation LLM prompt templates.  
- [x] **Facilitator, agent, and user speech-act classifier** prompts are driven by `ConversationLLMPrompt` (with file fallback), not string literals in service code.  
- [x] **Seeding** via `init_llm_seed` (or make target `init-llm-*`) updates bundled prompt text in DB.  
- [ ] **Makeshift invite** (and any other remaining literals) move to the same system.  
- [ ] **Optional**: per-agent overrides, versioning, demo-specific prompts.

---

## Workstream D — Text-to-speech improvements (voice consistency + quality)

**Owner**: Backend dev (audio + storage)  
**Primary files**: `backend/conversation/services/tts.py`, `backend/conversation/models.py`, Vue playback in `ConversationView.vue`  
**Avoids overlap with**: turn policy (Workstream A)

### What’s needed

Current TTS behavior:
- Called during agent turn append in `consumers.py`
- Uses OpenAI TTS with `voice=agent.voice or "alloy"`
- Stores a new file each time; no caching/dedup; no per-user voice preferences

Improve to handle:
- **Voice consistency**
  - Ensure each agent has a stable voice across sessions (not just within a session).
  - Add a clear mapping: agent role/id → voice, persisted.
    - Today voice is per `AgentProfile` (per session). Consider adding a “global agent voice preset” model or a per-user preference that seeds new sessions.
- **Audio generation policy**
  - Decide whether to always generate audio, or only for agent turns, or only when UI requests it.
  - Optionally generate audio asynchronously (so UI gets text immediately, audio later).
- **Caching**
  - Avoid re-generating audio when the exact same `(model, voice, text)` occurs (hash-based storage key).
- **Operational hardening**
  - Better error messages for missing API key (currently raises).
  - Size limits and text normalization (trim, max chars).

### Acceptance criteria

- **Stable voice mapping**: agents do not “randomly” change voices between turns/sessions.
- **Non-blocking UX (if implemented)**: agent text appears even if TTS is slow.
- **Storage discipline**: caching prevents obvious duplication.

---

## Workstream E — UI/UX improvements (Conversation + states)

**Owner**: Frontend dev (Vue)  
**Primary files**: `vue_frontend/src/views/ConversationView.vue`, `vue_frontend/src/services/*`  
**Avoids overlap with**: backend orchestration (Workstream B) by relying on emitted WS events

### What’s needed

Current UI is functional but minimal:
- can start session, choose who speaks first
- mic recording → STT → send user turn
- plays audio when `audio_url` arrives
- shows basic status (“Agent thinking…”, “Your turn”, “Paused”)

Improve:
- **Conversation timeline UX**
  - Visually distinguish user vs agents vs makeshift turns (badges, colors, alignment).
  - Show facilitator metadata (optional): speech act, subtype, target, source.
  - Auto-scroll behavior with a “jump to bottom” affordance.
- **Agent speaking/thinking states**
  - Today: generic `agent_status`.
  - Needed: show which agent is speaking (speaker id) and whether it’s “thinking” vs “speaking” vs “finished”.
  - If backend adds async TTS: show “audio pending” state.
- **Audio controls**
  - Per-turn play/pause; avoid overlapping playback; show progress.
  - Global “mute auto-play” toggle (because `new Audio(...).play()` happens automatically today).
- **Mic UX**
  - Better error states and permission guidance.
  - Show audio level / recording timer (optional).

### Acceptance criteria

- **Clarity**: user can always tell whose turn it is and what’s happening.
- **No audio chaos**: autoplay is controllable and multiple audios don’t stack.

---

## Workstream F — Profile setup BEFORE conversation (audio samples for CEFR + voice selection)

**Owner**: Full-stack dev (frontend + backend)  
**Primary files**: `vue_frontend/src/views/ProfileView.vue`, `backend/users/models.py`, new backend endpoints for “audio samples”, possibly `backend/conversation/services/tts.py`  
**Avoids overlap with**: prompt mgmt (Workstream C) unless you want prompt-driven sample text

### What’s needed

Spec calls for CEFR selection via **audio comprehension samples**, but today:
- `ProfileView.vue` only lets users pick a CEFR level from a dropdown.
- `UserProfile` stores `ocean` + `cefr_level` but no “profile completed” flag, no audio sample selection, no voice preference.

Implement onboarding flow:
- **Generate CEFR audio samples** the user can listen to and select from.
  - Option A (fast): predefined short scripts per CEFR level stored in DB/static, with audio generated via TTS.
  - Option B (better): generate samples based on current conversation topic, then TTS them.
- **Persist choice**
  - Store selected CEFR level (already exists) AND optionally which sample was chosen.
- **Voice preference**
  - Let user choose a preferred voice style, which can seed agent voices or user playback voice settings.
  - Store on `UserProfile` (new fields) and use when creating `AgentProfile` rows in `ConversationConsumer._create_session()`.
- **Profile completion gate**
  - Add a “profile is complete” concept; conversation start should require it.

### Acceptance criteria

- A first-time user is **guided** through OCEAN + CEFR audio sample listening before starting a conversation.
- Chosen settings persist and affect later sessions (e.g., voice defaults, CEFR level).

---

## Workstream G — Memory management (short-term + long-term, cross-session)

**Owner**: Backend dev (data + retrieval primitives)  
**Primary files**: `backend/conversation/services/memory.py`, `backend/conversation/models.py`, new Django models/migrations, `backend/conversation/services/*`  
**Avoids overlap with**: UI work (Workstream E) by exposing memory via stable service APIs

### What’s needed

Right now “memory” is only:
- **short-term**: `get_short_term_turns()` reads recent `TurnRecord`s from the DB
- **message adaptation**: `turns_to_messages()` converts turns into `{role, content}` for prompt builders

Add a real memory subsystem that supports:
- **Short-term memory (within-session)**
  - Keep current behavior, but add utilities to:
    - summarize/compact history when it grows
    - select salient turns (not just “last N”)
    - explicitly include facilitator metadata when useful (`speech_act`, `subtype`, `target`)
- **Long-term memory (cross-session per user)**
  - Extract “important facts” about the user and ongoing preferences from conversations (e.g., goals, constraints, recurring topics, language mistakes, preferences).
  - Store these as structured items linked to `User` (not just the session) so later conversations can use them.
  - Support “write policies” so we don’t store everything (avoid noise and sensitive data).

Recommended model shape (implementation detail, not required):
- `UserMemoryItem(user, kind, content, source_session, created_at, confidence, last_seen_at, is_active)`
- optionally `UserMemoryFact(key, value, provenance, updated_at)` for stable profile-like facts

Operational requirements:
- **Privacy & retention controls**
  - allow soft-delete / disable of memory items
  - avoid storing raw transcripts unnecessarily; store normalized facts + provenance pointers
- **Memory extraction pipeline**
  - Run after each turn or after each session ends (choose one).
  - Use an LLM extraction prompt (ties into Workstream C prompt storage) with strict JSON output.

### Acceptance criteria

- **Cross-session recall**: starting a new `ConversationSession` can fetch a compact “user memory brief” from long-term memory and include it in agent/facilitator context.
- **Noise control**: memory writes are bounded and deduplicated (same fact doesn’t get stored repeatedly).
- **Admin/debug visibility**: memory items are inspectable (admin page or simple API) for development and auditing.

---

## Workstream H — Retrieval / RAG-like features (memory + optional internet search)

**Owner**: Backend dev (retrieval + tools) with optional frontend support  
**Primary files**: new `backend/conversation/services/retrieval.py` (or similar), `backend/conversation/services/agent.py`, `backend/conversation/services/facilitator.py`, new models for embeddings/index (optional)

### What’s needed

Add a retrieval layer that agents can call to answer questions using:
- **Memory retrieval**
  - Query long-term user memory (Workstream G) for relevant facts.
  - Query current session turns for relevant snippets (semantic search over turns, not only last-N).
- **Knowledge retrieval (RAG)**
  - Optional: embed documents/turns/memory items and do vector search.
  - Provide citations back to the agent prompt (“use these retrieved snippets”).
- **Internet retrieval (tool-like)**
  - Optional: allow an agent to request web lookup for current facts.
  - Put guardrails: allowlist domains or safe-search; rate limits; store retrieved pages/snippets with provenance.

Implementation requirements:
- **Clear interface**
  - `retrieve(query, *, session, user, sources={memory, session, web}, top_k=...) -> RetrievedContext`
- **Prompt integration**
  - Update agent generation so it can:
    - decide when retrieval is needed (can be facilitator-driven via `retrieval_requirement` which already exists in `build_facilitator_plan`)
    - inject retrieved snippets into the system/human messages in a consistent format
- **Traceability**
  - Store what was retrieved for each turn (e.g., in `TurnRecord` metadata or a new `TurnRetrieval` model) so debugging is possible.

### Acceptance criteria

- **Memory RAG works**: agent can answer “What did I say about X last week?” by retrieving long-term memory items and summarizing them.
- **Session semantic search works**: agent can refer back to earlier parts of the current conversation even if they’re outside the short-term window.
- **(If web enabled)**: retrieval results include provenance and are rate-limited; failures degrade gracefully (agent continues without web context).

---

## Cross-cutting cleanup (small, low-risk)

These are optional but recommended and can be picked up by any dev when idle:

- **Move hard-coded agent creation out of `ConversationConsumer._create_session()`**:
  - Today it creates 3 agents with fixed personalities/traits. Extract into a service like `services/agent_factory.py` so it can incorporate `UserProfile` fields later.
- **Expose more structured WS events**
  - e.g. include `agent_id` in `agent_status`, or a dedicated `audio_ready` event if TTS becomes async.
- **Add migrations/tests around new models**
  - Keep migrations small per workstream to reduce merge conflicts.

