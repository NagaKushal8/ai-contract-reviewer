"""
analysis/owner_agent.py

Owner-favored clause analysis agent.

Scans targeted contract sections for clauses that create
disproportionate risk for the contractor or unreasonably
favour the owner.
"""

from utils.prompts import OWNER_AGENT_PROMPT
from utils.json_parser import safe_parse_json, clean_issues
from utils.config import get_openai_client, ANALYSIS_MODEL
from analysis.nrs_agent import build_sections_text, chunk_sections


# Only sections carrying at least one of these tags are sent to the agent.
OWNER_TAGS: list = [
    "termination", "indemnity", "dispute", "payment", "time",
]


def run_owner_agent(
    sections: list,
    contract_data: dict,
    target_section_ids: list,
) -> list:
    """Run owner-favored clause analysis on targeted sections.

    Filters sections to those both in target_section_ids AND tagged
    with at least one owner-risk tag, then sends them to GPT in chunks.
    Results are deduplicated by section_id + summary prefix.

    Each failed chunk is logged and skipped — other chunks still run.

    Args:
        sections: Full tagged section list from Phase 1.
        contract_data: Full contract dict (used for format metadata).
        target_section_ids: Section IDs selected by boilerplate filter.

    Returns:
        List of owner-risk issue dicts, each containing:
        issue_id, agent, page_number, section_id, heading,
        severity, summary, why_problem, proposed_fix,
        nrs_citation, confidence.
    """
    client = get_openai_client()
    contract_format = contract_data["contract_meta"]["format"]

    # Keep only sections that are targeted AND carry an owner-risk tag
    filtered = [
        s for s in sections
        if s["section_id"] in target_section_ids
        and any(t in s.get("tags", []) for t in OWNER_TAGS)
    ]

    if not filtered:
        print("Owner agent: no relevant sections found.")
        return []

    print(f"Owner agent: analysing {len(filtered)} sections...")

    chunks = chunk_sections(filtered)
    all_issues: list = []

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"Owner agent: chunk {i + 1}/{len(chunks)}")

        try:
            sections_text = build_sections_text(chunk)
            prompt = OWNER_AGENT_PROMPT.format(
                contract_format=contract_format,
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
            cleaned = clean_issues(issues, "owner")
            all_issues.extend(cleaned)

        except Exception as exc:
            print(f"WARNING: Owner agent chunk {i + 1} failed: {exc}")
            continue

    # Deduplicate by section_id + first 40 chars of summary
    seen: set = set()
    unique: list = []
    for issue in all_issues:
        key = issue.get("section_id", "") + issue.get("summary", "")[:40]
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    print(f"Owner agent complete. {len(unique)} issues found.")
    return unique
