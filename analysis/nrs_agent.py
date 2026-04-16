"""
analysis/nrs_agent.py

Nevada Revised Statutes (NRS) compliance analysis agent.

Scans targeted contract sections for clauses that may violate
Nevada construction law (NRS 108, 624) and returns a list of
flagged issues with severity, citation, and proposed fix.
"""

from utils.prompts import NRS_AGENT_PROMPT
from utils.json_parser import safe_parse_json, clean_issues
from utils.config import get_openai_client, ANALYSIS_MODEL


# Only sections carrying at least one of these tags are sent to the agent.
NRS_TAGS: list = ["nrs_risk", "payment", "termination", "indemnity"]


def build_sections_text(sections: list) -> str:
    """Format a list of section dicts into the block used in agent prompts.

    Each section is rendered as:
        [PAGE <n> | SECTION <id> | <HEADING>]
        <full section text>
        ---

    Args:
        sections: List of section dicts.

    Returns:
        Multi-line string ready for prompt insertion.
    """
    parts = []
    for s in sections:
        header = (
            f"[PAGE {s['page_start']} | "
            f"SECTION {s['section_id']} | "
            f"{s['heading']}]"
        )
        parts.append(f"{header}\n{s['text']}\n---")
    return "\n\n".join(parts)


def chunk_sections(sections: list, max_words: int = 6000) -> list:
    """Split a section list into chunks that stay under max_words.

    Prevents individual API calls from exceeding context limits.
    Sections are never split — a section that alone exceeds max_words
    is placed in its own chunk.

    Args:
        sections: List of section dicts with a ``word_count`` key.
        max_words: Soft cap on total words per chunk.

    Returns:
        List of section lists (chunks).
    """
    chunks: list = []
    current_chunk: list = []
    current_words: int = 0

    for section in sections:
        words = section.get("word_count", 0)
        if current_words + words > max_words and current_chunk:
            chunks.append(current_chunk)
            current_chunk = [section]
            current_words = words
        else:
            current_chunk.append(section)
            current_words += words

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def run_nrs_agent(
    sections: list,
    contract_data: dict,
    target_section_ids: list,
) -> list:
    """Run Nevada NRS compliance analysis on targeted sections.

    Filters sections to those both in target_section_ids AND tagged
    with at least one NRS-relevant tag, then sends them to GPT in
    chunks.  Results are deduplicated by section_id + summary prefix.

    Each failed chunk is logged and skipped — other chunks still run.

    Args:
        sections: Full tagged section list from Phase 1.
        contract_data: Full contract dict (used for format metadata).
        target_section_ids: Section IDs selected by boilerplate filter.

    Returns:
        List of NRS issue dicts, each containing:
        issue_id, agent, page_number, section_id, heading,
        severity, summary, why_problem, proposed_fix,
        nrs_citation, confidence.
    """
    client = get_openai_client()
    contract_format = contract_data["contract_meta"]["format"]

    # Keep only sections that are targeted AND carry an NRS-relevant tag
    filtered = [
        s for s in sections
        if s["section_id"] in target_section_ids
        and any(t in s.get("tags", []) for t in NRS_TAGS)
    ]

    if not filtered:
        print("NRS agent: no relevant sections found.")
        return []

    print(f"NRS agent: analysing {len(filtered)} sections...")

    chunks = chunk_sections(filtered)
    all_issues: list = []

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"NRS agent: chunk {i + 1}/{len(chunks)}")

        try:
            sections_text = build_sections_text(chunk)
            prompt = NRS_AGENT_PROMPT.format(
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
            cleaned = clean_issues(issues, "nrs")
            all_issues.extend(cleaned)

        except Exception as exc:
            print(f"WARNING: NRS agent chunk {i + 1} failed: {exc}")
            continue

    # Deduplicate by section_id + first 40 chars of summary
    seen: set = set()
    unique: list = []
    for issue in all_issues:
        key = issue.get("section_id", "") + issue.get("summary", "")[:40]
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    print(f"NRS agent complete. {len(unique)} issues found.")
    return unique
