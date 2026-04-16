"""
analysis/__init__.py

Phase 2 master orchestrator for the Kalb Contract Reviewer.

Exports run_all_agents() which runs the full AI analysis pipeline
on a Phase 1 contract_data dict.
"""

from extraction.tagger import tag_all_sections
from analysis.boilerplate_filter import run_boilerplate_filter
from analysis.nrs_agent import run_nrs_agent
from analysis.owner_agent import run_owner_agent
from analysis.insurance_agent import run_insurance_agent
from analysis.ld_agent import run_ld_agent
from analysis.summary_generator import run_summary_generator


def run_all_agents(contract_data: dict) -> dict:
    """Run the full Phase 2 AI analysis pipeline.

    Steps:
    1. Tag sections if they are not already tagged.
    2. Run the boilerplate filter to identify non-standard sections
       and merge with the always-analyze list.
    3. Run all four analysis agents independently (NRS, Owner,
       Insurance, LD).  If any single agent fails the others
       continue running.
    4. Assemble the combined results dict.
    5. Run the executive summary generator on the combined results.
    6. Return the final results dict.

    Args:
        contract_data: Dict produced by Phase 1 extract_contract().
            Must contain keys "sections" and "contract_meta".

    Returns:
        {
            "contract_format":           str,
            "target_sections_analyzed":  list[str],
            "nrs_issues":                list[dict],
            "owner_issues":              list[dict],
            "insurance_issues":          list[dict],
            "ld_findings":               list[dict],
            "total_issues":              int,
            "analysis_complete":         bool,
            "executive_summary": {
                "top_5_concerns":    list[dict],
                "recommended_markup":list[dict],
            }
        }
    """
    sections = contract_data.get("sections", [])
    contract_format = contract_data["contract_meta"]["format"]

    # Tag sections if the first section has no tags yet
    if sections and "tags" not in sections[0]:
        print("Tagging sections...")
        sections = tag_all_sections(sections, contract_format)
        contract_data["sections"] = sections

    # ── Step 1: Boilerplate filter ─────────────────────────────────────────
    target_ids = run_boilerplate_filter(sections, contract_format)

    # ── Step 2: Analysis agents (each wrapped independently) ───────────────
    print("\n--- Running analysis agents ---")

    try:
        nrs_issues = run_nrs_agent(sections, contract_data, target_ids)
    except Exception as exc:
        print(f"WARNING: NRS agent failed entirely: {exc}")
        nrs_issues = []

    try:
        owner_issues = run_owner_agent(sections, contract_data, target_ids)
    except Exception as exc:
        print(f"WARNING: Owner agent failed entirely: {exc}")
        owner_issues = []

    try:
        insurance_issues = run_insurance_agent(
            sections, contract_data, target_ids
        )
    except Exception as exc:
        print(f"WARNING: Insurance agent failed entirely: {exc}")
        insurance_issues = []

    try:
        ld_findings = run_ld_agent(sections, contract_data, target_ids)
    except Exception as exc:
        print(f"WARNING: LD agent failed entirely: {exc}")
        ld_findings = []

    # ── Step 3: Assemble combined results ──────────────────────────────────
    results = {
        "contract_format":          contract_format,
        "target_sections_analyzed": target_ids,
        "nrs_issues":               nrs_issues,
        "owner_issues":             owner_issues,
        "insurance_issues":         insurance_issues,
        "ld_findings":              ld_findings,
        "total_issues": (
            len(nrs_issues) + len(owner_issues) + len(insurance_issues)
        ),
        "analysis_complete": True,
    }

    # ── Step 4: Executive summary ──────────────────────────────────────────
    print("\n--- Generating summary ---")
    try:
        summary = run_summary_generator(results)
    except Exception as exc:
        print(f"WARNING: Summary generator failed entirely: {exc}")
        summary = {"top_5_concerns": [], "recommended_markup": []}

    results["executive_summary"] = summary
    return results
