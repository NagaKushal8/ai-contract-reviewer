"""
extraction/tagger.py

Topic tagging and filled-value detection layer for the Kalb Contract Reviewer.

Operates on section dicts produced by extractor.py. Adds two fields to each
section: a list of topic tags and a boolean indicating whether project-specific
values appear to have been filled in (vs. blank template placeholders).

No AI calls. Pure Python regex matching only.
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Topic Tag Keyword Maps
# ---------------------------------------------------------------------------
# Each tag maps to a list of lowercase search strings. A section earns the tag
# if ANY of its keywords appears in the lowercased section text.

_TAG_KEYWORDS: dict = {
    "insurance": [
        "insurance",
        "liability",
        "coverage",
        "cgl",
        "additional insured",
        "waiver of subrogation",
        "builder's risk",
        "builders risk",
        "umbrella",
        "indemnif",          # catches indemnify / indemnification
    ],
    "liquidated_damages": [
        "liquidated damages",
        "delay damages",
        "per diem",
        "ld ",               # trailing space avoids matching "old", "field", etc.
    ],
    "payment": [
        "retainage",
        "retention",
        "progress payment",
        "pay-if-paid",
        "pay-when-paid",
        "schedule of values",
        "final payment",
    ],
    "termination": [
        "termination",
        "terminate",
        "default",
        "cure period",
        "suspension",
        "convenience",
    ],
    "dispute": [
        "arbitration",
        "mediation",
        "venue",
        "governing law",
        "litigation",
        "jams",
        "aaa",
    ],
    "nrs_risk": [
        "nrs",
        "nevada",
        "lien",
        "mechanic",
        "waiver",
        "prompt pay",
    ],
    "indemnity": [
        "indemnif",          # catches indemnify / indemnification
        "hold harmless",
        "defend",
    ],
    "time": [
        "substantial completion",
        "final completion",
        "contract time",
        "time is of the essence",
        "days from",
        "date of commencement",
    ],
    "gmp": [
        "guaranteed maximum",
        "gmp",
        "cost of the work",
    ],
}


# ---------------------------------------------------------------------------
# Filled-Value Regex Patterns
# ---------------------------------------------------------------------------

# --- Shared patterns (both formats) ---
_PATTERN_DOLLAR        = re.compile(r"\$[\d,]+")                  # $1,000,000
_PATTERN_DAYS          = re.compile(r"\b\d+\s*days?\b", re.I)    # 150 days
_PATTERN_PERCENT       = re.compile(r"\b\d+\s*%")                 # 10%
_PATTERN_MONTH_NAME    = re.compile(
    r"\b(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b",
    re.I,
)

# --- ConsensusDocs-specific patterns ---
# Bracket fields that are filled in: [Project Name] but NOT [___] blanks
_CD_FILLED_BRACKET     = re.compile(r"\[(?!_+\])[^\]]{1,30}\]")
# Checked boxes: _x_, ☑, ✓, [x], [ x ]
_CD_CHECKBOX           = re.compile(r"_x_|☑|✓|\[x\]|\[ *x *\]", re.I)
# Known party name tokens indicating a blank has been completed
_CD_PARTY_NAME         = re.compile(r"\b(kalb|owner name|constructor)\b", re.I)

# --- AIA-specific patterns ---
# Underscores followed by at least one non-newline character (filled underline field)
_AIA_FILLED_UNDERSCORE = re.compile(r"_{3,}[^\n]+")
# AIA-style checked parenthetical: (x) or ( x )
_AIA_CHECKBOX          = re.compile(r"\( *x *\)|\(x\)", re.I)


# ---------------------------------------------------------------------------
# Core Tagging Functions
# ---------------------------------------------------------------------------

def tag_section(section: dict, contract_format: str) -> dict:
    """Add topic tags and filled-value detection to a single section dict.

    Mutates the input dict in place and also returns it so callers can chain.

    Args:
        section: A section dict as produced by extractor.detect_sections().
                 Must contain at least a "text" key (str).
        contract_format: "consensusdocs" | "aia" | "unknown"

    Returns:
        The same section dict with two new keys added:
            "tags"             — list of matched topic tag strings (may be empty)
            "has_filled_values"— bool; True if any filled-value pattern matched
    """
    if not section:
        section["tags"] = []
        section["has_filled_values"] = False
        return section

    text: str = section.get("text", "") or ""
    text_lower = text.lower()

    # ── Topic Tags ────────────────────────────────────────────────────────────
    tags: list = []
    for tag_name, keywords in _TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                tags.append(tag_name)
                break  # one match per tag is enough

    section["tags"] = tags

    # ── Filled-Value Detection ────────────────────────────────────────────────
    # Start with patterns common to both formats
    filled = (
        bool(_PATTERN_DOLLAR.search(text))
        or bool(_PATTERN_DAYS.search(text))
        or bool(_PATTERN_PERCENT.search(text))
        or bool(_PATTERN_MONTH_NAME.search(text))
    )

    if not filled:
        if contract_format == "consensusdocs":
            filled = (
                bool(_CD_FILLED_BRACKET.search(text))
                or bool(_CD_CHECKBOX.search(text))
                or bool(_CD_PARTY_NAME.search(text))
            )
        elif contract_format == "aia":
            filled = (
                bool(_AIA_FILLED_UNDERSCORE.search(text))
                or bool(_AIA_CHECKBOX.search(text))
            )
        else:
            # Unknown format: try all patterns
            filled = (
                bool(_CD_FILLED_BRACKET.search(text))
                or bool(_CD_CHECKBOX.search(text))
                or bool(_CD_PARTY_NAME.search(text))
                or bool(_AIA_FILLED_UNDERSCORE.search(text))
                or bool(_AIA_CHECKBOX.search(text))
            )

    section["has_filled_values"] = filled
    return section


def tag_all_sections(sections: list, contract_format: str) -> list:
    """Apply tag_section to every section in the list.

    Args:
        sections: List of section dicts from extractor.detect_sections().
        contract_format: "consensusdocs" | "aia" | "unknown"

    Returns:
        The same list with each section dict updated in place.
        Returns an empty list if sections is empty or None.
    """
    if not sections:
        return []

    for section in sections:
        tag_section(section, contract_format)

    return sections


def get_sections_by_tag(sections: list, tag: str) -> list:
    """Filter sections to those that contain a specific topic tag.

    Intended for use by Phase 2 AI agents to retrieve only the sections
    relevant to a particular analysis task (e.g. all insurance clauses).

    Args:
        sections: List of tagged section dicts (after tag_all_sections()).
        tag: One of the topic tag strings defined in _TAG_KEYWORDS,
             e.g. "insurance", "liquidated_damages", "payment", etc.

    Returns:
        Filtered list of section dicts that contain the given tag.
        Returns an empty list if sections is empty or no match is found.
    """
    if not sections or not tag:
        return []

    return [s for s in sections if tag in s.get("tags", [])]
