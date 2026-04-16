"""
analysis/boilerplate_filter.py

Lightweight GPT filter that identifies which sections contain
non-standard (filled-in or modified) content, so the heavier
analysis agents only receive sections worth analysing.

The result is merged with a hard-coded always-analyze list of
high-risk section IDs so critical clauses are never skipped even
if they appear to be boilerplate.
"""

from utils.prompts import BOILERPLATE_FILTER_PROMPT, BOILERPLATE_FILTER_SYSTEM
from utils.json_parser import safe_parse_json
from utils.config import get_openai_client, FILTER_MODEL


# Section IDs that are always sent to analysis agents regardless
# of the boilerplate filter verdict.

CONSENSUSDOCS_ALWAYS: list = [
    "6.5.1", "6.5.2", "6.5.3",
    "6.1",   "6.3",   "6.7",
    "10.2",  "10.2.3","10.8",
    "11.1",  "11.2",  "11.3.1",
    "12.1",  "12.3",  "12.4",  "12.5",
    "13.4.1","13.4.2",
    "14.3",  "3.5",
]

AIA_ALWAYS: list = [
    "9.3",  "9.8",  "11.1", "11.2", "11.3",
    "14.1", "14.2", "15.4", "13.1", "8.2",
]


def get_always_analyze(contract_format: str) -> list:
    """Return the always-analyze section ID list for the given format.

    Args:
        contract_format: "consensusdocs" | "aia" | "unknown"

    Returns:
        List of section ID strings that must always be analysed.
        Returns CONSENSUSDOCS_ALWAYS for unknown formats.
    """
    if contract_format == "aia":
        return AIA_ALWAYS
    return CONSENSUSDOCS_ALWAYS


def build_section_summaries(sections: list) -> str:
    """Build a compact one-liner per section for the boilerplate filter prompt.

    Format per line: "<section_id> <HEADING>: <first 150 chars of text>"

    Args:
        sections: List of section dicts from Phase 1.

    Returns:
        Multi-line string ready for prompt insertion.
    """
    lines = []
    for s in sections:
        preview = s.get("text", "")[:150].replace("\n", " ")
        lines.append(
            f"{s['section_id']} {s['heading']}: {preview}"
        )
    return "\n".join(lines)


def run_boilerplate_filter(
    sections: list,
    contract_format: str,
) -> list:
    """Identify non-standard sections and merge with always-analyze list.

    Sends a compact section summary to the filter model (gpt-4.1-mini by
    default) and asks it to return only the IDs of sections that contain
    filled-in values or modified language.  The result is merged with the
    hard-coded always-analyze list so critical clauses are never missed.

    Falls back to always-analyze list only if the API call fails.

    Args:
        sections: Tagged section list from Phase 1.
        contract_format: "consensusdocs" | "aia" | "unknown"

    Returns:
        Deduplicated list of section_id strings to pass to analysis agents.
    """
    always = get_always_analyze(contract_format)

    try:
        client = get_openai_client()
        summaries = build_section_summaries(sections)
        prompt = BOILERPLATE_FILTER_PROMPT.format(
            contract_format=contract_format,
            section_summaries=summaries,
        )

        print("Running boilerplate filter...")
        response = client.chat.completions.create(
            model=FILTER_MODEL,
            temperature=0,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": BOILERPLATE_FILTER_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )

        raw = response.choices[0].message.content
        non_standard = safe_parse_json(raw)
        # Ensure we only work with strings
        non_standard = [
            str(x) for x in non_standard if x is not None
        ]

        combined = list(set(always + non_standard))
        print(
            f"Boilerplate filter: {len(non_standard)} non-standard "
            f"+ {len(always)} always = {len(combined)} total"
        )
        return combined

    except Exception as exc:
        print(f"WARNING: Boilerplate filter failed: {exc}")
        print("Falling back to always-analyze list only.")
        return always
