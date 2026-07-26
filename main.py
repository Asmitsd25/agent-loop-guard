from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List
import re

app = FastAPI()


class Step(BaseModel):
    step_number: int
    tool: str
    args: Dict[str, Any]
    tokens_used: int


class Request(BaseModel):
    budget_tokens: int
    steps: List[Step]


def normalize_string(s: str):
    return re.sub(r"\s+", " ", s).strip()


def canonicalize(obj):
    if isinstance(obj, dict):
        return {
            k: canonicalize(v)
            for k, v in sorted(obj.items())
            if k != "client_ts"
        }
    elif isinstance(obj, list):
        return [canonicalize(x) for x in obj]
    elif isinstance(obj, str):
        return normalize_string(obj)
    else:
        return obj


def same_call(a, b):
    return (
        a.tool == b.tool
        and canonicalize(a.args) == canonicalize(b.args)
    )


@app.post("/")
def guard(req: Request):

    total = sum(step.tokens_used for step in req.steps)

    # Budget check
    if total >= req.budget_tokens:
        return {
            "decision": "halt",
            "reason": f"Cumulative tokens_used ({total}) has reached the budget ({req.budget_tokens})."
        }

    # 3 identical consecutive calls
    run = 1

    for i in range(1, len(req.steps)):
        if same_call(req.steps[i], req.steps[i - 1]):
            run += 1

            if run >= 3:
                return {
                    "decision": "halt",
                    "reason": "Detected three or more identical consecutive tool calls."
                }
        else:
            run = 1

    # Detect trailing ABABAB cycle
    if len(req.steps) >= 6:

        tail = req.steps[-6:]

        if (
            same_call(tail[0], tail[2]) and
            same_call(tail[2], tail[4]) and
            same_call(tail[1], tail[3]) and
            same_call(tail[3], tail[5]) and
            not same_call(tail[0], tail[1])
        ):
            return {
                "decision": "halt",
                "reason": "Detected repeating two-step cycle."
            }

    return {
        "decision": "continue",
        "reason": "Within token budget and no loop detected."
    }