"""Report-card / transcript rendering (Phase 5, ADR 005).

HTML + CSS templates → WeasyPrint → PDF, in the WORKER only (never the API
process — WeasyPrint is CPU-heavy and pulls native libraries). The seam is
`html_to_pdf`: tests inject a fake (byte-producing function) so no test
needs WeasyPrint or its system libraries installed.

The HTML builders here are the Phase 5 default layout: one subject's result
rows per student. Richer school-configurable CSS layouts are a later-phase
concern (ADR 005: design changes are a deploy, not a migration).
"""

from decimal import Decimal
from typing import Any

from app.platform.logging import get_logger

log = get_logger("documents")


def html_to_pdf(html: str) -> bytes:
    """The one place WeasyPrint is imported. Raises RuntimeError with an
    actionable message when the worker image lacks it (ADR 005 consequence:
    system font/CSS support must be verified in the worker image)."""
    try:
        from weasyprint import HTML  # noqa: PLC0415 — lazy by design; see module docstring
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint is not installed in this image; PDF rendering is unavailable"
        ) from exc
    return HTML(string=html).write_pdf()


def _fmt(value: Decimal | None) -> str:
    return "—" if value is None else str(value)


def render_result_document_html(
    *,
    kind: str,
    school_name: str,
    student_name: str,
    subject_name: str,
    term_name: str,
    rows: list[dict[str, Any]],
) -> str:
    """One student's result document (report card or transcript) as HTML.

    `rows` items: {assessment_label, total, grade, position, flags}.
    """
    title = "Report Card" if kind == "report_card" else "Transcript"
    body_rows = "\n".join(
        f"<tr><td>{r['assessment_label']}</td><td>{_fmt(r['total'])}</td>"
        f"<td>{r['grade'] or '—'}</td><td>{r['position'] if r['position'] is not None else '—'}</td>"
        f"<td>{', '.join(r['flags']) or ''}</td></tr>"
        for r in rows
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: sans-serif; margin: 2cm; }}
h1 {{ font-size: 16pt; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #444; padding: 6px 10px; text-align: left; }}
th {{ background: #eee; }}
</style></head>
<body>
<h1>{school_name} — {title}</h1>
<p><strong>Student:</strong> {student_name}<br>
<strong>Subject:</strong> {subject_name}<br>
<strong>Term:</strong> {term_name}</p>
<table>
<thead><tr><th>Assessment</th><th>Total</th><th>Grade</th><th>Position</th><th>Flags</th></tr></thead>
<tbody>
{body_rows}
</tbody>
</table>
</body></html>"""
