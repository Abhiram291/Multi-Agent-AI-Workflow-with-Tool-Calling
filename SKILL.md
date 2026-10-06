---
project: multi-agent-workflow
track: ai-ml
level: advanced
started: 2026-10-06
shipped: <TBD>
repo: <your github url>
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

[paste the ASCII diagram above]

Components:
- FastAPI       -> HTTP entry point           -> chose over Flask for native async + Pydantic typing (matches tool schemas)
- LangGraph     -> agent orchestration        -> chose over CrewAI for explicit state machine + built-in checkpointing
- Planner agent -> goal → subtask list        -> isolated so plan can be inspected before execution
- Worker agents -> execute subtasks via tools -> scoped tools reduce loop surface area
- Tool layer    -> typed functions LLM calls  -> Pydantic schemas = errors as data, not exceptions
- Postgres      -> workflow state persistence -> survives process restart (card step 5)
- Redis         -> token/cost budget counters -> atomic INCRBY for safe concurrent increments
- Trace log     -> JSONL of every event       -> replayable, greppable, interview-ready evidence

# 4. Key decisions and trade-offs
<fill as decisions happen>

# 5. Skills demonstrated
<fill as evidence accumulates>

# 6-12. <fill as the project progresses>
