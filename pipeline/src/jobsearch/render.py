"""Build the resume and cover letter as Word files, then PDFs (via LibreOffice).

Two resume layouts mirror Kojo's originals:
  technical — Arial; bold centered name; SUMMARY / EDUCATION / PROJECTS / EXPERIENCE /
              TECHNICAL SKILLS with ruled headings (resumes/…Technical_Resume.pdf)
  admin     — Arial (the original's Aptos isn't installed on the Mac); navy headings,
              accent rule under the name, hanging bullets (resumes/…Program_Administration_Resume.docx)

Facts that must be exact (name, contact, education, titles, employers, dates) come
from the master profile; the tailored content only supplies selection, order, and
wording. `fit_one_page` drops the least relevant bullets until the resume fits.
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from .content import CoverLetterContent, EntryBlock, ResumeContent, Template
from .profile import Entry, Profile

FONT = "Arial"
NAVY = RGBColor(0x14, 0x20, 0x30)


class RenderError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _new_document(*, margins: tuple[float, float, float, float], size: float) -> DocxDocument:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.top_margin, sec.bottom_margin, sec.left_margin, sec.right_margin = (Inches(m) for m in margins)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(size)
    rfonts = normal.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), FONT)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)
    return doc


def _para(
    doc: DocxDocument,
    runs: list[tuple[str, bool]],
    *,
    size: float | None = None,
    align: str = "left",
    before: float = 0,
    after: float = 0,
    color: RGBColor | None = None,
    hanging: tuple[float, float] | None = None,
) -> Paragraph:
    p = doc.add_paragraph()
    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER}[align]
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    if hanging:
        pf.left_indent, pf.first_line_indent = Inches(hanging[0]), Inches(-hanging[1])
    for text, bold in runs:
        r = p.add_run(_no_break_symbols(text))
        r.bold = bold or None
        if size:
            r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
    return p


def _no_break_symbols(text: str) -> str:
    """LibreOffice may wrap "C++" as "C+ / +"; word joiners (U+2060) keep it together."""
    return text.replace("C++", "C\u2060+\u2060+").replace("C#", "C\u2060#")


def _rule_below(p: Paragraph, *, color: str = "000000", size_eighths: int = 6, space: int = 1) -> None:
    ppr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (
        ("w:val", "single"),
        ("w:sz", str(size_eighths)),
        ("w:space", str(space)),
        ("w:color", color),
    ):
        bottom.set(qn(k), v)
    bdr.append(bottom)
    ppr.append(bdr)


def _entry_index(profile: Profile) -> dict[str, Entry]:
    return {e.id: e for e in [*profile.experience, *profile.projects]}


def _dates(e: Entry) -> str:
    return " – ".join(d for d in (e.start, e.end) if d)


def _contact_bits(profile: Profile) -> list[str]:
    c = profile.contact
    return [x for x in (c.location, c.phone, c.email) if x]


# ---------------------------------------------------------------------------
# Resume layouts
# ---------------------------------------------------------------------------


def _technical(content: ResumeContent, profile: Profile) -> DocxDocument:
    doc = _new_document(margins=(0.5, 0.5, 0.6, 0.6), size=10)
    entries = _entry_index(profile)

    def heading(text: str) -> None:
        _rule_below(_para(doc, [(text.upper(), True)], size=11, before=7, after=2))

    def bullets(block: EntryBlock) -> None:
        for b in block.bullets:
            _para(doc, [("•  " + b.text, False)], hanging=(0.22, 0.15), after=1)

    _para(doc, [(profile.contact.name, True)], size=20, align="center")
    _para(doc, [(" | ".join(_contact_bits(profile)), False)], align="center")
    if profile.contact.links:
        _para(doc, [(" | ".join(profile.contact.links), False)], align="center")

    if content.summary:
        heading("Summary")
        _para(doc, [(content.summary.text, False)])

    heading("Education")
    for ed in profile.education:
        loc = f", {ed.location}" if ed.location else ""
        _para(doc, [(ed.school, True), (f"{loc} – {ed.degree}, {ed.end}", False)], before=1)
        for d in ed.details:
            _para(doc, [(d, False)])
    if profile.certifications:
        _para(doc, [("Certifications: " + "; ".join(profile.certifications), False)])

    if content.projects:
        heading("Projects")
        for block in content.projects:
            e = entries[block.entry_id]
            meta = [
                x
                for x in (", ".join(e.stack) if e.stack else "", ", ".join(x for x in (e.org, e.end) if x))
                if x
            ]
            _para(doc, [(e.name or e.title or "", True), *[("  |  " + m, False) for m in meta]], before=3)
            bullets(block)

    if content.experience:
        heading("Experience")
        for block in content.experience:
            e = entries[block.entry_id]
            org = ", ".join(x for x in (e.org, e.location) if x)
            _para(
                doc,
                [(e.title or "", True), (f", {org}" if org else "", False), (f"  |  {_dates(e)}", False)],
                before=3,
            )
            bullets(block)

    if content.skills:
        heading("Technical Skills")
        for s in content.skills:
            _para(doc, [(f"{s.category}: ", True), (", ".join(s.items), False)])
    return doc


def _admin(content: ResumeContent, profile: Profile) -> DocxDocument:
    doc = _new_document(margins=(0.55, 0.52, 0.73, 0.73), size=9.5)
    entries = _entry_index(profile)

    def heading(text: str) -> None:
        _para(doc, [(text.upper(), True)], size=10, before=8, after=3, color=NAVY)

    def entry(title: str, *rest: str) -> None:
        _para(doc, [(title, True), *[(f"  |  {r}", False) for r in rest if r]], before=3, after=1)

    def bullets(block: EntryBlock) -> None:
        for b in block.bullets:
            _para(doc, [("•  " + b.text, False)], hanging=(0.22, 0.15), after=1)

    name = _para(doc, [(profile.contact.name, False)], size=17, align="center", after=6, color=NAVY)
    _rule_below(name, color="4F81BD", size_eighths=8, space=4)
    _para(doc, [("  |  ".join(_contact_bits(profile)), False)], align="center", after=1)
    if content.headline:
        _para(doc, [(content.headline, False)], align="center", after=1)

    heading("Education")
    for ed in profile.education:
        school = ", ".join(x for x in (ed.school, ed.location) if x)
        entry(school, ed.end)
        _para(doc, [(ed.degree, False)], after=2)

    if content.experience:
        heading("Relevant Experience")
        for block in content.experience:
            e = entries[block.entry_id]
            entry(e.title or "", ", ".join(x for x in (e.org, e.location) if x), _dates(e))
            bullets(block)

    if content.projects:
        heading("Selected Projects")
        for block in content.projects:
            e = entries[block.entry_id]
            entry(e.name or e.title or "", e.org or "", _dates(e))
            bullets(block)

    if content.skills:
        heading("Skills")
        runs: list[tuple[str, bool]] = []
        for i, s in enumerate(content.skills):
            runs += [(("  " if i else "") + f"{s.category}: ", True), (", ".join(s.items) + ".", False)]
        _para(doc, runs)
    return doc


def build_resume(content: ResumeContent, profile: Profile) -> DocxDocument:
    return {"technical": _technical, "admin": _admin}[content.template](content, profile)


# ---------------------------------------------------------------------------
# Cover letter
# ---------------------------------------------------------------------------


def build_cover_letter(
    content: CoverLetterContent,
    profile: Profile,
    *,
    company: str,
    template: Template,
    today: date | None = None,
) -> DocxDocument:
    doc = _new_document(margins=(0.9, 0.9, 1.0, 1.0), size=10.5)
    color = NAVY if template == "admin" else None
    name = _para(doc, [(profile.contact.name, True)], size=16, color=color)
    if template == "admin":
        _rule_below(name, color="4F81BD", size_eighths=8, space=4)
    _para(doc, [(" | ".join(_contact_bits(profile)), False)], size=9.5, after=14)
    _para(doc, [((today or date.today()).strftime("%B %-d, %Y"), False)], after=10)
    _para(doc, [("Hiring Team", False)])
    _para(doc, [(company, False)], after=12)
    _para(doc, [(content.greeting, False)], after=8)
    for line in content.paragraphs:
        p = _para(doc, [(line.text, False)], after=8)
        p.paragraph_format.line_spacing = 1.1
    _para(doc, [(content.closing, False)], before=4)
    _para(doc, [(profile.contact.name, False)], before=14)
    return doc


# ---------------------------------------------------------------------------
# PDF conversion and one-page fitting
# ---------------------------------------------------------------------------


def soffice_binary() -> str:
    path = os.environ.get("SOFFICE_BIN") or shutil.which("soffice")
    mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if not path and Path(mac).exists():
        path = mac
    if not path:
        raise RenderError("LibreOffice not found (brew install --cask libreoffice), or set SOFFICE_BIN.")
    return path


def to_pdf(docx_path: Path) -> Path:
    """Convert with LibreOffice in a throwaway profile (safe even if LibreOffice is open)."""
    with tempfile.TemporaryDirectory(prefix="jobsearch-lo-") as profile_dir:
        cmd = [
            soffice_binary(),
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(docx_path.parent),
            str(docx_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        except subprocess.TimeoutExpired as e:
            raise RenderError("LibreOffice timed out converting to PDF") from e
    pdf = docx_path.with_suffix(".pdf")
    if proc.returncode != 0 or not pdf.exists():
        raise RenderError(f"PDF conversion failed: {(proc.stderr or proc.stdout)[-300:]}")
    return pdf


def page_count(pdf: Path) -> int:
    return len(PdfReader(str(pdf)).pages)


def _drop_least_relevant(content: ResumeContent) -> bool:
    """Make the resume shorter by one step, cutting the least relevant material first.

    Blocks and bullets are ordered most-relevant-first by the tailoring step, so:
    1. drop trailing projects beyond the top two;
    2. else drop the last bullet of the block with the most bullets (later blocks win ties);
    3. else drop trailing project blocks, then trailing experience blocks (keeping one).
    Returns False when there's nothing left to cut.
    """
    if len(content.projects) > 2:
        content.projects.pop()
        return True
    blocks = [*content.experience, *content.projects]
    longest = max(blocks, key=lambda b: len(b.bullets), default=None)
    if longest is not None and len(longest.bullets) > 1:
        candidates = [b for b in blocks if len(b.bullets) == len(longest.bullets)]
        candidates[-1].bullets.pop()
        return True
    if content.projects:
        content.projects.pop()
        return True
    if len(content.experience) > 1:
        content.experience.pop()
        return True
    return False


def fit_one_page(
    content: ResumeContent, profile: Profile, out_dir: Path, stem: str
) -> tuple[ResumeContent, Path, Path]:
    """Render, and trim until the PDF is one page. Returns (final content, docx path, pdf path)."""
    work = copy.deepcopy(content)
    for _ in range(25):
        docx_path = out_dir / f"{stem}.docx"
        build_resume(work, profile).save(str(docx_path))
        pdf_path = to_pdf(docx_path)
        if page_count(pdf_path) <= 1 or not _drop_least_relevant(work):
            return work, docx_path, pdf_path
    return work, docx_path, pdf_path
