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
    # Ignore whitespace-only differences
    return re.sub(r"\s+", " ", s).strip()


def canonicalize(obj: Any):
    # Remove client_ts recursively, sort keys, normalize strings
    if isinstance(obj, dict):
        return {
            k: canonicalize(v)
            for k, v in sorted(obj.items())
            if k != "client_ts"
        }

    if isinstance(obj, list):
        return [canonicalize(x) for x in obj]

    if isinstance(obj, str):
        return normalize_string(obj)

    return obj


def same_call(a: Step, b: Step) -> bool:
    return (
        a.tool == b.tool
        and canonicalize(a.args) == canonicalize(b.args)
    )


def has_three_identical_calls(steps: List[Step]) -> bool:
    run = 1

    for i in range(1, len(steps)):
        if same_call(steps[i], steps[i - 1]):
            run += 1
            if run >= 3:
                return True
        else:
            run = 1

    return False


def has_alternating_cycle(steps: List[Step]) -> bool:
    """
    Detect any trailing
    A B A B A B ...
    pattern of length >=6.
    """

    n = len(steps)

    if n < 6:
        return False

    # Try every possible trailing length
    for length in range(6, n + 1):

        tail = steps[-length:]

        # Need two distinct calls
        if same_call(tail[0], tail[1]):
            continue

        ok = True

        for i in range(length):

            expected = tail[i % 2]

            if not same_call(tail[i], expected):
                ok = False
                break

        if ok:
            return True

    return False


@app.post("/")
def guard(req: Request):

    total = sum(step.tokens_used for step in req.steps)

    # Budget rule
    if total >= req.budget_tokens:
        return {
            "decision": "halt",
            "reason": f"Cumulative tokens_used ({total}) has reached the budget ({req.budget_tokens})."
        }

    # 3+ identical consecutive calls
    if has_three_identical_calls(req.steps):
        return {
            "decision": "halt",
            "reason": "Detected three or more identical consecutive tool calls."
        }

    # Alternating A/B cycle
    if has_alternating_cycle(req.steps):
        return {
            "decision": "halt",
            "reason": "Detected repeating two-step cycle."
        }

    return {
        "decision": "continue",
        "reason": "Within token budget and no loop detected."
    }