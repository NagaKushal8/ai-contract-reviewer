"""
analysis/summary_generator.py

Executive summary generator.

Takes the combined results from all four analysis agents and
produces a plain-English executive summary with the top five
business concerns and a recommended markup list.
"""

import json

from utils.prompts import EXECUTIVE_SUMMARY_PROMPT, EXECUTIVE_SUMMARY_SYSTEM
from utils.json_parser import safe_parse_json
from utils.config import get_openai_client, ANALYSIS_MODEL

# Fallback object returned when the API call or parsing fails.
_EMPTY_SUMMARY: dict = {
    "top_5_concerns": [],
    "recommended_markup": [],
}


def run_summary_generator(analysis_results: dict) -> dict:
    """Generate an executive summary from the combined agent results.

    Formats all four agent outputs as JSON and sends them to GPT with
    the EXECUTIVE_SUMMARY_PROMPT.  The model returns a single JSON
    object containing top_5_concerns and recommended_markup.

    Args:
        analysis_results: Dict returned by run_all_agents(), containing
            keys nrs_issues, owner_issues, insurance_issues, ld_findings.

    Returns:
        Dict with keys:
            "top_5_concerns"    — list of concern dicts (rank 1–5)
            "recommended_markup"— list of revision action dicts
        Returns _EMPTY_SUMMARY on any API or parsing failure.
    """
    client = get_openai_client()

    def _fmt(issues: list) -> str:
        """Serialise issues list to indented JSON, or 'None found.' string."""
        if not issues:
            return "None found."
        return json.dumps(issues, indent=2)

    try:
        prompt = EXECUTIVE_SUMMARY_PROMPT.format(
            nrs_issues=_fmt(analysis_results.get("nrs_issues", [])),
            owner_issues=_fmt(analysis_results.get("owner_issues", [])),
            insurance_issues=_fmt(
                analysis_results.get("insurance_issues", [])
            ),
            ld_findings=_fmt(analysis_results.get("ld_findings", [])),
        )

        print("Generating executive summary...")
        response = client.chat.completions.create(
            model=ANALYSIS_MODEL,
            temperature=0,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": EXECUTIVE_SUMMARY_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )

        raw = response.choices[0].message.content
        # safe_parse_json always returns a list; summary is a single object
        parsed = safe_parse_json(raw)

        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]
        if isinstance(parsed, dict):
            return parsed

        print("WARNING: Summary generator returned unexpected structure.")
        return _EMPTY_SUMMARY

    except Exception as exc:
        print(f"WARNING: Summary generator failed: {exc}")
        return _EMPTY_SUMMARY
