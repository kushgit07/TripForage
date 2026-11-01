# ✈️ AI Travel Agent

A LangGraph-based travel assistant that searches flights and hotels, holds a
conversation to refine the request, and — with a human-in-the-loop review step —
emails a formatted itinerary to the user.

This is a from-scratch production rebuild of a Streamlit demo project, running
entirely on free-tier services (Groq, Duffel's test mode, Resend).

## Architecture

```
User (Streamlit) → TravelAgent (LangGraph state machine)
                        │
                        ├─ call_tools_llm  ── Groq LLM decides which tool(s) to call
                        ├─ invoke_tools    ── flights_finder / hotels_finder (Duffel API, cached)
                        │        └─ loops back to call_tools_llm until it has an answer
                        └─ email_sender    ── (paused for human review) formats + sends via Resend
```

- **`src/travel_agent/agents/`** — the LangGraph graph (`graph.py`), system prompts
  (`prompts.py`), and a factory (`factory.py`) that wires config → concrete LLM/API clients.
- **`src/travel_agent/tools/`** — `flights_finder` and `hotels_finder`, as LangChain tools
  backed by Duffel (flights via Duffel Air, hotels via Duffel Stays).
- **`src/travel_agent/services/`** — the Duffel HTTP client (bearer token + retries), the
  Resend wrapper, and a TTL cache shared by both tools.
- **`src/travel_agent/config.py`** — one `Settings` object (pydantic) for every env var,
  validated at startup.
- **`src/travel_agent/ui/streamlit_app.py`** — the chat UI.

## Why these choices

- **Groq or NVIDIA NIM instead of OpenAI** — both free, no credit card. Set `LLM_PROVIDER`
  in `.env` to switch; `agents/factory.py` builds whichever client that config selects.
  ⚠️ Both providers deprecate/rotate specific model names over time — check
  `console.groq.com/docs/models` or `build.nvidia.com` for the current list before
  assuming a model name in this repo still works.
- **Duffel for flights/hotels, replacing Amadeus.** Amadeus shut down its Self-Service
  portal on **2026-07-17**, breaking the original integration. Duffel is a modern REST API
  covering flights (`/air/offer_requests`) and hotels (`/stays/search`, "Duffel Stays") under
  one provider, with free test-mode credentials (`duffel_test_...` keys, no card required) and
  a single static bearer token instead of Amadeus's OAuth2 client-credentials flow.
- **Dependency injection everywhere** (`TravelAgent(llm, tools, email_service, ...)`) —
  every external dependency is passed in rather than constructed inline, so the graph,
  tools, and email step are each unit-testable with fakes/mocks, with no network calls
  needed to run the test suite.
- **A TTL cache in front of both search tools** — the same query asked twice within
  15 minutes (default) costs one API call, not two. Matters a lot on a free-tier quota.
- **A bounded tool-call loop** (`max_iterations`, default 6) — stops a confused LLM from
  looping through tool calls indefinitely.
- **Recipient details live in graph state, not `os.environ`** — the original app used
  global environment variables for the sender/recipient email, which would leak between
  concurrent Streamlit sessions. Here they're per-conversation state, set via
  `graph.update_state()` before the email step resumes.

## Setup

### 1. Get free API keys

| Service | Used for | Free tier | Status |
|---|---|---|---|
| [Groq](https://console.groq.com) **or** [NVIDIA NIM](https://build.nvidia.com) | LLM calls | Free, no card (NVIDIA needs phone verification) | Both active as of Aug 2026 — check current model names, see caveat above |
| [Duffel](https://duffel.com) | Flight & hotel search | Free test mode (`duffel_test_...` key, simulated data, no card) | Active — wired into `services/duffel_client.py` |
| ~~Amadeus for Developers~~ | ~~Flight & hotel search~~ | — | **Shut down 2026-07-17, removed from this repo** |
| [Resend](https://resend.com) | Sending the itinerary email | 100 emails/day, 3,000/month, free, no card | Active — wired into `services/email_service.py` (replaced SendGrid: their free-tier signup fraud checks were blocking new accounts) |

### 2. Configure

```bash
cp .env.example .env
# Set LLM_PROVIDER=groq or nvidia, and fill in the matching API key.
# Paste your Duffel test API key into DUFFEL_API_KEY.
```

### 3. Run locally with Poetry

```bash
poetry install
poetry run streamlit run src/travel_agent/ui/streamlit_app.py
```

### 4. Or run with Docker

```bash
docker compose up --build
```

Then open http://localhost:8501.

## Running the tests

```bash
poetry install
poetry run pytest -v
poetry run ruff check src tests
```

All tests run offline — the Duffel client, LLM, and Resend client are mocked/faked, so
`pytest` never makes a real network call and never needs API keys.

## Known limitations / next steps

- **Hotel search only covers a small, hardcoded set of major cities.** Duffel Stays searches
  by geographic coordinates rather than a city code, so `tools/hotels.py` resolves a city
  name via a small `_CITY_COORDS` lookup table instead of a real geocoding service. Cities
  outside that table return a clear "unsupported" message rather than a wrong result — swap
  in a geocoding API (Mapbox, Google, etc., per Duffel's own Stays guide) for full coverage.
- **Flight search returns list-summary data only** (price, itinerary, segments) — booking an
  offer, holding it, and paying for it are separate Duffel endpoints not implemented here,
  since this agent only searches and reports back, it doesn't complete purchases.
- Whichever LLM provider you pick (Groq or NVIDIA), both rotate/deprecate specific model
  names over time on their free tiers — verify the model name in `.env` against the
  provider's current docs rather than trusting what's pinned in this repo.
- The in-memory TTL cache is per-process; running multiple replicas would need a shared
  cache (e.g. Redis) to get the same de-duplication benefit.
- No persistent conversation history across app restarts (LangGraph's `MemorySaver` is
  in-memory) — swapping in a SQLite/Postgres checkpointer would fix that for a real deployment.

## License

MIT — see `LICENSE`.
