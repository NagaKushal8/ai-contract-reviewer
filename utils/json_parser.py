"""
utils/json_parser.py

Robust JSON parsing helpers for GPT agent output.

GPT responses sometimes wrap JSON in markdown fences, return a bare
object instead of an array, or produce slightly malformed JSON.  The
functions here handle all of those cases without raising exceptions.
"""

import re
import json


def safe_parse_json(raw_text: str) -> list:
    """Safely parse GPT JSON output. Never crashes.

    Attempts four strategies in order:
    1. Strip markdown fences, then json.loads the whole string.
    2. Regex-extract the outermost [...] array and parse it.
    3. Regex-extract the outermost {...} object, wrap in a list.
    4. Return [] with a warning if all strategies fail.

    Args:
        raw_text: Raw string from a GPT completion.

    Returns:
        A Python list.  Always a list — single objects are wrapped.
        Returns [] if parsing fails entirely.
    """
    if not raw_text:
        return []

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    clean = re.sub(r"```json|```", "", raw_text).strip()

    # Strategy 1: direct parse
    try:
        result = json.loads(clean)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract outermost [...] array
    array_match = re.search(r"\[.*\]", clean, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 3: extract outermost {...} object and wrap
    obj_match = re.search(r"\{.*\}", clean, re.DOTALL)
    if obj_match:
        try:
            return [json.loads(obj_match.group())]
        except json.JSONDecodeError:
            pass

    print(f"WARNING: JSON parse failed. Preview: {raw_text[:200]}")
    return []


def validate_issue(issue: dict, agent_name: str) -> bool:
    """Validate that an issue dict contains all required fields.

    Each agent returns a different output schema, so required fields are
    determined by agent_name:
    - "ld"        : LD extraction schema  (ld_summary, rate, etc.)
    - "insurance" : Insurance gap schema  (contract_requirement, gap_exists, etc.)
    - all others  : Standard risk schema  (severity, why_problem, proposed_fix)

    Args:
        issue: The issue dict returned by an agent.
        agent_name: Short agent identifier — "ld", "insurance", "nrs", "owner".

    Returns:
        True if all required fields are present, False otherwise.
        Prints a warning listing missing fields when returning False.
    """
    if agent_name == "ld":
        required = ["page_number", "section_id", "ld_summary"]

    elif agent_name == "insurance":
        required = [
            "page_number", "section_id", "summary",
            "contract_requirement", "kalb_coverage",
            "gap_exists", "confidence",
        ]

    else:
        # nrs and owner agents share the standard risk schema
        required = [
            "page_number", "section_id", "severity",
            "summary", "why_problem", "proposed_fix", "confidence",
        ]

    missing = [f for f in required if f not in issue]
    if missing:
        print(
            f"WARNING [{agent_name}]: Issue missing fields: {missing}"
        )
        return False
    return True


def clean_issues(issues: list, agent_name: str) -> list:
    """Validate all issues, stamp the agent field, and return clean list.

    Iterates over a raw list of issue dicts, validates each one, adds the
    ``agent`` field, and drops any that fail validation.

    Args:
        issues: List of raw issue dicts from safe_parse_json().
        agent_name: Short identifier for the calling agent (e.g. "nrs",
                    "owner", "insurance", "ld").

    Returns:
        List of valid, agent-stamped issue dicts.
    """
    clean = []
    for issue in issues:
        if validate_issue(issue, agent_name):
            issue["agent"] = agent_name
            clean.append(issue)
    return clean
