"""Phase 2 import and unit smoke test. No API calls made."""

from utils.config import get_openai_client, FILTER_MODEL, ANALYSIS_MODEL
from utils.json_parser import safe_parse_json, validate_issue, clean_issues
from utils.prompts import (
    BOILERPLATE_FILTER_PROMPT, NRS_AGENT_PROMPT, OWNER_AGENT_PROMPT,
    INSURANCE_AGENT_PROMPT, LD_AGENT_PROMPT, EXECUTIVE_SUMMARY_PROMPT,
)
from analysis.boilerplate_filter import run_boilerplate_filter, build_section_summaries
from analysis.nrs_agent import run_nrs_agent, build_sections_text, chunk_sections
from analysis.owner_agent import run_owner_agent
from analysis.insurance_agent import run_insurance_agent
from analysis.ld_agent import run_ld_agent
from analysis.summary_generator import run_summary_generator
from analysis import run_all_agents

print("All imports OK")
print(f"FILTER_MODEL   = {FILTER_MODEL}")
print(f"ANALYSIS_MODEL = {ANALYSIS_MODEL}")

# ── safe_parse_json ───────────────────────────────────────────────────────
assert safe_parse_json("") == [], "empty string"
assert safe_parse_json("[]") == [], "empty array"
assert safe_parse_json('[{"a":1}]') == [{"a": 1}], "normal array"
assert safe_parse_json('{"a":1}') == [{"a": 1}], "bare object"
assert safe_parse_json('```json\n[{"a":1}]\n```') == [{"a": 1}], "fenced"
print("safe_parse_json             : OK")

# ── validate_issue ────────────────────────────────────────────────────────
good_standard = {
    "page_number": 1, "section_id": "6.5", "severity": "High",
    "summary": "x", "why_problem": "y", "proposed_fix": "z",
    "confidence": "High",
}
assert validate_issue(good_standard, "nrs") is True
assert validate_issue({"page_number": 1}, "nrs") is False

# LD schema
assert validate_issue({"page_number": 1, "section_id": "6.5", "ld_summary": "x"}, "ld") is True

# Insurance schema — the fields that were previously causing 0 results
good_insurance = {
    "page_number": 33, "section_id": "11.2",
    "summary": "Contract requires builders risk",
    "contract_requirement": "$5M builders risk",
    "kalb_coverage": "Not carried",
    "gap_exists": True,
    "confidence": "High",
}
assert validate_issue(good_insurance, "insurance") is True
# Insurance issue must NOT be rejected for missing severity/why_problem/proposed_fix
assert validate_issue({"page_number": 1, "section_id": "11.2"}, "insurance") is False
print("validate_issue              : OK")

# ── clean_issues ──────────────────────────────────────────────────────────
raw = [good_standard.copy(), {"bad": "issue"}]
cleaned = clean_issues(raw, "nrs")
assert len(cleaned) == 1
assert cleaned[0]["agent"] == "nrs"
print("clean_issues                : OK")

# ── chunk_sections ────────────────────────────────────────────────────────
secs = [{"word_count": 2000, "section_id": str(i)} for i in range(5)]
chunks = chunk_sections(secs, max_words=6000)
assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"
assert len(chunks[0]) == 3
assert len(chunks[1]) == 2
print("chunk_sections              : OK")

# ── build_section_summaries ───────────────────────────────────────────────
sample_secs = [
    {"section_id": "6.5", "heading": "LIQUIDATED DAMAGES",
     "text": "The contractor shall pay $1,000 per day."}
]
summary_str = build_section_summaries(sample_secs)
assert "6.5" in summary_str
assert "LIQUIDATED DAMAGES" in summary_str
print("build_section_summaries     : OK")

# ── build_sections_text ───────────────────────────────────────────────────
text = build_sections_text(
    [{"page_start": 22, "section_id": "6.5", "heading": "LDs", "text": "body"}]
)
assert "PAGE 22" in text
assert "SECTION 6.5" in text
print("build_sections_text         : OK")

# ── prompt placeholders render without KeyError ───────────────────────────
BOILERPLATE_FILTER_PROMPT.format(
    contract_format="consensusdocs",
    section_summaries="6.5 LDs: body",
)
NRS_AGENT_PROMPT.format(contract_format="consensusdocs", sections_text="body")
OWNER_AGENT_PROMPT.format(contract_format="consensusdocs", sections_text="body")
INSURANCE_AGENT_PROMPT.format(sections_text="body")
LD_AGENT_PROMPT.format(sections_text="body")
EXECUTIVE_SUMMARY_PROMPT.format(
    nrs_issues="[]", owner_issues="[]",
    insurance_issues="[]", ld_findings="[]",
)
print("All prompt templates render : OK")

print()
print("All Phase 2 smoke tests passed.")
