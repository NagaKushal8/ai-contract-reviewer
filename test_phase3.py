"""
test_phase3.py

Phase 3 test: loads saved Phase 2 results and builds the PDF report
without re-running any AI analysis.  Use this during PDF development
iterations to avoid burning API credits.
"""

import json
from report.pdf_builder import build_pdf

RESULTS_PATH = "test/phase2_results.json"
OUTPUT_PATH  = "test/contract_review_report.pdf"


def run_test():
    """Load Phase 2 results from disk and build the PDF report."""

    print("Loading Phase 2 results...")
    with open(RESULTS_PATH, encoding="utf-8") as fh:
        results = json.load(fh)

    total   = results.get("total_issues", 0)
    nrs     = len(results.get("nrs_issues", []))
    owner   = len(results.get("owner_issues", []))
    ins     = len(results.get("insurance_issues", []))
    ld      = len(results.get("ld_findings", []))
    secs    = len(results.get("target_sections_analyzed", []))

    print(f"  Total issues      : {total}")
    print(f"  NRS issues        : {nrs}")
    print(f"  Owner issues      : {owner}")
    print(f"  Insurance gaps    : {ins}")
    print(f"  LD findings       : {ld}")
    print(f"  Sections analyzed : {secs}")

    print(f"\nBuilding PDF report -> {OUTPUT_PATH}")
    build_pdf(results, OUTPUT_PATH)

    print(f"PDF saved to: {OUTPUT_PATH}")
    print("Open the file to verify formatting.")


if __name__ == "__main__":
    run_test()
