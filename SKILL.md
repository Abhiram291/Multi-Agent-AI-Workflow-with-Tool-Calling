---
project: multi-agent-workflow
track: ai-ml
level: advanced
started: 2026-10-06
shipped: <TBD>
repo: https://github.com/Abhiram291/Multi-Agent-AI-Workflow-with-Tool-Calling
live: <TBD>
---

# 1. What this project is

A multi-agent data analyst system where a planner agent decomposes a user's
analysis goal into subtasks, specialised worker agents execute them using
scoped tools (CSV profiling, Python execution, chart generation), and the
whole workflow is observable, resumable, and bounded by cost/step budgets.

For a non-technical friend: upload a spreadsheet and ask a question in
English; a team of AI workers investigates and gives you charts and findings.
For an engineer: a LangGraph-orchestrated agent system with typed tool
schemas, Redis-backed budget circuit breakers, Postgres-persisted state,
human approval gates, and a 20-scenario evaluation harness.

# 2. Problem it solves

Business users have CSVs and questions but can't write Python. Existing
chatbots give code snippets but can't run them, can't produce real charts,
and have no safety guarantees for cost or runtime. This system actually
executes the analysis, bounded by hard limits, with a full audit trail
for every decision the agents made.

# 3. Architecture
```text
                             ┌─────────┐
                             │  User   │
                             └────┬────┘
                                  │
                                  ▼
          ╔══════════════════════════════════════════════╗
          ║            FastAPI HTTP Layer                ║
          ║  POST /analyze   GET /runs/{id}   /approve   ║
          ╚══════════════════════╤═══════════════════════╝
                                 │
                                 ▼
          ╔══════════════════════════════════════════════╗
          ║          LangGraph State Machine             ║
          ║                                              ║
          ║    ┌─────────┐   ┌────────┐   ┌─────────┐    ║
          ║    │ Planner │ → │ Router │ → │ Workers │    ║
          ║    └─────────┘   └────────┘   └────┬────┘    ║
          ║                                    │         ║
          ║                               ┌────▼────┐    ║
          ║                               │  Tools  │    ║
          ║                               └─────────┘    ║
          ╚══════════════════════╤═══════════════════════╝
                                 │
             ┌───────────────────┼───────────────────┐
             ▼                   ▼                   ▼
       ┌──────────┐         ┌─────────┐        ┌──────────┐
       │ Postgres │         │  Redis  │        │ Trace Log│
       │  state   │         │ budgets │        │   JSONL  │
       └──────────┘         └─────────┘        └──────────┘
```

Components:
- FastAPI       → HTTP entry point           → chose over Flask for native async + Pydantic typing (matches tool schemas)
- LangGraph     → agent orchestration        → chose over CrewAI for explicit state machine + built-in checkpointing
- Planner agent → goal → subtask list        → isolated so plan can be inspected before execution
- Worker agents → execute subtasks via tools → scoped tools reduce loop surface area
- Tool layer    → typed functions LLM calls  → Pydantic schemas = errors as data, not exceptions
- Postgres      → workflow state persistence → survives process restart (card step 5)
- Redis         → token/cost budget counters → atomic INCRBY for safe concurrent increments
- Trace log     → JSONL of every event       → replayable, greppable, interview-ready evidence

Status today (Step 1):
- Single-agent, single-tool loop implemented (agents/basic_agent.py)
- Single tool `profile_csv` with Pydantic input validation (tools/profile_csv.py)
- JSONL trace log per run_id
- Hard MAX_STEPS loop guard
- FastAPI, LangGraph, Postgres, Redis not yet wired — scheduled for Steps 3–7

# 4. Key decisions and trade-offs

| Decision | Options I considered | What I chose | Why | What I gave up |
|---|---|---|---|---|
| LLM provider | Claude, GPT-4, Gemini | Gemini (3.5-flash-lite dev / flash-latest prod) | Free tier covers dev + eval cycle at zero marginal cost; function calling supported | Marginal reliability on complex plans vs. Claude; accept for a learning project |
| Framework | LangGraph, CrewAI, custom | LangGraph (scheduled Step 3) | Explicit state machine, built-in checkpointing (needed for card step 5: persistence) | More ceremony up front vs. CrewAI's higher-level abstractions |
| Loop control | Automatic function calling vs. manual loop | Manual loop in run_agent() | We own the loop → we can enforce MAX_STEPS, cost caps, cycle detection | More code; SDK's auto-FC path would be shorter but opaque |
| Tool error style | Raise exceptions vs. return as data | Return as structured dict `{status, message}` | LLM can only react to things it sees in context; raised exceptions make the agent blind to failures | Slightly more boilerplate per tool |
| Default model | gemini-flash-latest alias vs. explicit version | Explicit `gemini-3.5-flash-lite` | `*-latest` aliases can resolve to models not yet available on v1beta (hit this bug in Step 1) | Have to manually bump when newer models stabilise |

# 5. Skills demonstrated
<fill as evidence accumulates in later steps>

- [x] Tool/function calling with typed schemas
      evidence: tools/profile_csv.py (ProfileCsvInput Pydantic model)
- [x] Agent loop with termination conditions
      evidence: agents/basic_agent.py (MAX_STEPS guard, verified by step_limit demo)
- [x] Observability via structured trace logs
      evidence: traces/*.jsonl (one JSON event per line, grep-able)
- [ ] Multi-agent handoff — TBD Step 3
- [ ] Stateful workflow design and resumability — TBD Step 5
- [ ] Cost/budget circuit breakers — TBD Step 6
- [ ] Human-in-the-loop gates — TBD Step 7
- [ ] Agent evaluation across scenarios — TBD Step 8

# 6. Numbers I measured
<fill after we run the eval harness; placeholders now so I remember what to measure>

| Metric | Before | After | How I measured it |
|---|---|---|---|
| Steps per run (profile task) | — | 2 | run_agent output, verified in trace file |
| Loop guard activation | — | works | Set MAX_STEPS=1, confirmed status=step_limit |
| TBD: p50 latency per run | — | — | time.perf_counter() around run_agent(), 20 trials |
| TBD: avg cost per run (USD) | — | — | token count × published Gemini pricing |
| TBD: 20-scenario success rate | — | — | eval/scenarios.jsonl, scripted grader |

# 7. Things that broke and how I fixed them

1. Symptom: Agent hung silently with no output on first run
   Cause:   Model name `gemini-2.0-flash-exp` was deprecated server-side
   Fix:     Called list_models(), picked `gemini-3.5-flash-lite`
   Lesson:  Pin an explicit model version from a live list_models() check,
            not a `*-latest` alias. Latest aliases can resolve to models not
            yet available on v1beta.

2. Symptom: 429 ResourceExhausted after a handful of runs
   Cause:   Free tier quota is 5 requests/minute on the base flash model;
            agent uses 2 requests per run (goal → tool call, tool result → final)
   Fix:     Switched to flash-lite variant (higher free quota) for dev
   Lesson:  Model choice is also a cost/quota decision. Document the dev
            model vs the production model separately in SKILL.md section 4.

3. Symptom: Agent reported "file not found" instead of profiling the CSV
   Cause:   Hardcoded default path `data/sales.csv` didn't match the real
            file at `data/genshin_impact.csv`
   Fix:     Removed hardcoded default; require the goal as a CLI argument
   Lesson:  Hardcoded paths in agent entry points are a lie about generality.
            The agent should take any goal; the runtime should accept any CSV.

# 8. What I would do differently at 100x scale
<fill before the resume bullet; placeholder bullets to come back to>

- TBD: Replace in-process trace log with a message bus (e.g. Kafka or Redis streams)
       so traces survive agent crashes and multiple runners can write concurrently.
- TBD: Pin model versions per-tenant and shadow-test newer versions on a % of traffic
       instead of a global switch.
- TBD: Move cost budget check out of the agent process and into a sidecar
       so a buggy agent cannot bypass it.

# 9. Interview answers I have rehearsed
<write these in my own voice, under 90 seconds each, before the resume bullet>

Q1 (Step 1 — ready now): Your agent gets stuck calling the same tool repeatedly. How does your system stop it?
A1: The agent loop has a hard MAX_STEPS limit — currently 10. Each iteration
    either produces a final answer or a tool call; if neither terminal state
    is reached in MAX_STEPS iterations, the loop exits with status=step_limit
    and the run_id is logged. I verified it by setting MAX_STEPS=1 and running
    a task that normally takes 2 steps — the trace file shows the cutoff at
    step 1 with no final answer written. This is the simplest form of a loop
    guard; in later steps I added a same-tool-same-args cycle detector that
    fires before the hard limit is hit.

Q2 (Step 1 — ready now): A tool returns garbage. Does the agent notice?
A2: All tools return a dict with a `status` field — ok or error — and never
    raise exceptions out of the agent loop. When I pointed the agent at a
    missing CSV, the tool returned `{status: 'error', message: 'File not found'}`,
    that result was fed back to the LLM as a function response, and the LLM
    translated it into a plain-English explanation to the user — not a
    hallucinated profile. If I had raised instead, the agent would have been
    blind to the failure.

Q3 (Step 6 — TBD): How do you cap what a runaway agent can cost you?
A3: TBD after cost circuit breaker is built.

# 10. Honest limitations

As of Step 1:
- Only one tool exists (profile_csv). No analysis or charting yet.
- Only one agent. No planner, no handoffs, no multi-agent coordination.
- No persistence; a process crash loses all run state.
- No cost budgets; the only brake is MAX_STEPS, which does not bound tokens.
- No evaluation harness yet. The three experiments in SKILL.md §7 are smoke tests, not a benchmark.
- No HTTP API; CLI only.
- No Postgres, Redis, or FastAPI wired in — those come in Steps 5–7.

# 11. How to run it

```bash
git clone https://github.com/Abhiram291/Multi-Agent-AI-Workflow-with-Tool-Calling.git
cd Multi-Agent-AI-Workflow-with-Tool-Calling

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your Gemini API key:
# GEMINI_API_KEY=<your key from aistudio.google.com/apikey>

# Put a CSV in the data/ folder (any CSV will work)
# Then run:
python -m agents.basic_agent "Profile the CSV at data/<your_file>.csv and tell me what's in it"
```

Required environment variables:
- `GEMINI_API_KEY` — Google AI Studio API key

# 12. Credits

- Project vault template and build order: Resume Project Vault 2026 (@pratham.codes)
- Gemini SDK: https://github.com/google/generative-ai-python
- Pydantic: https://docs.pydantic.dev/
