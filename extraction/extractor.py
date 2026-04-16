"""
extraction/extractor.py

Data extraction layer for the Kalb Contract Reviewer (Phase 1).
Handles PDF ingestion, format detection, and section parsing for
ConsensusDocs 230 and AIA A201/A101 construction contracts.

Extraction strategy:
  1. pdfplumber  — fast, zero-cost, works for digital/text-layer PDFs
  2. Mistral OCR — automatic fallback for scanned/image-only PDFs
"""

import base64
import re
import json
import os
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Format Detection
# ---------------------------------------------------------------------------

def detect_format(pages: dict) -> str:
    """Detect the contract format from the first three pages of text.

    Scans for vendor-specific keywords to distinguish between
    ConsensusDocs 230 and AIA A201/A101 contracts.

    Args:
        pages: Dict mapping page_number (int) to extracted text (str).
               Only the first 3 pages are examined.

    Returns:
        "consensusdocs" | "aia" | "unknown"
    """
    if not pages:
        return "unknown"

    # Combine text from pages 1, 2, 3 (or however many exist)
    sample_text = ""
    for page_num in sorted(pages.keys())[:3]:
        sample_text += pages[page_num].lower()

    # ConsensusDocs identifiers
    consensusdocs_keywords = [
        "consensusdocs",
        "consensus docs",
        "cd 230",
        "cd230",
    ]
    for kw in consensusdocs_keywords:
        if kw in sample_text:
            return "consensusdocs"

    # AIA identifiers
    aia_keywords = [
        "american institute of architects",
        "aia document",
        " aia ",
        "a201",
        "a101",
    ]
    for kw in aia_keywords:
        if kw in sample_text:
            return "aia"

    return "unknown"


# ---------------------------------------------------------------------------
# PDF Page Extraction  (pdfplumber primary → Mistral OCR fallback)
# ---------------------------------------------------------------------------

# Minimum character count for a page to be considered non-empty
_MIN_PAGE_CHARS = 20

# If fewer than this fraction of pages have text, treat the PDF as scanned
_SCANNED_COVERAGE_THRESHOLD = 0.20


def extract_pages_mistral(pdf_path: str) -> dict:
    """Extract text from a scanned PDF using the Mistral OCR API.

    Reads the whole PDF as bytes, base64-encodes it, and submits it to
    ``mistral-ocr-latest`` as an inline data-URI document.  Mistral returns
    per-page markdown which is stored directly as the page text.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dict of {page_number (int): text (str)}, 1-indexed.
        Returns an empty dict on any API or IO error.
    """
    from mistralai.client import Mistral

    load_dotenv()
    api_key = os.getenv("MISTRAL_API_KEY")

    if not api_key:
        print("ERROR: MISTRAL_API_KEY not found in .env — cannot run OCR.")
        return {}

    try:
        print("Reading PDF for Mistral OCR...")
        with open(pdf_path, "rb") as fh:
            pdf_bytes = fh.read()

        # Encode as base64 string for the data-URI payload
        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        client = Mistral(api_key=api_key)

        print("Sending to Mistral OCR API...")
        print("This may take 30-60 seconds for a full contract...")

        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                # Inline the entire PDF as a base64 data-URI
                "document_url": f"data:application/pdf;base64,{pdf_b64}",
            },
            include_image_base64=False,
        )

        pages: dict = {}
        # ocr_response.pages is a list; each item has .index (0-based) and .markdown
        for page in ocr_response.pages:
            page_number = page.index + 1          # convert to 1-indexed
            text = page.markdown if page.markdown else ""
            if text and len(text.strip()) > _MIN_PAGE_CHARS:
                pages[page_number] = text.strip()

        print(f"Mistral OCR complete. Extracted {len(pages)} pages.")
        return pages

    except Exception as exc:
        print(f"ERROR: Mistral OCR failed: {exc}")
        print("Check your MISTRAL_API_KEY in .env")
        return {}


def extract_pages(pdf_path: str) -> dict:
    """Extract text from a PDF, falling back to Mistral OCR for scanned files.

    Strategy:
      1. Try pdfplumber (instant, free, works for digital PDFs).
      2. Count pages that returned meaningful text (> 20 chars).
      3. If fewer than 20 % of pages have text, the PDF is scanned →
         automatically retry with the Mistral OCR API.
      4. Return {page_number: text} regardless of which path was taken.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        Dict of {page_number (int): text (str)}, 1-indexed.
        Returns an empty dict if the file is missing or all extraction fails.
    """
    if not pdf_path:
        return {}

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"WARNING: PDF not found at path: {pdf_path}")
        return {}

    # ── Step 1: pdfplumber pass ───────────────────────────────────────────
    pages: dict = {}
    total_pages = 0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text and len(text.strip()) > _MIN_PAGE_CHARS:
                    pages[i] = text.strip()
    except Exception as exc:
        print(f"ERROR: pdfplumber failed on '{pdf_path}': {exc}")

    # ── Step 2: Coverage check ────────────────────────────────────────────
    coverage = len(pages) / total_pages if total_pages > 0 else 0

    if coverage >= _SCANNED_COVERAGE_THRESHOLD:
        print(f"pdfplumber extracted {len(pages)}/{total_pages} pages.")
        return pages

    # ── Step 3: Scanned PDF — switch to Mistral OCR ───────────────────────
    print(
        f"pdfplumber only got {len(pages)}/{total_pages} pages "
        f"({coverage:.0%} coverage)."
    )
    print("Scanned PDF detected. Switching to Mistral OCR...")
    return extract_pages_mistral(pdf_path)


# ---------------------------------------------------------------------------
# Section Detection
# ---------------------------------------------------------------------------

# --- ConsensusDocs heading patterns ---

# Matches "ARTICLE 6 TIME" — ARTICLE keyword, number, then all-caps title
_CD_ARTICLE = re.compile(
    r"^(ARTICLE\s+(\d+)\s+([A-Z][A-Z\s,/\-&]+))$",
    re.MULTILINE,
)

# Matches "6.5 LIQUIDATED DAMAGES" — n.n then all-caps text
_CD_SECTION = re.compile(
    r"^((\d+\.\d+)\s+([A-Z][A-Z\s,/\-&]+))$",
    re.MULTILINE,
)

# Matches subsections like "6.5.1" with optional all-caps title
_CD_SUBSECTION = re.compile(
    r"^((\d+\.\d+\.\d+)(?:\s+([A-Z][A-Z\s,/\-&]*))?)\s*$",
    re.MULTILINE,
)

# --- AIA heading patterns ---

# Matches "§ 9.3" or "§9.3" — AIA section symbol with number
_AIA_SECTION = re.compile(
    r"^(§\s*(\d+(?:\.\d+)*)\s*(.*))$",
    re.MULTILINE,
)

# Matches "ARTICLE 1" — standalone article header
_AIA_ARTICLE = re.compile(
    r"^(ARTICLE\s+(\d+)\s*([A-Z][A-Z\s,/\-&]*)?)\s*$",
    re.MULTILINE,
)

# Matches "Section 3.1 ..." — spelled-out Section keyword
_AIA_NAMED_SECTION = re.compile(
    r"^(Section\s+(\d+\.\d+)\s+(.*))$",
    re.MULTILINE | re.IGNORECASE,
)


def _build_heading_list_consensusdocs(pages: dict) -> list:
    """Scan all pages and return a sorted list of heading hit records for ConsensusDocs.

    Each record is a dict:
      page, char_offset_in_page, section_id, heading, article_label, raw_line
    """
    hits = []
    current_article = ""

    for page_num in sorted(pages.keys()):
        text = pages[page_num]
        lines = text.split("\n")
        char_offset = 0

        for line in lines:
            stripped = line.strip()

            # Check for ARTICLE-level header first (highest precedence)
            m_art = _CD_ARTICLE.match(stripped)
            if m_art:
                current_article = m_art.group(1).strip()
                hits.append({
                    "page": page_num,
                    "char_offset": char_offset,
                    "section_id": f"ARTICLE {m_art.group(2)}",
                    "heading": m_art.group(3).strip(),
                    "article_label": current_article,
                    "raw_line": stripped,
                    "level": "article",
                })
                char_offset += len(line) + 1
                continue

            # Check for n.n SECTION header
            m_sec = _CD_SECTION.match(stripped)
            if m_sec:
                hits.append({
                    "page": page_num,
                    "char_offset": char_offset,
                    "section_id": m_sec.group(2),
                    "heading": m_sec.group(3).strip(),
                    "article_label": current_article,
                    "raw_line": stripped,
                    "level": "section",
                })
                char_offset += len(line) + 1
                continue

            # Check for n.n.n subsection
            m_sub = _CD_SUBSECTION.match(stripped)
            if m_sub:
                title = m_sub.group(3).strip() if m_sub.group(3) else ""
                hits.append({
                    "page": page_num,
                    "char_offset": char_offset,
                    "section_id": m_sub.group(2),
                    "heading": title,
                    "article_label": current_article,
                    "raw_line": stripped,
                    "level": "subsection",
                })

            char_offset += len(line) + 1

    return hits


def _build_heading_list_aia(pages: dict) -> list:
    """Scan all pages and return a sorted list of heading hit records for AIA."""
    hits = []
    current_article = ""

    for page_num in sorted(pages.keys()):
        text = pages[page_num]
        lines = text.split("\n")
        char_offset = 0

        for line in lines:
            stripped = line.strip()

            # ARTICLE header
            m_art = _AIA_ARTICLE.match(stripped)
            if m_art:
                current_article = stripped
                hits.append({
                    "page": page_num,
                    "char_offset": char_offset,
                    "section_id": f"ARTICLE {m_art.group(2)}",
                    "heading": (m_art.group(3) or "").strip(),
                    "article_label": current_article,
                    "raw_line": stripped,
                    "level": "article",
                })
                char_offset += len(line) + 1
                continue

            # § symbol section
            m_sec = _AIA_SECTION.match(stripped)
            if m_sec:
                hits.append({
                    "page": page_num,
                    "char_offset": char_offset,
                    "section_id": m_sec.group(2),
                    "heading": m_sec.group(3).strip(),
                    "article_label": current_article,
                    "raw_line": stripped,
                    "level": "section",
                })
                char_offset += len(line) + 1
                continue

            # "Section n.n ..." style
            m_named = _AIA_NAMED_SECTION.match(stripped)
            if m_named:
                hits.append({
                    "page": page_num,
                    "char_offset": char_offset,
                    "section_id": m_named.group(2),
                    "heading": m_named.group(3).strip(),
                    "article_label": current_article,
                    "raw_line": stripped,
                    "level": "section",
                })

            char_offset += len(line) + 1

    return hits


def _headings_to_sections(hits: list, pages: dict) -> list:
    """Convert a list of heading hits into section dicts with body text.

    For each heading, the body text is everything from that heading's line
    to (but not including) the next heading's line, collected across pages.

    Args:
        hits: Ordered list of heading hit records from a _build_heading_list_* fn.
        pages: Full {page_number: text} dict for text lookup.

    Returns:
        List of section dicts matching the spec.
    """
    if not hits:
        return []

    # Build a flat list of all lines with their page numbers for easy slicing
    all_lines: list = []  # [(page_num, line_text), ...]
    for page_num in sorted(pages.keys()):
        for line in pages[page_num].split("\n"):
            all_lines.append((page_num, line))

    # Map each heading hit to an index in all_lines by matching raw_line
    # We scan forward to find the first occurrence of the raw_line on the
    # expected page, starting from the previous hit's position.
    def find_line_index(raw_line: str, page: int, search_from: int) -> int:
        for idx in range(search_from, len(all_lines)):
            if all_lines[idx][0] == page and all_lines[idx][1].strip() == raw_line:
                return idx
        # Fallback: search whole corpus
        for idx in range(len(all_lines)):
            if all_lines[idx][0] == page and all_lines[idx][1].strip() == raw_line:
                return idx
        return search_from

    sections = []
    search_cursor = 0

    for i, hit in enumerate(hits):
        start_idx = find_line_index(hit["raw_line"], hit["page"], search_cursor)
        search_cursor = start_idx + 1

        # End index is either the line before the next heading, or end of doc
        if i + 1 < len(hits):
            next_hit = hits[i + 1]
            end_idx = find_line_index(next_hit["raw_line"], next_hit["page"], search_cursor)
        else:
            end_idx = len(all_lines)

        # Collect body text (include the heading line itself)
        body_lines = [ln for (_, ln) in all_lines[start_idx:end_idx]]
        body_text = "\n".join(body_lines).strip()

        page_start = all_lines[start_idx][0] if start_idx < len(all_lines) else hit["page"]
        page_end = all_lines[end_idx - 1][0] if end_idx > 0 and end_idx <= len(all_lines) else page_start

        word_count = len(body_text.split()) if body_text else 0

        sections.append({
            "section_id": hit["section_id"],
            "heading": hit["heading"],
            "article": hit["article_label"],
            "page_start": page_start,
            "page_end": page_end,
            "text": body_text,
            "word_count": word_count,
        })

    return sections


def _detect_sections_plaintext(pages: dict, contract_format: str) -> list:
    """Parse sections from plain-text pdfplumber output.

    Uses format-specific regex patterns (ConsensusDocs and AIA) to locate
    headings, then bundles all text between successive headings into section
    dicts.  This is the original detection logic, unchanged.

    Args:
        pages: Dict of {page_number: text} from extract_pages().
        contract_format: "consensusdocs" | "aia" | "unknown"

    Returns:
        List of section dicts with keys:
        section_id, heading, article, page_start, page_end, text, word_count.
    """
    if contract_format == "consensusdocs":
        hits = _build_heading_list_consensusdocs(pages)
    elif contract_format == "aia":
        hits = _build_heading_list_aia(pages)
    else:
        # Unknown: try both and keep the richer result
        cd_hits = _build_heading_list_consensusdocs(pages)
        aia_hits = _build_heading_list_aia(pages)
        hits = cd_hits if len(cd_hits) >= len(aia_hits) else aia_hits

    return _headings_to_sections(hits, pages)


# Regex that extracts a numeric section ID from the start of a heading string,
# e.g. "6.5", "11.2.1", "3.5" — used by the markdown parser below.
_MD_SECTION_ID = re.compile(r"^(\d+(?:\.\d+)+)")

# Regex for an ARTICLE heading: "ARTICLE 6 TIME" or "ARTICLE 11"
_MD_ARTICLE_ID = re.compile(r"^ARTICLE\s+(\d+)", re.IGNORECASE)


def _detect_sections_markdown(pages: dict, contract_format: str) -> list:
    """Parse sections from Mistral OCR markdown output.

    Mistral OCR renders headings with standard markdown pound signs:
      #   = article level  (e.g. "# ARTICLE 6 TIME")
      ##  = main section   (e.g. "## 6.5 LIQUIDATED DAMAGES")
      ### = subsection     (e.g. "### 6.5.1 Substantial Completion")

    Any line that starts with one or more ``#`` characters is treated as a
    section boundary.  All body text between two consecutive headings is
    accumulated into that section's ``text`` field.

    Args:
        pages: Dict of {page_number: text} from extract_pages().
        contract_format: "consensusdocs" | "aia" | "unknown" — kept for
                         signature compatibility; not used in this path.

    Returns:
        List of section dicts with keys:
        section_id, heading, article, page_start, page_end, text, word_count.
        Sections with 10 or fewer words are filtered out as noise.
    """
    sections: list = []
    current_section: dict | None = None
    current_article: str = ""

    for page_num in sorted(pages.keys()):
        page_text = pages[page_num]
        lines = page_text.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Classify heading level by counting leading # characters
            is_article      = stripped.startswith("# ")       # H1
            is_main_section = stripped.startswith("## ")      # H2
            is_subsection   = stripped.startswith("### ")     # H3
            is_any_heading  = is_article or is_main_section or is_subsection

            if is_any_heading:
                # Flush the previous section before opening a new one
                if current_section and current_section["text"].strip():
                    sections.append(current_section)

                # Strip all leading # markers and whitespace
                clean_heading = stripped.lstrip("#").strip()

                # Try to pull a numeric section ID (e.g. "6.5", "11.2.1")
                id_match = _MD_SECTION_ID.match(clean_heading)
                if id_match:
                    section_id = id_match.group(1).rstrip(".")
                else:
                    # Fall back to ARTICLE number or first 20 chars
                    art_match = _MD_ARTICLE_ID.match(clean_heading)
                    section_id = (
                        f"ARTICLE_{art_match.group(1)}"
                        if art_match
                        else clean_heading[:20]
                    )

                # H1 lines update the running article context
                if is_article:
                    current_article = clean_heading

                current_section = {
                    "section_id": section_id,
                    "heading":    clean_heading,
                    "article":    current_article,
                    "page_start": page_num,
                    "page_end":   page_num,
                    "text":       "",
                    "word_count": 0,
                }

            elif current_section is not None:
                # Accumulate body lines into the open section
                current_section["text"]    += line + "\n"
                current_section["page_end"] = page_num

    # Flush the final open section
    if current_section and current_section["text"].strip():
        sections.append(current_section)

    # Compute word counts now that all body text is gathered
    for section in sections:
        section["word_count"] = len(section["text"].split())

    # Drop stub entries that are almost certainly noise (table of contents
    # lines, page headers, etc.)
    sections = [s for s in sections if s["word_count"] > 10]

    print(f"Markdown section detection found {len(sections)} sections.")

    if len(sections) < 5:
        print("WARNING: Low section count. "
              "Check markdown heading structure.")

    return sections


def detect_sections(pages: dict, contract_format: str) -> list:
    """Detect and extract sections from contract pages.

    Auto-detects whether the page text is markdown (Mistral OCR output) or
    plain text (pdfplumber output) and delegates to the appropriate parsing
    strategy.  Both paths return the same output format so callers are
    completely unaware of which path was taken.

    Args:
        pages: Dict of {page_number: text} from extract_pages().
        contract_format: "consensusdocs" | "aia" | "unknown"

    Returns:
        List of section dicts:
        {
            "section_id":  str,   e.g. "6.5" or "ARTICLE_6"
            "heading":     str,   e.g. "LIQUIDATED DAMAGES"
            "article":     str,   parent article label if known
            "page_start":  int,
            "page_end":    int,
            "text":        str,   full section body text
            "word_count":  int,
        }

    Prints a warning if fewer than 5 sections are detected.
    """
    if not pages:
        return []

    # Sample the first three pages to decide which parser to use.
    # More than 5 ``#`` characters in that sample strongly indicates markdown.
    sample_text = " ".join(list(pages.values())[:3])
    is_markdown = sample_text.count("#") > 5

    if is_markdown:
        print("Detected markdown format (Mistral OCR output).")
        sections = _detect_sections_markdown(pages, contract_format)
    else:
        print("Detected plain text format (pdfplumber output).")
        sections = _detect_sections_plaintext(pages, contract_format)

    if len(sections) < 5:
        print(
            "WARNING: Low section count detected. "
            "Format detection may have failed."
        )

    return sections


# ---------------------------------------------------------------------------
# Master Extraction Function
# ---------------------------------------------------------------------------

def extract_contract(pdf_path: str) -> dict:
    """Run the full extraction pipeline on a construction contract PDF.

    Calls extract_pages → detect_format → detect_sections in order and
    assembles the results into a single structured JSON-serialisable dict
    ready for Phase 2 AI agents.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        {
            "contract_meta": {
                "format":      str,   "consensusdocs" | "aia" | "unknown"
                "total_pages": int,
                "pdf_path":    str,
            },
            "pages":    {page_number: text, ...},
            "sections": [list of section dicts],
        }

    Returns a dict with empty pages/sections lists on failure — never raises.
    """
    result = {
        "contract_meta": {
            "format": "unknown",
            "total_pages": 0,
            "pdf_path": str(pdf_path),
        },
        "pages": {},
        "sections": [],
    }

    if not pdf_path:
        return result

    # Step 1: Extract raw page text
    pages = extract_pages(pdf_path)
    if not pages:
        print(f"WARNING: No text extracted from '{pdf_path}'.")
        return result

    # Step 2: Detect format using first 3 pages
    first_three = {k: v for k, v in pages.items() if k <= 3}
    contract_format = detect_format(first_three)

    # Step 3: Detect and group sections
    sections = detect_sections(pages, contract_format)

    # Assemble output
    result["contract_meta"]["format"] = contract_format
    result["contract_meta"]["total_pages"] = len(pages)
    result["pages"] = pages
    result["sections"] = sections

    return result


# ---------------------------------------------------------------------------
# Quick smoke test — run this file directly to verify against a sample PDF
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Accept an optional PDF path from the command line; otherwise use a placeholder
    test_pdf = sys.argv[1] if len(sys.argv) > 1 else "sample_contract.pdf"

    print(f"\n{'='*60}")
    print(f"  Kalb Contract Reviewer - Phase 1 Extraction Smoke Test")
    print(f"{'='*60}\n")

    # ── Test 1: detect_format with synthetic page text ──────────────────────
    print("--- Test 1: detect_format ---")

    fake_cd_pages = {1: "This ConsensusDocs 230 Agreement for Construction.", 2: "", 3: ""}
    fmt = detect_format(fake_cd_pages)
    print(f"  ConsensusDocs sample -> format: '{fmt}'")   # expect consensusdocs
    assert fmt == "consensusdocs", f"FAIL: expected consensusdocs, got {fmt}"

    fake_aia_pages = {1: "AIA Document A201-2017 General Conditions of the Contract.", 2: "", 3: ""}
    fmt = detect_format(fake_aia_pages)
    print(f"  AIA sample           -> format: '{fmt}'")   # expect aia
    assert fmt == "aia", f"FAIL: expected aia, got {fmt}"

    fmt = detect_format({})
    print(f"  Empty input          -> format: '{fmt}'")   # expect unknown
    assert fmt == "unknown", f"FAIL: expected unknown, got {fmt}"

    print("  PASSED\n")

    # ── Test 2: detect_sections with synthetic ConsensusDocs text ───────────
    print("--- Test 2: detect_sections (ConsensusDocs synthetic) ---")

    synthetic_cd = {
        1: (
            "ARTICLE 6 TIME\n"
            "This article governs all time-related obligations.\n"
            "6.1 DATE OF COMMENCEMENT\n"
            "The work shall commence on the date specified in the notice to proceed.\n"
            "6.2 SUBSTANTIAL COMPLETION\n"
            "Substantial Completion means the stage in the Work when it is\n"
            "sufficiently complete in accordance with the Contract Documents.\n"
            "6.5 LIQUIDATED DAMAGES\n"
            "If the Contractor fails to achieve Substantial Completion, Owner\n"
            "may assess liquidated damages of $1,000 per day.\n"
            "6.5.1\n"
            "The parties agree this represents a genuine pre-estimate of damages.\n"
        ),
        2: (
            "ARTICLE 7 PAYMENTS\n"
            "This article governs all payment obligations.\n"
            "7.1 SCHEDULE OF VALUES\n"
            "Contractor shall submit a Schedule of Values within 10 days.\n"
        ),
    }

    secs = detect_sections(synthetic_cd, "consensusdocs")
    print(f"  Sections found: {len(secs)}")
    for s in secs:
        print(f"    [{s['section_id']}] {s['heading']}  (p{s['page_start']}–{s['page_end']}, {s['word_count']} words)")
    assert len(secs) >= 5, f"FAIL: expected >= 5 sections, got {len(secs)}"
    print("  PASSED\n")

    # ── Test 3: detect_sections with synthetic AIA text ─────────────────────
    print("--- Test 3: detect_sections (AIA synthetic) ---")

    synthetic_aia = {
        1: (
            "ARTICLE 1 GENERAL PROVISIONS\n"
            "This document governs general provisions.\n"
            "§ 1.1 Basic Definitions\n"
            "The Contract Documents consist of the Agreement and its exhibits.\n"
            "§ 1.2 Correlation and Intent\n"
            "The intent of the Contract Documents is to include all items\n"
            "necessary for the proper execution of the Work.\n"
        ),
        2: (
            "ARTICLE 9 PAYMENTS AND COMPLETION\n"
            "§ 9.3 Applications for Payment\n"
            "At least ten days before each progress payment date, the Contractor\n"
            "shall submit an Application for Payment.\n"
            "§ 9.8 Substantial Completion\n"
            "Substantial Completion is the stage at which the Work is ready for\n"
            "its intended use.\n"
        ),
    }

    secs_aia = detect_sections(synthetic_aia, "aia")
    print(f"  Sections found: {len(secs_aia)}")
    for s in secs_aia:
        print(f"    [{s['section_id']}] {s['heading']}  (p{s['page_start']}–{s['page_end']}, {s['word_count']} words)")
    assert len(secs_aia) >= 5, f"FAIL: expected >= 5 sections, got {len(secs_aia)}"
    print("  PASSED\n")

    # ── Test 4: Full extract_contract on real PDF (if supplied) ─────────────
    print(f"--- Test 4: extract_contract ('{test_pdf}') ---")
    if Path(test_pdf).exists():
        contract = extract_contract(test_pdf)
        print(f"  Format      : {contract['contract_meta']['format']}")
        print(f"  Total pages : {contract['contract_meta']['total_pages']}")
        print(f"  Sections    : {len(contract['sections'])}")
        if contract["sections"]:
            print(f"  First section: [{contract['sections'][0]['section_id']}] "
                  f"{contract['sections'][0]['heading']}")
        # Verify JSON serialisability
        json_str = json.dumps(contract, indent=2)
        print(f"  JSON output size: {len(json_str):,} chars")
        print("  PASSED\n")
    else:
        print(f"  Skipped — '{test_pdf}' not found. "
              f"Pass a PDF path as: python extractor.py path/to/contract.pdf\n")

    print("All available tests passed.")
