from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "out" / "密立根油滴实验1.0_源程序.docx"


def source_paths():
    backend = sorted((ROOT / "normal/src/millikan_ai").rglob("*.py"))
    electron = sorted((ROOT / "normal/apps/desktop/electron").rglob("*.ts"))
    scripts = sorted((ROOT / "normal/apps/desktop/scripts").glob("*.mjs"))
    renderer = sorted(
        p for p in (ROOT / "normal/apps/desktop/src").rglob("*")
        if p.suffix in {".ts", ".tsx", ".css"}
        and not p.name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )
    return backend + electron + scripts + renderer


def collect_source():
    lines, files = [], []
    for path in source_paths():
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig").splitlines()
        files.append({"path": relative, "line_count": len(source),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        lines.extend((relative, i, line) for i, line in enumerate(source, 1))
    return lines, files


def enough(part):
    return len(part) >= 60 and sum(bool(row[2].strip()) for row in part) >= 52


def make_pages(lines):
    front, end = [], 0
    for _ in range(30):
        start = end
        while not enough(lines[start:end]):
            end += 1
        front.append((start, end))

    back_rev, start = [], len(lines)
    for _ in range(30):
        end = start
        while not enough(lines[start:end]):
            start -= 1
        back_rev.append((start, end))

    assert front[-1][1] <= start, "Source too short for disjoint front/back excerpts"
    pages = front + list(reversed(back_rev))
    assert len(pages) == 60
    for begin, end in pages:
        assert enough(lines[begin:end])
    return pages


def add_page_number(paragraph):
    run = paragraph.add_run()
    for kind, value in (("begin", None), ("instrText", "PAGE"), ("separate", None),
                        ("t", "1"), ("end", None)):
        if kind == "instrText":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = value
        elif kind == "t":
            el = OxmlElement("w:t")
            el.text = value
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        run._r.append(el)
    run.font.size = Pt(9)


def build_doc(lines, pages, font_pt):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Mm(297), Mm(210)
    sec.top_margin, sec.bottom_margin = Mm(20), Mm(16)
    sec.left_margin, sec.right_margin = Mm(17), Mm(14)
    sec.header_distance, sec.footer_distance = Mm(8), Mm(8)

    style = doc.styles["Normal"]
    style.font.name = "Noto Sans Mono CJK SC"
    style.font.size = Pt(font_pt)
    style.font.color.rgb = RGBColor(0, 0, 0)
    pf = style.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(font_pt * 1.27)

    head = sec.header.paragraphs[0]
    head.paragraph_format.tab_stops.add_tab_stop(Mm(179), WD_TAB_ALIGNMENT.RIGHT)
    run = head.add_run("密立根油滴实验 1.0  源程序")
    run.font.name, run.font.size = "Noto Sans CJK SC", Pt(9)
    head.add_run("\t")
    add_page_number(head)

    for page, (begin, end) in enumerate(pages, 1):
        p = doc.add_paragraph()
        if page != 1:
            p.paragraph_format.page_break_before = True
        p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(font_pt * 1.27)
        run = p.add_run("\n".join(item[2] for item in lines[begin:end]))
        run.font.name, run.font.size = "Noto Sans Mono CJK SC", Pt(font_pt)
    doc.core_properties.title = "密立根油滴实验 1.0 源程序"
    doc.core_properties.author = ""
    doc.save(OUTPUT)


def main():
    lines, files = collect_source()
    pages = make_pages(lines)
    font_pt = float(os.getenv("SOURCE_FONT_PT", "7.2"))
    build_doc(lines, pages, font_pt)
    manifest = {
        "version_ref": "normal-v1.0.0",
        "source_files": files,
        "total_source_lines": len(lines),
        "pages": [
            {"page": i, "source_line_count": end - begin,
             "nonblank_source_lines": sum(bool(row[2].strip()) for row in lines[begin:end]),
             "start": f"{lines[begin][0]}:{lines[begin][1]}",
             "end": f"{lines[end-1][0]}:{lines[end-1][1]}"}
            for i, (begin, end) in enumerate(pages, 1)
        ],
        "front_end_offset": pages[29][1],
        "back_start_offset": pages[30][0],
        "font_pt": font_pt,
    }
    path = OUTPUT.with_suffix(".manifest.json")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "source_files": len(files), "total_lines": len(lines), "pages": len(pages),
        "front_end": pages[29][1], "back_start": pages[30][0],
        "min_nonblank_per_page": min(p["nonblank_source_lines"] for p in manifest["pages"]),
        "output": str(OUTPUT)
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
