"""Quick pipeline test against the real contract PDF."""

import json
from extraction.extractor import extract_contract
from extraction.tagger import tag_all_sections, get_sections_by_tag
from extraction.quality_check import check_quality, get_section_count_warning

PDF = "test/Concensus Contract EXECUTED.pdf"

print("=" * 60)
print("  Running full pipeline on real contract PDF")
print("=" * 60)

# ── Step 1: Extract ───────────────────────────────────────────
print("\n[1] Extracting pages...")
contract = extract_contract(PDF)
meta = contract["contract_meta"]

pages = contract["pages"]
total = meta["total_pages"]
print(f"    Format         : {meta['format']}")
print(f"    Total pages    : {total}")
print(f"    Pages extracted: {len(pages)} of {total}")
print(f"    Sections found : {len(contract['sections'])}")

if len(pages) > 0:
    # Show first 300 chars of page 3 (pages 1-2 are cover in this contract)
    preview_page = pages.get(3, pages.get(1, ""))
    print(f"\n    Page 3 preview (first 300 chars):")
    print("    " + preview_page[:300].replace("\n", "\n    "))
    print("    ...")

# ── Step 2: Quality check ─────────────────────────────────────
print("\n[2] Quality check...")
qc = check_quality(contract["pages"])
print(f"    Quality     : {qc['quality']}")
print(f"    Empty pages : {qc['empty_pages']}")
if qc["warning"]:
    print(f"    Warning     : {qc['warning']}")

warn = get_section_count_warning(contract["sections"])
if warn:
    print(f"    {warn}")

# ── Step 3: Tag all sections ──────────────────────────────────
print("\n[3] Tagging sections...")
sections = contract["sections"]
tagged = tag_all_sections(sections, meta["format"])

# Section detection summary
print(f"\nSection detection results:")
print(f"    Total sections found: {len(sections)}")
print(f"\n    First 10 sections:")
for s in sections[:10]:
    print(
        f"      [{s['section_id']}] {s['heading'][:50]:<50} "
        f"| p{s['page_start']} "
        f"| tags: {s.get('tags', [])}"
    )

print(f"\n    High priority sections found:")
high_priority = ["6.5", "11.1", "11.2", "10.2", "12.3", "12.4", "13.4", "3.5"]
for hp in high_priority:
    match = next((s for s in sections if s["section_id"] == hp), None)
    if match:
        print(f"      FOUND  : {match['section_id']} {match['heading'][:40]}")
    else:
        print(f"      MISSING: {hp}")

print(f"\n    --- All {len(tagged)} Sections (tagged) ---")
for s in tagged:
    filled_marker = "[FILLED]" if s["has_filled_values"] else ""
    tags_str = ", ".join(s["tags"]) if s["tags"] else "no tags"
    heading_preview = s["heading"][:52]
    print(
        f"    p{s['page_start']:>3}  [{s['section_id']:<12}] "
        f"{heading_preview:<52}  {tags_str}  {filled_marker}"
    )

# ── Step 4: Key tag groups ────────────────────────────────────
print("\n[4] Sections by tag:")
key_tags = [
    "insurance", "liquidated_damages", "payment",
    "termination", "dispute", "indemnity", "time", "gmp", "nrs_risk",
]
for tag in key_tags:
    secs = get_sections_by_tag(tagged, tag)
    if secs:
        ids = [s["section_id"] for s in secs]
        print(f"    {tag:<22}: {ids}")

# ── Step 5: Dump JSON output size ─────────────────────────────
json_out = json.dumps(contract, indent=2)
print(f"\n[5] JSON output size: {len(json_out):,} chars")

print("\nAll done.")
