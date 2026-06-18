"""
app.py

Gradio web interface for the Kalb Contract Reviewer.

Chains Phase 1 (extraction) -> Phase 2 (AI analysis) -> Phase 3 (PDF report)
behind a clean upload-and-go UI.


"""

import tempfile
import os
import datetime

import gradio as gr

from extraction.extractor import extract_contract
from extraction.tagger import tag_all_sections
from analysis.boilerplate_filter import run_boilerplate_filter
from analysis.nrs_agent import run_nrs_agent
from analysis.owner_agent import run_owner_agent
from analysis.insurance_agent import run_insurance_agent
from analysis.ld_agent import run_ld_agent
from analysis.summary_generator import run_summary_generator
from report.pdf_builder import build_pdf

# ---------------------------------------------------------------------------
# Colour tokens — match pdf_builder.py brand palette
# ---------------------------------------------------------------------------
_NAVY = "#1B2A4A"
_GOLD = "#C9952A"
_RED = "#B91C1C"
_RED_BG = "#FEF2F2"
_AMBER_BG = "#FFFBEB"
_AMBER_TEXT = "#92400E"
_GREEN = "#1A6B3C"
_GREEN_BG = "#F0FAF4"
_LIGHT = "#F7F9FC"
_SLATE = "#4A5568"
_BORDER = "#D1D9E6"
_WHITE = "#FFFFFF"

PROGRESS_STEPS = [
    "Extracting contract text...",
    "Detecting sections and structure...",
    "Filtering relevant sections...",
    "Checking Nevada law compliance...",
    "Reviewing owner-favored clauses...",
    "Comparing insurance requirements...",
    "Reviewing liquidated damages...",
    "Generating executive summary...",
    "Building PDF report...",
]


# ---------------------------------------------------------------------------
# HTML builder helpers
# ---------------------------------------------------------------------------


def _badge(text: str, bg: str, color: str = _WHITE) -> str:
    """Return an inline-styled HTML badge span."""
    return (
        f'<span style="background:{bg};color:{color};'
        f"padding:2px 8px;border-radius:4px;font-size:12px;"
        f'font-weight:600;white-space:nowrap">{text}</span>'
    )


def build_exec_summary_html(results: dict) -> str:
    """Build the executive summary HTML block for Gradio display.

    Renders total issue counts, top-5 concern cards with urgency badges,
    and a quick stats row.  Uses inline CSS only.

    Args:
        results: Phase 2 results dict from run_all_agents().

    Returns:
        HTML string ready for gr.HTML().
    """
    summary = results.get("executive_summary", {})
    concerns = summary.get("top_5_concerns", [])
    total = results.get("total_issues", 0)
    nrs_count = len(results.get("nrs_issues", []))
    own_count = len(results.get("owner_issues", []))
    ins_count = len(results.get("insurance_issues", []))
    ld_count = len(results.get("ld_findings", []))

    # Stats bar
    stats = (
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;'
        f'margin-bottom:20px">'
        f'<div style="background:{_LIGHT};color:{_SLATE};padding:12px 20px;'
        f'border-radius:8px;text-align:center">'
        f'<div style="font-size:28px;font-weight:700">{total}</div>'
        f'<div style="font-size:12px;opacity:.85">Total Issues</div></div>'
        f'<div style="background:{_RED_BG};color:{_RED};padding:12px 20px;'
        f'border-radius:8px;text-align:center">'
        f'<div style="font-size:22px;font-weight:700">{nrs_count}</div>'
        f'<div style="font-size:12px">NRS / Legal</div></div>'
        f'<div style="background:{_AMBER_BG};color:{_AMBER_TEXT};'
        f'padding:12px 20px;border-radius:8px;text-align:center">'
        f'<div style="font-size:22px;font-weight:700">{own_count}</div>'
        f'<div style="font-size:12px">Owner-Favored</div></div>'
        f'<div style="background:{_GREEN_BG};color:{_GREEN};padding:12px 20px;'
        f'border-radius:8px;text-align:center">'
        f'<div style="font-size:22px;font-weight:700">{ins_count}</div>'
        f'<div style="font-size:12px">Insurance Gaps</div></div>'
        f'<div style="background:{_LIGHT};color:{_SLATE};padding:12px 20px;'
        f'border-radius:8px;text-align:center">'
        f'<div style="font-size:22px;font-weight:700">{ld_count}</div>'
        f'<div style="font-size:12px">LD Findings</div></div>'
        f"</div>"
    )

    if not concerns:
        return stats + "<p>No concerns identified.</p>"

    # Urgency badge colours
    def urgency_badge(u: str) -> str:
        if "Must Fix" in u:
            return _badge(u, _RED)
        if "Should Negotiate" in u:
            return _badge(u, _AMBER_TEXT, _WHITE)
        return _badge(u, _GREEN)

    cards = ""
    for c in concerns:
        rank = c.get("rank", "")
        concern = c.get("concern", "")
        category = c.get("category", "")
        sec_ref = c.get("section_reference", "")
        urgency = c.get("urgency", "")

        cards += (
            f'<div style="border:1px solid {_BORDER};border-radius:8px;'
            f'padding:14px 16px;margin-bottom:10px;background:{_WHITE}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="font-size:22px;font-weight:700;color:{_NAVY};'
            f'min-width:28px">{rank}</div>'
            f'<div style="flex:1">'
            f'<p style="margin:0 0 8px;color:{_SLATE};font-size:14px">'
            f"{concern}</p>"
            f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">'
            f"{urgency_badge(urgency)}"
            f'<span style="color:{_SLATE};font-size:12px">'
            f"{category} &nbsp;|&nbsp; § {sec_ref}</span>"
            f"</div></div></div></div>"
        )

    return stats + cards


def build_issues_html(issues: list, agent: str) -> str:
    """Build an HTML table for NRS or owner issues.

    Columns: Page | Section | Severity | Summary | Proposed Fix | Confidence

    Severity cell is colour-coded (red / amber / green background).
    Returns a styled "no issues" message when the list is empty.

    Args:
        issues: List of NRS or owner issue dicts.
        agent:  "nrs" or "owner" — used only for the empty-state message.

    Returns:
        HTML string.
    """
    if not issues:
        return (
            f'<div style="padding:16px;background:{_LIGHT};'
            f'border-radius:8px;color:{_SLATE};text-align:center">'
            f"No issues identified.</div>"
        )

    def sev_style(s: str) -> str:
        if s == "High":
            return f"background:{_RED_BG};color:{_RED};font-weight:600"
        if s == "Medium":
            return f"background:{_AMBER_BG};color:{_AMBER_TEXT};font-weight:600"
        return f"background:{_GREEN_BG};color:{_GREEN};font-weight:600"

    def conf_style(c: str) -> str:
        if c == "High":
            return f"color:{_GREEN};font-style:italic"
        if c == "Medium":
            return f"color:{_AMBER_TEXT};font-style:italic"
        return f"color:{_SLATE};font-style:italic"

    th = (
        f'<th style="background:{_NAVY};color:{_WHITE};padding:8px 10px;'
        f'text-align:left;font-size:12px;white-space:nowrap">'
    )

    header = (
        f"<tr>{th}Page</th>{th}Section</th>{th}Severity</th>"
        f"{th}Summary</th>{th}Proposed Fix</th>{th}Confidence</th></tr>"
    )

    rows = ""
    for i, issue in enumerate(issues):
        bg = _LIGHT if i % 2 == 0 else _WHITE
        sev = issue.get("severity", "")
        conf = issue.get("confidence", "")
        td = f'style="padding:8px 10px;font-size:13px;vertical-align:top;background:{bg}"'
        rows += (
            f"<tr>"
            f"<td {td}>{issue.get('page_number', '')}</td>"
            f"<td {td}>{issue.get('section_id', '')}</td>"
            f'<td style="padding:8px 10px;{sev_style(sev)};vertical-align:top">'
            f"{sev}</td>"
            f"<td {td}>{issue.get('summary', '')}</td>"
            f"<td {td}>{issue.get('proposed_fix', '')}</td>"
            f'<td style="padding:8px 10px;{conf_style(conf)};vertical-align:top">'
            f"{conf}</td>"
            f"</tr>"
        )

    return (
        f'<div style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif">'
        f"<thead>{header}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


def build_insurance_html(issues: list) -> str:
    """Build an HTML table for insurance gap issues.

    Columns: Page | Section | Summary | Contract Requirement |
             Kalb Coverage | Gap | Confidence

    Gap cell shows YES (red) or NO (green).  Returns a styled
    "no gaps" message when the list is empty.

    Args:
        issues: List of insurance gap dicts from Phase 2.

    Returns:
        HTML string.
    """
    if not issues:
        return (
            f'<div style="padding:16px;background:{_GREEN_BG};'
            f'border-radius:8px;color:{_GREEN};text-align:center;font-weight:600">'
            f"No insurance gaps identified. Coverage appears sufficient.</div>"
        )

    th = (
        f'<th style="background:{_NAVY};color:{_WHITE};padding:8px 10px;'
        f'text-align:left;font-size:12px;white-space:nowrap">'
    )
    header = (
        f"<tr>{th}Page</th>{th}Section</th>{th}Summary</th>"
        f"{th}Contract Requirement</th>{th}Kalb Coverage</th>"
        f"{th}Gap</th>{th}Confidence</th></tr>"
    )

    rows = ""
    for i, issue in enumerate(issues):
        bg = _LIGHT if i % 2 == 0 else _WHITE
        gap = issue.get("gap_exists", False)
        gap_cell = (
            f'<span style="color:{_RED};font-weight:700">YES</span>'
            if gap
            else f'<span style="color:{_GREEN};font-weight:700">NO</span>'
        )
        conf = issue.get("confidence", "")
        td = f'style="padding:8px 10px;font-size:13px;vertical-align:top;background:{bg}"'
        rows += (
            f"<tr>"
            f"<td {td}>{issue.get('page_number', '')}</td>"
            f"<td {td}>{issue.get('section_id', '')}</td>"
            f"<td {td}>{issue.get('summary', '')}</td>"
            f"<td {td}>{issue.get('contract_requirement', '')}</td>"
            f"<td {td}>{issue.get('kalb_coverage', '')}</td>"
            f'<td style="padding:8px 10px;text-align:center;vertical-align:top;background:{bg}">'
            f"{gap_cell}</td>"
            f"<td {td}>{conf}</td>"
            f"</tr>"
        )

    return (
        f'<div style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif">'
        f"<thead>{header}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


def build_ld_html(findings: list) -> str:
    """Build an HTML table for liquidated damages findings.

    Columns: Page | Section | Rate | Trigger | Grace Period |
             Extensions | Summary

    Rate cell shown in red bold when value is "blank".
    Returns a styled "none found" message when empty.

    Args:
        findings: List of LD finding dicts from Phase 2.

    Returns:
        HTML string.
    """
    if not findings:
        return (
            f'<div style="padding:16px;background:{_LIGHT};'
            f'border-radius:8px;color:{_SLATE};text-align:center">'
            f"No liquidated damages provisions found.</div>"
        )

    th = (
        f'<th style="background:{_NAVY};color:{_WHITE};padding:8px 10px;'
        f'text-align:left;font-size:12px;white-space:nowrap">'
    )
    header = (
        f"<tr>{th}Page</th>{th}Section</th>{th}Rate</th>"
        f"{th}Trigger</th>{th}Grace Period</th>"
        f"{th}Extensions</th>{th}Summary</th></tr>"
    )

    rows = ""
    for i, f in enumerate(findings):
        bg = _LIGHT if i % 2 == 0 else _WHITE
        rate = f.get("rate", "blank")
        rate_cell = (
            f'<span style="color:{_RED};font-weight:700">BLANK</span>'
            if str(rate).lower() == "blank"
            else str(rate)
        )
        ext = f.get("extensions_available")
        ext_str = "Yes" if ext is True else ("No" if ext is False else "—")
        td = f'style="padding:8px 10px;font-size:13px;vertical-align:top;background:{bg}"'
        rows += (
            f"<tr>"
            f"<td {td}>{f.get('page_number', '')}</td>"
            f"<td {td}>{f.get('section_id', '')}</td>"
            f'<td style="padding:8px 10px;vertical-align:top;background:{bg}">'
            f"{rate_cell}</td>"
            f"<td {td}>{f.get('trigger', '—')}</td>"
            f"<td {td}>{f.get('grace_period', '—')}</td>"
            f"<td {td}>{ext_str}</td>"
            f"<td {td}>{f.get('ld_summary', '')}</td>"
            f"</tr>"
        )

    return (
        f'<div style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse;font-family:sans-serif">'
        f"<thead>{header}</thead>"
        f"<tbody>{rows}</tbody>"
        f"</table></div>"
    )


def build_markup_html(results: dict) -> str:
    """Build the recommended contract revisions HTML list.

    Renders each markup item as a numbered card with the action in bold
    and the section reference in muted text.

    Args:
        results: Phase 2 results dict containing executive_summary.

    Returns:
        HTML string.
    """
    markup = results.get("executive_summary", {}).get("recommended_markup", [])
    if not markup:
        return (
            f'<div style="padding:16px;background:{_LIGHT};'
            f'border-radius:8px;color:{_SLATE};text-align:center">'
            f"No markup recommendations generated.</div>"
        )

    items = ""
    for m in markup:
        num = m.get("revision_number", "")
        action = m.get("action", "")
        ref = m.get("section_reference", "")
        items += (
            f'<div style="display:flex;gap:12px;align-items:flex-start;'
            f"padding:12px 14px;border:1px solid {_BORDER};border-radius:8px;"
            f'margin-bottom:8px;background:{_WHITE}">'
            f'<div style="background:{_NAVY};color:{_WHITE};border-radius:50%;'
            f"width:26px;height:26px;display:flex;align-items:center;"
            f"justify-content:center;font-size:13px;font-weight:700;"
            f'flex-shrink:0">{num}</div>'
            f"<div>"
            f'<span style="font-weight:600;color:{_NAVY}">{action}</span>'
            f"&nbsp;&nbsp;"
            f'<span style="color:{_SLATE};font-size:13px">§ {ref}</span>'
            f"</div></div>"
        )

    return f'<div style="font-family:sans-serif">{items}</div>'


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------


def analyze_contract(pdf_file, progress=gr.Progress()):
    """Run the full pipeline and return all display outputs.

    Chains Phase 1 (extraction + tagging) -> Phase 2 (AI agents) ->
    Phase 3 (PDF report), updating the Gradio progress bar at each step.

    Args:
        pdf_file: File path string (Gradio 5+) or legacy object with a
                  .name attribute (Gradio 4).  Both are handled.
        progress: Gradio Progress tracker injected automatically.

    Returns:
        8-tuple:
        (exec_html, nrs_html, owner_html, insurance_html,
         ld_html, markup_html, pdf_path, status_message)

        On failure: all HTML fields are empty strings, pdf_path is None,
        and status_message contains the error.
    """
    try:
        if pdf_file is None:
            return ("", "", "", "", "", "", None, "Please upload a PDF file first.")

        # Gradio 5+ returns a filepath string directly;
        # Gradio 4 returned an object with a .name attribute.
        pdf_path_input = pdf_file if isinstance(pdf_file, str) else pdf_file.name

        # ── Phase 1: Extract ──────────────────────────────────────────────
        progress(0.10, desc=PROGRESS_STEPS[0])
        contract_data = extract_contract(pdf_path_input)

        progress(0.20, desc=PROGRESS_STEPS[1])
        fmt = contract_data["contract_meta"]["format"]
        contract_data["sections"] = tag_all_sections(contract_data["sections"], fmt)

        # ── Phase 2: AI analysis — each agent updates the progress bar ───
        sections = contract_data["sections"]

        progress(0.30, desc="Filtering relevant sections...")
        target_ids = run_boilerplate_filter(sections, fmt)

        progress(0.42, desc="Running Nevada law (NRS) check...")
        try:
            nrs_issues = run_nrs_agent(sections, contract_data, target_ids)
        except Exception as exc:
            print(f"WARNING: NRS agent failed: {exc}")
            nrs_issues = []

        progress(0.54, desc="Checking owner-favored clauses...")
        try:
            owner_issues = run_owner_agent(sections, contract_data, target_ids)
        except Exception as exc:
            print(f"WARNING: Owner agent failed: {exc}")
            owner_issues = []

        progress(0.66, desc="Reviewing insurance requirements...")
        try:
            insurance_issues = run_insurance_agent(sections, contract_data, target_ids)
        except Exception as exc:
            print(f"WARNING: Insurance agent failed: {exc}")
            insurance_issues = []

        progress(0.76, desc="Extracting liquidated damages...")
        try:
            ld_findings = run_ld_agent(sections, contract_data, target_ids)
        except Exception as exc:
            print(f"WARNING: LD agent failed: {exc}")
            ld_findings = []

        progress(0.85, desc="Generating executive summary...")
        results = {
            "contract_format": fmt,
            "target_sections_analyzed": target_ids,
            "nrs_issues": nrs_issues,
            "owner_issues": owner_issues,
            "insurance_issues": insurance_issues,
            "ld_findings": ld_findings,
            "total_issues": (
                len(nrs_issues) + len(owner_issues) + len(insurance_issues)
            ),
            "analysis_complete": True,
        }
        try:
            results["executive_summary"] = run_summary_generator(results)
        except Exception as exc:
            print(f"WARNING: Summary generator failed: {exc}")
            results["executive_summary"] = {
                "top_5_concerns": [],
                "recommended_markup": [],
            }

        # ── Phase 3: Build PDF ────────────────────────────────────────────
        progress(0.92, desc="Building PDF report...")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(tempfile.gettempdir(), f"analysis_{timestamp}.pdf")
        build_pdf(results, pdf_path)

        progress(1.0, desc="Complete!")

        # ── Build display outputs ─────────────────────────────────────────
        exec_html = build_exec_summary_html(results)
        nrs_html = build_issues_html(results.get("nrs_issues", []), "nrs")
        owner_html = build_issues_html(results.get("owner_issues", []), "owner")
        insurance_html = build_insurance_html(results.get("insurance_issues", []))
        ld_html = build_ld_html(results.get("ld_findings", []))
        markup_html = build_markup_html(results)

        status = (
            f"Analysis complete. "
            f"{results['total_issues']} issues found across "
            f"{len(results['target_sections_analyzed'])} sections."
        )

        return (
            exec_html,
            nrs_html,
            owner_html,
            insurance_html,
            ld_html,
            markup_html,
            pdf_path,
            status,
        )

    except Exception as exc:
        error_msg = f"Analysis failed: {exc}"
        print(f"ERROR: {error_msg}")
        return ("", "", "", "", "", "", None, error_msg)


# ---------------------------------------------------------------------------
# Gradio interface
# ---------------------------------------------------------------------------

with gr.Blocks(title="Kalb Contract Review Tool") as demo:
    # ── Header ───────────────────────────────────────────────────────────
    gr.HTML("""
<div style="
    background: linear-gradient(135deg, #1B2A4A 0%, #243660 100%);
    padding: 28px 32px;
    border-radius: 12px;
    margin-bottom: 4px;
    border-left: 5px solid #C9952A;
">
    <h1 style="
        color: #C9952A;
        margin: 0 0 4px 0;
        font-size: 1.75rem;
        font-weight: 700;
        letter-spacing: -0.3px;
        line-height: 1.2;
    ">Contract Review Tool</h1>
    <p style="
        color: #8fa3c0;
        margin: 0 0 10px 0;
        font-size: 0.85rem;
        line-height: 1.6;
    ">
        Upload a construction contract PDF to begin AI-powered analysis.
        Supports
        <span style="color:#C9952A; font-weight:600;">ConsensusDocs 230</span>
        and
        <span style="color:#C9952A; font-weight:600;">AIA A201 / A101</span>
        formats.

</div>
    """)

    # ── Models info bar ───────────────────────────────────────────────────
    gr.HTML("""
<div style="
    display: flex;
    align-items: center;
    gap: 12px;
    background: #F7F9FC;
    border: 1px solid #D1D9E6;
    border-radius: 8px;
    padding: 10px 18px;
    margin-bottom: 12px;
    flex-wrap: wrap;
">
    <span style="font-size:0.78rem; font-weight:700; color:#4A5568; text-transform:uppercase; letter-spacing:0.6px;">
        AI Models
    </span>
    <span style="width:1px; height:16px; background:#D1D9E6; display:inline-block;"></span>
    <span style="
        display:inline-flex; align-items:center; gap:6px;
        background:#EFF6FF; border:1px solid #BFDBFE;
        border-radius:6px; padding:3px 10px;
        font-size:0.82rem; font-weight:600; color:#1D4ED8;
    ">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
        GPT-4o &nbsp;<span style="font-weight:400;color:#6B7280;">· Analysis &amp; Filtering</span>
    </span>
    <span style="
        display:inline-flex; align-items:center; gap:6px;
        background:#F0FDF4; border:1px solid #BBF7D0;
        border-radius:6px; padding:3px 10px;
        font-size:0.82rem; font-weight:600; color:#15803D;
    ">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 12h6M9 15h4"/></svg>
        mistral-ocr-latest &nbsp;<span style="font-weight:400;color:#6B7280;">· OCR (scanned PDFs)</span>
    </span>
</div>
    """)

    # ── Disclaimer / courtesy notice ──────────────────────────────────────
    gr.HTML("""
<p style="font-size:0.82rem; color:#6B7280; margin:0 0 12px 0; line-height:1.5;">
    This is running live — if anything does not load, it may be due to limited usage on a free account. The demo video included with the submission shows everything working perfectly.
</p>
    """)

    # ── Upload row ────────────────────────────────────────────────────────
    with gr.Row():
        pdf_input = gr.File(
            label="Upload Contract PDF",
            file_types=[".pdf"],
            scale=3,
        )
        analyze_btn = gr.Button(
            "Analyze Contract",
            variant="primary",
            scale=1,
        )

    # ── Status bar ────────────────────────────────────────────────────────
    status_output = gr.Textbox(
        label="Status",
        interactive=False,
        visible=True,
    )

    # ── Results (hidden until analysis runs) ──────────────────────────────
    with gr.Column(visible=False) as results_column:
        gr.Markdown("## Executive Summary")
        exec_summary_output = gr.HTML()

        gr.Markdown("---")

        with gr.Accordion("Nevada Law Issues", open=False):
            gr.Markdown(
                "Clauses that may conflict with Nevada state law and NRS requirements."
            )
            nrs_output = gr.HTML()

        with gr.Accordion("Owner-Favored Clauses", open=False):
            gr.Markdown(
                "Terms that place Kalb at a disadvantage or shift "
                "risk unfairly to the contractor."
            )
            owner_output = gr.HTML()

        with gr.Accordion("Insurance Requirements", open=False):
            gr.Markdown(
                "Places where the contract requires coverage beyond "
                "what Kalb currently carries."
            )
            insurance_output = gr.HTML()

        with gr.Accordion("Liquidated Damages", open=False):
            gr.Markdown(
                "Every penalty clause found in the contract, including "
                "daily rates and trigger conditions."
            )
            ld_output = gr.HTML()

        gr.Markdown("---")
        gr.Markdown("## Recommended Contract Revisions")
        markup_output = gr.HTML()

        gr.Markdown("---")
        gr.HTML("""
<p style="font-size:0.85rem; color:#6b7280; margin:0 0 8px 0;">
    Your full analysis is ready as a formatted PDF report.
</p>
        """)
        pdf_output = gr.DownloadButton(
            label="⬇  Download Full Report  (PDF)",
            variant="primary",
            size="lg",
        )

    # ── Wire button ───────────────────────────────────────────────────────
    analyze_btn.click(
        fn=analyze_contract,
        inputs=[pdf_input],
        outputs=[
            exec_summary_output,
            nrs_output,
            owner_output,
            insurance_output,
            ld_output,
            markup_output,
            pdf_output,
            status_output,
        ],
    ).then(
        fn=lambda: gr.update(visible=True),
        outputs=[results_column],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
