# 🧞 Calendar-Genie
Calendar-Genie is an AI-powered meeting preparation and chat assistant that combines local meeting data, a local RAG corpus, and LLM reasoning to answer questions, prepare meeting summaries, and schedule meetings via a conversational interface.
**Quick links**
- Server: `server.py`
- Agents: `agents/` (`smart_fetcher.py`, `scheduler_agent.py`, `conversation_agent.py`, `answer_synthesizer.py`)
- Meetings data: `meeting.json` (hot-reloadable)
- RAG docs: `meetings_bundle/`

**Short summary**
- Hot-reloads `meeting.json` so the LLM always sees the latest meeting state.
- SmartFetcherAgent implements a ReAct-style retrieval pipeline (Plan → Execute → Reflect) and returns an execution trace for debugging.
- SchedulerAgent is an agentic, multi-phase scheduler (Analyze → Check → Gather → Confirm → Commit) with conflict detection, organizer-aware messages, and replacement flow support.
- Primary LLM: OpenRouter (Claude family) when `OPENROUTER_API_KEY` is provided; agents degrade gracefully to heuristics/stubs for offline testing.
- TTS: ElevenLabs (primary) with a browser Web Speech fallback if ElevenLabs is unavailable.

**Environment**
Create a `.env` at repo root with the relevant keys. Minimal for development:

```
OPENROUTER_API_KEY=your_openrouter_key
MOCK_AUTH=true
# Optional for TTS
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run server in mock mode (dev):

```bash
export MOCK_AUTH=true
MOCK_AUTH=true python3 -u server.py 2>&1 | tee /tmp/server.log
```

Run scheduler tests:

```bash
python3 test_scheduler.py
```

**Architecture (high level)**

- Frontend: `index.html` + `static/*` — a minimal SPA providing chat and meeting prep UI.
- Backend: `server.py` (FastAPI) — session management (mock or real OAuth), chat endpoint, prep endpoints, and orchestration.
- Agents:
	- `ConversationAnalysisAgent`: decides intent and what information is needed.
	- `SmartFetcherAgent`: ReAct retrieval pipeline over `meeting.json` and RAG docs.
	- `SchedulerAgent`: multi-phase scheduling agent with confirmation and commit.
- RAG: Vector search via `llama_index` (if available) with HuggingFace embeddings; token-based paragraph scoring fallback if vector index or embeddings are missing.
- TTS: ElevenLabs API used to return base64 audio URLs; browser Web Speech used as a fallback.

**SmartFetcherAgent (summary)**

- Pattern: ReAct — Planning (LLM-based or heuristic), Execution (meetings + RAG tools), Reflection (quality checks and refinement).
- Keeps `query_history`, `current_plan`, and `execution_trace` for explainability and tuning.
- Parameterized retrieval: `_fetch_from_meetings(query, limit=...)`, `_fetch_from_rag(query, top_k=..., threshold=...)` so the agent can adapt retrieval granularity per query.
- Fallbacks: heuristic planning and lower RAG thresholds when vector/embedding calls fail.

**SchedulerAgent (summary)**

- Phases:
	1. Analyze: detect scheduling intent and extract a time slot.
	2. Check: conflict detection against `meeting.json` (with organizer-aware messaging).
	3. Gather: infer missing fields via LLM (title, duration, participants, location) or use sensible defaults.
	4. Confirm: present a nicely formatted meeting confirmation and store in `pending_confirmation`.
	5. Commit: on explicit user confirmation, append to `meeting.json` (supports replacement flow when user requests to replace another meeting).
- Safety: prevents scheduling in past time slots and asks clarifying questions when needed.

**RAG and documents**

- Documents live in `meetings_bundle/` and are indexed lazily into `index_storage/` when `llama_index` and embeddings are available.
- If embeddings or llama_index are missing, the system falls back to token-based paragraph scoring and still returns relevant snippets.

**Data: meetings.json**

- Location: `meeting.json` (hot-reload enabled by `POST /api/reload-meetings` and by running `POST /api/prep-meeting`).
- Structure: list of meeting objects with `meeting_id`, `title`, `description`, `start_time`, `end_time`, `participants` (with `is_organizer`).

**Audio generation**

- Primary: ElevenLabs TTS via `ELEVENLABS_API_KEY` (returns base64 data URLs). If ElevenLabs fails (e.g., 401), the frontend falls back to the browser Web Speech API.

**Testing**

- `test_scheduler.py` includes offline stubs to test scheduling and replacement flows without live LLM keys.
- `test_agent.py` exercises SmartFetcher behaviors.

**Known issues & next steps**

- ElevenLabs TTS may return 401 Unauthorized if `ELEVENLABS_API_KEY` is missing/invalid — add a valid key to `.env` to fix.
- Vector RAG requires the appropriate embedding package (`llama_index.embeddings.huggingface` or similar). If missing, the app falls back to paragraph scoring.
- Frontend confirmation UI can be improved: server supports `needs_confirmation` and `scheduler_details` for the UI to show confirm/cancel buttons.

**Contributing**

If you'd like me to commit this README change, run tests, or restart the server, tell me which action to take and I'll run it.

---

Generated/updated on: 2025-11-16

# 🧞 Calendar-Genie



