"""
report/pdf_builder.py

Simple text-first PDF report builder for the Kalb Contract Reviewer.

This version intentionally keeps the layout plain: title, metadata, section
headings, short issue blocks, and light separators.  It uses only minimal
brand colour accents and avoids decorative cards or marketing-style layout.
"""

import html

from reportlab.platypus import (
    Paragraph, Spacer, HRFlowable, SimpleDocTemplate, CondPageBreak,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.colors import HexColor, grey, black
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter

NAVY = HexColor("#1B2A4A")
GOLD = HexColor("#C9952A")
RED = HexColor("#B91C1C")
AMBER = HexColor("#92400E")
GREEN = HexColor("#1A6B3C")
SLATE = HexColor("#4A5568")
BORDER = HexColor("#D1D9E6")

TITLE = ParagraphStyle(
    "Title",
    fontName="Helvetica-Bold",
    fontSize=18,
    leading=22,
    textColor=NAVY,
    alignment=TA_LEFT,
    spaceAfter=4,
)
META = ParagraphStyle(
    "Meta",
    fontName="Helvetica",
    fontSize=9,
    leading=13,
    textColor=SLATE,
    spaceAfter=2,
)
H1 = ParagraphStyle(
    "H1",
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=17,
    textColor=NAVY,
    spaceBefore=6,
    spaceAfter=6,
)
H2 = ParagraphStyle(
    "H2",
    fontName="Helvetica-Bold",
    fontSize=10,
    leading=13,
    textColor=GOLD,
    spaceBefore=8,
    spaceAfter=3,
)
BODY = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=9.5,
    leading=13.5,
    textColor=black,
    spaceAfter=3,
)
SMALL = ParagraphStyle(
    "Small",
    fontName="Helvetica",
    fontSize=8.5,
    leading=12,
    textColor=SLATE,
    spaceAfter=2,
)


def _clean(value) -> str:
    """Return an escaped display string suitable for a Paragraph."""
    if value is None or value == "":
        return "-"
    return html.escape(str(value).strip()).replace("\n", "<br/>")


def _severity_markup(value) -> str:
    """Return a colourised severity label."""
    severity = str(value or "").strip().lower()
    if severity == "high":
        colour = RED.hexval()[2:]
    elif severity == "medium":
        colour = AMBER.hexval()[2:]
    else:
        colour = GREEN.hexval()[2:]
    label = _clean(value or "Low")
    return f'<font color="#{colour}"><b>{label}</b></font>'


def _line(label: str, value, style=BODY) -> Paragraph:
    """Build a simple label/value paragraph."""
    return Paragraph(f"<b>{html.escape(label)}:</b> {_clean(value)}", style)


def _rule(colour=BORDER, thickness=0.5) -> HRFlowable:
    """Return a thin horizontal separator."""
    return HRFlowable(
        width="100%",
        thickness=thickness,
        color=colour,
        spaceBefore=4,
        spaceAfter=6,
    )


_HALF_PAGE = 4.5 * inch  # if less than this remains, start a fresh page


def _section_heading(title: str) -> list:
    """Return a section heading that starts on a new page when less than
    half the page height remains, with gold rules above and below."""
    return [
        CondPageBreak(_HALF_PAGE),
        _rule(GOLD, 0.8),
        Paragraph(title, H1),
        _rule(GOLD, 0.8),
    ]


def _issue_meta(issue: dict, include_nrs: bool = False) -> Paragraph:
    """Build the first metadata line for an issue block."""
    pieces = [
        f"Page {_clean(issue.get('page_number'))}",
        f"Section {_clean(issue.get('section_id'))}",
        f"Severity {_severity_markup(issue.get('severity', ''))}",
        f"Confidence {_clean(issue.get('confidence'))}",
    ]
    if include_nrs:
        pieces.append(f"NRS {_clean(issue.get('nrs_citation'))}")
    return Paragraph(" | ".join(pieces), SMALL)


def _simple_issue_block(issue: dict, include_nrs: bool = False) -> list:
    """Render a plain text block for NRS/owner issues."""
    story = [
        _issue_meta(issue, include_nrs=include_nrs),
        _line("Heading", issue.get("heading")),
        _line("Summary", issue.get("summary")),
        _line("Why problem", issue.get("why_problem")),
        _line("Proposed fix", issue.get("proposed_fix")),
        _rule(),
    ]
    return story


def build_executive_summary(summary: dict) -> list:
    """Build a simple executive summary section."""
    story = _section_heading("Executive Summary")

    concerns = summary.get("top_5_concerns", [])
    if not concerns:
        story.append(Paragraph("No concerns identified.", BODY))
    else:
        for item in concerns:
            rank = _clean(item.get("rank"))
            concern = _clean(item.get("concern"))
            story.append(Paragraph(f"<b>{rank}.</b> {concern}", BODY))
            story.append(
                Paragraph(
                    " | ".join(
                        [
                            f"Urgency {_clean(item.get('urgency'))}",
                            f"Section {_clean(item.get('section_reference'))}",
                            f"Category {_clean(item.get('category'))}",
                        ]
                    ),
                    SMALL,
                )
            )
            story.append(Spacer(1, 4))

    return story


def build_recommended_revisions(summary: dict) -> list:
    """Build the recommended revisions section at the end of the report."""
    story = _section_heading("Recommended Contract Revisions")

    markup = summary.get("recommended_markup", [])
    if not markup:
        story.append(Paragraph("No markup recommendations.", BODY))
        return story

    for item in markup:
        num = _clean(item.get("revision_number"))
        action = _clean(item.get("action"))
        ref = _clean(item.get("section_reference"))
        story.append(Paragraph(f"<b>{num}.</b> {action}", BODY))
        story.append(Paragraph(f"Section {ref}", SMALL))
        story.append(Spacer(1, 4))

    return story


def build_nrs_table(issues: list) -> list:
    """Build the NRS issues section in plain text format."""
    story = _section_heading("Nevada / NRS Legal Issues")
    if not issues:
        story.append(Paragraph("No Nevada law issues identified.", BODY))
        return story

    for issue in issues:
        story.extend(_simple_issue_block(issue, include_nrs=True))
    return story


def build_owner_table(issues: list) -> list:
    """Build the owner-favored clauses section in plain text format."""
    story = _section_heading("Owner-Favored Clauses")
    if not issues:
        story.append(Paragraph("No owner-favored clauses identified.", BODY))
        return story

    for issue in issues:
        story.extend(_simple_issue_block(issue))
    return story


def build_insurance_table(issues: list) -> list:
    """Build the insurance section in plain text format."""
    story = _section_heading("Insurance Requirements")
    if not issues:
        story.append(Paragraph("No insurance gaps identified.", BODY))
        return story

    for issue in issues:
        gap_exists = "Yes" if issue.get("gap_exists") else "No"
        gap_colour = RED.hexval()[2:] if issue.get("gap_exists") else GREEN.hexval()[2:]
        story.append(
            Paragraph(
                " | ".join(
                    [
                        f"Page {_clean(issue.get('page_number'))}",
                        f"Section {_clean(issue.get('section_id'))}",
                        f'Gap <font color="#{gap_colour}"><b>{gap_exists}</b></font>',
                        f"Confidence {_clean(issue.get('confidence'))}",
                    ]
                ),
                SMALL,
            )
        )
        story.append(_line("Heading", issue.get("heading")))
        story.append(_line("Summary", issue.get("summary")))
        story.append(_line("Contract requirement", issue.get("contract_requirement")))
        story.append(_line("Kalb coverage", issue.get("kalb_coverage")))
        story.append(_line("Gap description", issue.get("gap_description")))
        story.append(_rule())
    return story


def build_ld_table(findings: list) -> list:
    """Build the liquidated damages section in plain text format."""
    story = _section_heading("Liquidated Damages")
    if not findings:
        story.append(Paragraph("No liquidated damages provisions found.", BODY))
        return story

    for finding in findings:
        story.append(
            Paragraph(
                " | ".join(
                    [
                        f"Page {_clean(finding.get('page_number'))}",
                        f"Section {_clean(finding.get('section_id'))}",
                        f"Rate {_clean(finding.get('rate'))}",
                        f"Confidence {_clean(finding.get('confidence'))}",
                    ]
                ),
                SMALL,
            )
        )
        story.append(_line("Heading", finding.get("heading")))
        story.append(_line("Trigger", finding.get("trigger")))
        story.append(_line("LD summary", finding.get("ld_summary")))
        story.append(_line("Cap", finding.get("cap")))
        story.append(_line("Grace period", finding.get("grace_period")))
        story.append(_line("Extensions available", finding.get("extensions_available")))
        story.append(_line("Sole remedy", finding.get("sole_remedy")))
        story.append(_rule())
    return story


def _add_page_decorations(canvas, doc):
    """Draw a simple header and page number."""
    canvas.saveState()
    page_w, page_h = letter

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(grey)
    canvas.drawRightString(
        page_w - 0.75 * inch,
        page_h - 0.5 * inch,
        "Kalb Contract Review Report",
    )

    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(
        0.75 * inch,
        page_h - 0.58 * inch,
        page_w - 0.75 * inch,
        page_h - 0.58 * inch,
    )

    canvas.drawCentredString(page_w / 2, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(results: dict, output_path: str) -> str:
    """Build a simple, text-first PDF report."""
    try:
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.8 * inch,
            bottomMargin=0.8 * inch,
        )

        fmt = str(results.get("contract_format", "")).upper() or "-"
        total_issues = results.get("total_issues", 0)
        sections_count = len(results.get("target_sections_analyzed", []))

        story = [
            Paragraph("Contract Review Report", TITLE),
            Paragraph("Kalb Construction + BLAK Development", META),
            Paragraph(
                " | ".join(
                    [
                        f"Contract format: {html.escape(fmt)}",
                        f"Total issues: {total_issues}",
                        f"Sections analyzed: {sections_count}",
                    ]
                ),
                META,
            ),
            _rule(GOLD, 1.0),
        ]

        story.extend(build_executive_summary(results.get("executive_summary", {})))
        story.extend(build_nrs_table(results.get("nrs_issues", [])))
        story.extend(build_owner_table(results.get("owner_issues", [])))
        story.extend(build_insurance_table(results.get("insurance_issues", [])))
        story.extend(build_ld_table(results.get("ld_findings", [])))
        story.extend(
            build_recommended_revisions(results.get("executive_summary", {}))
        )

        doc.build(
            story,
            onFirstPage=_add_page_decorations,
            onLaterPages=_add_page_decorations,
        )
        return output_path
    except Exception as exc:
        raise RuntimeError(f"PDF generation failed: {exc}") from exc
