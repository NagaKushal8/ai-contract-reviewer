"""
extraction/quality_check.py

PDF extraction quality assessment for the Kalb Contract Reviewer.

Analyses the pages dict produced by extractor.extract_pages() to determine
whether the extracted text is likely complete and usable, or whether too many
pages were blank/unreadable (e.g. scanned image-only pages without OCR).

No AI calls. Pure Python only.
"""

from typing import Optional

# A page is considered empty / unreadable if its text is shorter than this
_EMPTY_PAGE_THRESHOLD = 50  # characters

# If this fraction of pages are empty the quality is flagged as "poor"
_POOR_QUALITY_THRESHOLD = 0.20  # 20 %


def check_quality(pages: dict) -> dict:
    """Assess the extraction quality of a pages dict.

    A page is considered empty/unreadable if its text contains fewer than
    50 characters (after whitespace stripping). If 20 % or more of all pages
    are empty the quality is rated "poor", otherwise "good".

    Args:
        pages: Dict of {page_number (int): text (str)} from extract_pages().
               An empty dict is valid input and returns a "good" result with
               zero pages (no warning is emitted for an empty contract).

    Returns:
        {
            "quality":     "good" | "poor",
            "total_pages": int,
            "empty_pages": [list of page numbers whose text is too short],
            "warning":     None | str,
        }
    """
    total_pages = len(pages)
    empty_pages: list = []

    for page_num, text in pages.items():
        # Treat None or whitespace-only text as empty
        if not text or len(text.strip()) < _EMPTY_PAGE_THRESHOLD:
            empty_pages.append(page_num)

    # Sort for deterministic output
    empty_pages.sort()

    # Calculate quality rating
    if total_pages == 0:
        # Edge case: no pages extracted at all — treat as good (no content, no warning)
        quality = "good"
        warning = None
    elif len(empty_pages) / total_pages >= _POOR_QUALITY_THRESHOLD:
        quality = "poor"
        warning = (
            "Some pages could not be read. "
            "Results may be incomplete for those pages."
        )
    else:
        quality = "good"
        warning = None

    return {
        "quality": quality,
        "total_pages": total_pages,
        "empty_pages": empty_pages,
        "warning": warning,
    }


def get_section_count_warning(sections: list) -> Optional[str]:
    """Return a warning string if too few sections were detected.

    A low section count usually means the format detection or regex
    patterns did not match the document structure correctly.

    Args:
        sections: List of section dicts from detect_sections().

    Returns:
        A warning string if fewer than 5 sections were found, else None.
    """
    if not sections or len(sections) < 5:
        return (
            "WARNING: Low section count detected. "
            "Format detection may have failed."
        )
    return None
