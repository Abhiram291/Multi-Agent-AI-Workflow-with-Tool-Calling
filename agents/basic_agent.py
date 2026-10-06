"""
agents/basic_agent.py

A single-tool agent. The simplest possible version of the system,
which everything else will build on.

What happens on run():
  1. We register profile_csv as a Gemini tool
  2. We start a chat with the user's goal as the first message
  3. The model either:
       a. responds with text (we're done, return it)
       b. responds with a tool call (we execute it, feed result back, loop)
  4. We cap the loop with a hard step limit (MAX_STEPS)

Interview-worthy points baked into this file:
  - Why do we need MAX_STEPS?
       Because the model can get stuck calling the same tool forever.
       This is literally interview question #1 on the project card.
  - Why do we feed error results back as "function_response" instead
    of raising?
       So the LLM can see the failure and react. Raising would hide it.
  - Why log every step to a trace file?
       Observability. The card requires a "full trace log of every agent
       decision, tool call and result" (core feature bullet 8).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from tools.profile_csv import profile_csv


# ---------- Config ----------
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY missing. Put it in .env (see .env.example)."
    )

genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-3.5-flash-lite"

# Hard step limit — the simplest form of loop prevention.
MAX_STEPS = 10

TRACES_DIR = Path("traces")
TRACES_DIR.mkdir(exist_ok=True)


# ---------- Tool registry ----------
TOOLS = [profile_csv]


# ---------- Tracing ----------
def _write_trace(run_id: str, event: dict[str, Any]) -> None:
    event["ts"] = time.time()
    trace_path = TRACES_DIR / f"{run_id}.jsonl"
    with trace_path.open("a") as f:
        f.write(json.dumps(event, default=str) + "\n")


# ---------- The agent loop ----------
def run_agent(goal: str) -> dict[str, Any]:
    """
    Run the single-tool agent on a user goal.

    Returns:
      {
        "run_id": str,
        "status": "ok" | "step_limit" | "error",
        "final_answer": str | None,
        "steps_taken": int
      }
    """
    run_id = str(uuid.uuid4())[:8]
    _write_trace(run_id, {"event": "run_start", "goal": goal})

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        tools=TOOLS,
        system_instruction=(
            "You are a data analyst assistant. "
            "When the user mentions a CSV file, use the profile_csv tool "
            "to inspect it, then summarise what you learned in plain English. "
            "If a tool returns status='error', explain what went wrong to "
            "the user; do not retry blindly."
        ),
    )

    # We control the loop; Gemini will NOT auto-execute functions.
    chat = model.start_chat(enable_automatic_function_calling=False)
    response = chat.send_message(goal)

    for step in range(1, MAX_STEPS + 1):
        parts = response.candidates[0].content.parts
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            # Final answer path.
            final_text = "".join(
                p.text for p in parts if hasattr(p, "text") and p.text
            )
            _write_trace(
                run_id,
                {"event": "final_answer", "step": step, "text": final_text},
            )
            return {
                "run_id": run_id,
                "status": "ok",
                "final_answer": final_text,
                "steps_taken": step,
            }

        # Execute each tool call.
        tool_responses = []
        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args)

            _write_trace(
                run_id,
                {
                    "event": "tool_call",
                    "step": step,
                    "tool": tool_name,
                    "args": tool_args,
                },
            )

            if tool_name == "profile_csv":
                result = profile_csv(**tool_args)
            else:
                result = {
                    "status": "error",
                    "message": f"Unknown tool: {tool_name}",
                }

            _write_trace(
                run_id,
                {
                    "event": "tool_result",
                    "step": step,
                    "tool": tool_name,
                    "result": result,
                },
            )

            tool_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=tool_name,
                        response={"result": result},
                    )
                )
            )

        response = chat.send_message(tool_responses)

    # Step limit hit — the runaway agent case.
    _write_trace(run_id, {"event": "step_limit_hit", "limit": MAX_STEPS})
    return {
        "run_id": run_id,
        "status": "step_limit",
        "final_answer": None,
        "steps_taken": MAX_STEPS,
    }


# ---------- CLI entry point ----------
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Everything after the script name becomes the goal.
        # Example: python -m agents.basic_agent "Profile data/genshin_impact.csv"
        user_goal = " ".join(sys.argv[1:])
    else:
        print("Usage: python -m agents.basic_agent \"<your goal>\"")
        print("Example: python -m agents.basic_agent \"Profile data/genshin_impact.csv\"")
        sys.exit(1)

    print(f"\n>> Goal: {user_goal}\n")
    result = run_agent(user_goal)

    print(f"\n>> Run ID:      {result['run_id']}")
    print(f">> Status:      {result['status']}")
    print(f">> Steps taken: {result['steps_taken']}")
    print(f"\n>> Final answer:\n{result['final_answer']}\n")
    print(f">> Full trace: traces/{result['run_id']}.jsonl")