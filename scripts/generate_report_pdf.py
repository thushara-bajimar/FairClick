"""Build FairClick_Project_Report.pdf from PROJECT_REPORT.md (single source of truth).

Supports the Markdown subset used in the report: #/##/### headings, paragraphs,
bullet and numbered lists, pipe tables, fenced code blocks, images
(![caption](path)), **bold**, *italic* and `code`. The first "# " heading
becomes the cover page; a table of contents and page numbers are generated.

    python scripts/generate_report_pdf.py
"""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "PROJECT_REPORT.md"
OUTPUT = ROOT / "FairClick_Project_Report.pdf"

NAVY = colors.HexColor("#0f172a")
TEAL = colors.HexColor("#0f766e")
GREY = colors.HexColor("#475569")
LIGHT = colors.HexColor("#f1f5f9")

base = getSampleStyleSheet()
STYLES = {
    "body": ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=10, leading=14.5, textColor=NAVY, spaceAfter=6),
    "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=TEAL, spaceBefore=6, spaceAfter=10),
    "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=6),
    "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.3, leading=10.5, textColor=NAVY),
    "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=8.3, leading=10.5, textColor=colors.white),
    "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=8.5, leading=11, textColor=GREY, alignment=TA_CENTER, spaceAfter=10),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=7.6, leading=9.5, textColor=NAVY, backColor=LIGHT, borderPadding=6, spaceAfter=8),
    "toc1": ParagraphStyle("toc1", fontName="Helvetica", fontSize=10, leading=15, textColor=NAVY),
    "toc2": ParagraphStyle("toc2", fontName="Helvetica", fontSize=9, leading=13, leftIndent=16, textColor=GREY),
}


def inline(text: str) -> str:
    """Convert inline Markdown to ReportLab mini-HTML (escaping everything else)."""
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#0f766e">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    return text


class ReportDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ("h1", "h2") and flowable.getPlainText() != "Table of Contents":
            level = 0 if flowable.style.name == "h1" else 1
            text = flowable.getPlainText()
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            self.notify("TOCEntry", (level, text, self.page, key))


def on_page(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(2 * cm, 1.2 * cm, "FairClick - Project Report")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
    canvas.restoreState()


def image_flowable(path: Path, caption: str, max_w: float, max_h: float = 17 * cm):
    img = Image(str(path))
    ratio = min(max_w / img.imageWidth, max_h / img.imageHeight, 1.0 if img.imageWidth < max_w else 10)
    img.drawWidth, img.drawHeight = img.imageWidth * ratio, img.imageHeight * ratio
    return KeepTogether([img, Paragraph(inline(caption), STYLES["caption"])])


def table_flowable(rows: list[list[str]], width: float):
    header, *body = rows
    data = [[Paragraph(inline(c), STYLES["cellh"]) for c in header]] + [[Paragraph(inline(c), STYLES["cell"]) for c in r] for r in body]
    t = Table(data, colWidths=[width / len(header)] * len(header), repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def parse(markdown: str, width: float) -> tuple[list, dict]:
    lines = markdown.splitlines()
    story: list = []
    cover: dict = {"title": "", "lines": []}
    i = 0
    bullets: list[str] = []
    numbered = False

    def flush_list():
        nonlocal bullets
        if bullets:
            items = [ListItem(Paragraph(inline(b), STYLES["body"]), leftIndent=12) for b in bullets]
            story.append(ListFlowable(items, bulletType="1" if numbered else "bullet", start="1" if numbered else None,
                                      bulletFontSize=8, leftIndent=14, bulletColor=TEAL))
            bullets = []

    # Cover block: everything before the first "## " heading.
    while i < len(lines) and not lines[i].startswith("## "):
        line = lines[i].strip()
        if line.startswith("# "):
            cover["title"] = line[2:]
        elif line and not line.startswith("---"):
            cover["lines"].append(line)
        i += 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_list()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            story.append(Preformatted("\n".join(block), STYLES["code"]))
        elif stripped.startswith("## "):
            flush_list()
            if story:
                story.append(PageBreak())
            story.append(Paragraph(inline(stripped[3:]), STYLES["h1"]))
        elif stripped.startswith("### "):
            flush_list()
            story.append(Paragraph(inline(stripped[4:]), STYLES["h2"]))
        elif stripped.startswith("#### "):
            flush_list()
            story.append(Paragraph(inline(stripped[5:]), STYLES["h3"]))
        elif stripped.startswith("!["):
            flush_list()
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
            if m and (ROOT / m.group(2)).exists():
                story.append(image_flowable(ROOT / m.group(2), m.group(1), width))
        elif stripped.startswith("|"):
            flush_list()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            story.append(table_flowable(rows, width))
            story.append(Spacer(1, 8))
            continue
        elif re.match(r"^(\s*)[-*] ", line):
            if numbered:
                flush_list()
            numbered = False
            bullets.append(re.sub(r"^\s*[-*] ", "", line))
        elif re.match(r"^\s*\d+\. ", line):
            if not numbered:
                flush_list()
            numbered = True
            bullets.append(re.sub(r"^\s*\d+\. ", "", line))
        elif not stripped or stripped.startswith("<!--"):
            flush_list()
        elif stripped.startswith(">"):
            flush_list()
            story.append(Paragraph(f'<font color="#475569"><i>{inline(stripped.lstrip("> "))}</i></font>', STYLES["body"]))
        else:
            flush_list()
            paragraph = [stripped]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^\s*([-*] |\d+\. |#|\||!\[|```|>)", lines[i + 1]):
                i += 1
                paragraph.append(lines[i].strip())
            story.append(Paragraph(inline(" ".join(paragraph)), STYLES["body"]))
        i += 1
    flush_list()
    return story, cover


def cover_page(cover: dict) -> list:
    title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=34, leading=40, textColor=TEAL, alignment=TA_CENTER)
    sub = ParagraphStyle("s", fontName="Helvetica", fontSize=13, leading=19, textColor=NAVY, alignment=TA_CENTER)
    small = ParagraphStyle("m", fontName="Helvetica", fontSize=10, leading=15, textColor=GREY, alignment=TA_CENTER)
    out = [Spacer(1, 5 * cm), Paragraph(inline(cover["title"]), title), Spacer(1, 0.8 * cm)]
    for idx, line in enumerate(cover["lines"]):
        out.append(Paragraph(inline(line.lstrip("*").rstrip("*")), sub if idx < 2 else small))
        out.append(Spacer(1, 0.3 * cm))
    out += [Spacer(1, 6 * cm), Paragraph(f"Generated {date.today():%d %B %Y}", small), PageBreak()]
    return out


def main() -> None:
    doc = ReportDoc(str(OUTPUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2.2 * cm,
                    title="FairClick Project Report", author="FairClick project team", subject="Agentic AI & Multi-Agent Systems")
    width = A4[0] - 4 * cm
    body, cover = parse(SOURCE.read_text(encoding="utf-8"), width)
    toc = TableOfContents()
    toc.levelStyles = [STYLES["toc1"], STYLES["toc2"]]
    story = cover_page(cover) + [Paragraph("Table of Contents", STYLES["h1"]), toc, PageBreak()] + body
    doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
