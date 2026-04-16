"""
analysis/insurance_agent.py

Insurance gap analysis agent.

Compares the insurance requirements stated in the contract against
Kalb Construction's current Certificate of Insurance and returns
a list of any coverage gaps.
"""

from utils.prompts import INSURANCE_AGENT_PROMPT
from utils.json_parser import safe_parse_json, clean_issues
from utils.config import get_openai_client, ANALYSIS_MODEL
from analysis.nrs_agent import build_sections_text


# Only sections carrying this tag are sent to the insurance agent.
INSURANCE_TAGS: list = ["insurance"]


def run_insurance_agent(
    sections: list,
    contract_data: dict,
    target_section_ids: list,
) -> list:
    """Run insurance gap analysis on contract insurance sections.

    Filters sections to those both in target_section_ids AND tagged
    ``insurance``, formats them for the prompt, and sends a single
    API call (insurance sections are typically compact enough to fit
    in one context window).

    Args:
        sections: Full tagged section list from Phase 1.
        contract_data: Full contract dict (used for format metadata).
        target_section_ids: Section IDs selected by boilerplate filter.

    Returns:
        List of insurance gap dicts, each containing:
        issue_id, agent, page_number, section_id, heading,
        summary, contract_requirement, kalb_coverage,
        gap_exists, gap_description, confidence.
        Returns [] if no insurance sections found or API call fails.
    """
    client = get_openai_client()
    contract_format = contract_data["contract_meta"]["format"]

    # Keep only sections that are targeted AND tagged insurance
    filtered = [
        s for s in sections
        if s["section_id"] in target_section_ids
        and any(t in s.get("tags", []) for t in INSURANCE_TAGS)
    ]

    if not filtered:
        print("Insurance agent: no relevant sections found.")
        return []

    print(f"Insurance agent: analysing {len(filtered)} sections...")

    try:
        sections_text = build_sections_text(filtered)
        prompt = INSURANCE_AGENT_PROMPT.format(
            sections_text=sections_text,
        )

        response = client.chat.completions.create(
            model=ANALYSIS_MODEL,
            temperature=0,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.choices[0].message.content
        issues = safe_parse_json(raw)
        cleaned = clean_issues(issues, "insurance")

        print(f"Insurance agent complete. {len(cleaned)} gaps found.")
        return cleaned

    except Exception as exc:
        print(f"WARNING: Insurance agent failed: {exc}")
        return []
