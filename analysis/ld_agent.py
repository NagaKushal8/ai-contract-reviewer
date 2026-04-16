"""
analysis/ld_agent.py

Liquidated damages extraction agent.

Scans targeted contract sections for every reference to liquidated
damages and extracts the rate, cap, trigger, grace period, and
other key terms into structured records.
"""

from utils.prompts import LD_AGENT_PROMPT
from utils.json_parser import safe_parse_json, clean_issues
from utils.config import get_openai_client, ANALYSIS_MODEL
from analysis.nrs_agent import build_sections_text, chunk_sections


# Sections carrying either of these tags may contain LD language.
LD_TAGS: list = ["liquidated_damages", "time"]


def run_ld_agent(
    sections: list,
    contract_data: dict,
    target_section_ids: list,
) -> list:
    """Run liquidated damages extraction on targeted sections.

    Filters sections to those both in target_section_ids AND tagged
    with a liquidated-damages or time tag, then sends them to GPT in
    chunks.  Results are deduplicated by section_id.

    Each failed chunk is logged and skipped — other chunks still run.

    Args:
        sections: Full tagged section list from Phase 1.
        contract_data: Full contract dict (used for format metadata).
        target_section_ids: Section IDs selected by boilerplate filter.

    Returns:
        List of LD finding dicts, each containing:
        issue_id, agent, page_number, section_id, heading,
        ld_summary, rate, cap, trigger, grace_period,
        extensions_available, sole_remedy, confidence.
        Returns [] if no relevant sections found or all chunks fail.
    """
    client = get_openai_client()
    contract_format = contract_data["contract_meta"]["format"]

    # Keep only sections that are targeted AND carry an LD-relevant tag
    filtered = [
        s for s in sections
        if s["section_id"] in target_section_ids
        and any(t in s.get("tags", []) for t in LD_TAGS)
    ]

    if not filtered:
        print("LD agent: no relevant sections found.")
        return []

    print(f"LD agent: analysing {len(filtered)} sections...")

    chunks = chunk_sections(filtered)
    all_findings: list = []

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"LD agent: chunk {i + 1}/{len(chunks)}")

        try:
            sections_text = build_sections_text(chunk)
            prompt = LD_AGENT_PROMPT.format(
                sections_text=sections_text,
            )

            response = client.chat.completions.create(
                model=ANALYSIS_MODEL,
                temperature=0,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.choices[0].message.content
            findings = safe_parse_json(raw)
            cleaned = clean_issues(findings, "ld")
            all_findings.extend(cleaned)

        except Exception as exc:
            print(f"WARNING: LD agent chunk {i + 1} failed: {exc}")
            continue

    # Deduplicate by section_id — keep first occurrence
    seen: set = set()
    unique: list = []
    for finding in all_findings:
        key = finding.get("section_id", "")
        if key not in seen:
            seen.add(key)
            unique.append(finding)

    print(f"LD agent complete. {len(unique)} findings extracted.")
    return unique
