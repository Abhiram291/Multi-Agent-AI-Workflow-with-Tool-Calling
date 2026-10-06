"""
tools/profile_csv.py

The single tool for Step 1. Loads a CSV and returns structured
metadata about it: row count, column names, dtypes, nulls, sample rows.

Design decisions worth noting (for SKILL.md section 4 later):

1. The tool returns errors as data, not exceptions.
   Why: the LLM can only react to things it SEES. If we raise an exception
   that bubbles up outside the loop, the agent is blind to it and will
   either hang or confidently claim success. By returning
   {"status": "error", "message": "..."} we let the LLM read the failure
   and decide what to do (retry, give up, ask the user).

2. We validate input with a Pydantic schema.
   Why: Gemini might hallucinate argument names (e.g., 'filepath' instead
   of 'path'). Pydantic catches that at the boundary with a clear error,
   not deep inside pandas with a confusing stack trace.

3. The return shape is JSON-serialisable (dict of primitives).
   Why: it gets fed back to the LLM as text. If pandas objects leaked out,
   serialisation would fail silently and the LLM would see garbage.
"""

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, ValidationError


# ---------- Input schema ----------
class ProfileCsvInput(BaseModel):
    path: str = Field(
        ...,
        description="Relative or absolute path to a CSV file on disk.",
    )


def profile_csv(path: str) -> dict[str, Any]:
    """
    Load a CSV and return a structured profile of it.

    Returns a dict. Never raises for expected failures (missing file,
    unreadable file, empty file). Only unexpected failures (OS errors,
    out-of-memory) will propagate.
    """
    # 1. Validate the input through Pydantic.
    try:
        validated = ProfileCsvInput(path=path)
    except ValidationError as e:
        return {
            "status": "error",
            "message": f"Invalid tool input: {e.errors()}",
        }

    # 2. Does the file exist?
    file_path = Path(validated.path)
    if not file_path.exists():
        return {
            "status": "error",
            "message": f"File not found: {validated.path}",
        }

    # 3. Can pandas read it?
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to parse CSV: {type(e).__name__}: {e}",
        }

    # 4. Edge case: empty file.
    if df.empty:
        return {
            "status": "error",
            "message": "CSV loaded but contains zero rows.",
        }

    # 5. Build the profile.
    columns = [
        {
            "name": str(col),
            "dtype": str(df[col].dtype),
            "nulls": int(df[col].isna().sum()),
        }
        for col in df.columns
    ]

    sample = df.head(3).to_dict(orient="records")

    return {
        "status": "ok",
        "data": {
            "path": str(file_path),
            "rows": int(len(df)),
            "columns": columns,
            "sample": sample,
        },
    }