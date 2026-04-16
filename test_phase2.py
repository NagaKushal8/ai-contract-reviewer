"""
test_phase2.py

End-to-end Phase 2 test: runs full AI analysis on the real contract PDF.
Chains Phase 1 extraction into Phase 2 agents and prints a summary.
"""

import json

from extraction.extractor import extract_contract
from extraction.tagger import tag_all_sections
from analysis import run_all_agents

PDF = "test/Concensus Contract EXECUTED.pdf"


def run_test():
    """Execute the full Phase 1 + Phase 2 pipeline and print results."""

    print("=" * 60)
    print("  PHASE 2 TEST: Full AI Analysis Pipeline")
    print("=" * 60)

    # ── Phase 1: Extract ───────────────────────────────────────────────────
    print("\n[1] Extracting contract (Phase 1)...")
    contract_data = extract_contract(PDF)
    sections = contract_data["sections"]
    fmt = contract_data["contract_meta"]["format"]
    print(f"    Format: {fmt} | Sections: {len(sections)}")

    # ── Tag sections ───────────────────────────────────────────────────────
    print("\n[2] Tagging sections...")
    contract_data["sections"] = tag_all_sections(sections, fmt)
    tagged_count = sum(
        1 for s in contract_data["sections"] if s.get("tags")
    )
    print(f"    {tagged_count}/{len(sections)} sections have tags")

    # ── Phase 2: AI analysis ───────────────────────────────────────────────
    print("\n[3] Running AI analysis (Phase 2)...")
    results = run_all_agents(contract_data)

    # ── Results summary ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    print(f"  NRS issues found      : {len(results['nrs_issues'])}")
    print(f"  Owner-favored found   : {len(results['owner_issues'])}")
    print(f"  Insurance gaps found  : {len(results['insurance_issues'])}")
    print(f"  LD findings found     : {len(results['ld_findings'])}")
    print(f"  Total issues          : {results['total_issues']}")

    # ── Sample issue from each agent (one block per agent) ───────────────
    for agent_key, label in [
        ("nrs_issues",       "NRS"),
        ("owner_issues",     "OWNER"),
        ("insurance_issues", "INSURANCE"),
        ("ld_findings",      "LD"),
    ]:
        issues = results[agent_key]
        if issues:
            print(f"\n  --- Sample {label} issue ---")
            sample = issues[0]
            print(f"    Section   : {sample.get('section_id')}")
            print(f"    Page      : {sample.get('page_number')}")
            if agent_key == "ld_findings":
                print(f"    Summary   : {sample.get('ld_summary', '')[:100]}")
                print(f"    Rate      : {sample.get('rate', 'n/a')}")
                print(f"    Trigger   : {sample.get('trigger', 'n/a')}")
            else:
                print(f"    Severity  : {sample.get('severity')}")
                print(f"    Summary   : {sample.get('summary', '')[:100]}")
                print(f"    Confidence: {sample.get('confidence')}")
    # ── end per-agent loop ─────────────────────────────────────────────────

    # ── Executive summary (printed once, after all agents) ─────────────────
    summary = results.get("executive_summary", {})

    concerns = summary.get("top_5_concerns", [])
    if concerns:
        print(f"\n  --- Executive Summary: Top {len(concerns)} Concerns ---")
        for c in concerns:
            print(f"    {c['rank']}. [{c.get('urgency', '')}] "
                  f"{c.get('concern', '')[:80]}")

    markup = summary.get("recommended_markup", [])
    if markup:
        print(f"\n  --- Recommended Markup ({len(markup)} items) ---")
        for m in markup:
            print(f"    {m['revision_number']}. "
                  f"{m.get('action', '')[:80]}  "
                  f"[{m.get('section_reference', '')}]")
    # ── end executive summary ──────────────────────────────────────────────

    # Save full results to disk
    output_path = "test/phase2_results.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\n  Full results saved to: {output_path}")

    print("\n" + "=" * 60)
    print("  PHASE 2 TEST COMPLETE")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_test()
