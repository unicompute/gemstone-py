#!/usr/bin/env python3
"""Build PDF books from the docs/ markdown files using a tiny local converter."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DOCS_DIR = Path(__file__).resolve().parent
ASSETS_DIR = DOCS_DIR / "assets"
PDF_DIR = DOCS_DIR / "pdf"
HTML_DIR = DOCS_DIR / ".pdf-build"
CSS_PATH = DOCS_DIR / "pdf-theme.css"


@dataclass(frozen=True)
class BuildTarget:
    slug: str
    title: str
    subtitle: str
    source_paths: tuple[Path, ...]
    cover_image: Path | None = None
    cover_only: bool = False


def _normalize_target(target: str, source_dir: Path, known_stems: frozenset[str] | None = None) -> str:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return target
    # Cross-document .md link — resolve to an internal anchor when all docs
    # are compiled into one HTML (companion / book builds).
    path = target.split("#")[0]
    fragment = target[len(path):]  # e.g. "#some-heading" or ""
    if path.endswith(".md"):
        stem = Path(path).stem
        if known_stems is not None and stem in known_stems:
            # Map "other-doc.md" → "#other-doc" so links work inside the
            # combined HTML / PDF without needing cross-file navigation.
            return f"#{stem}{fragment}"
    return (source_dir / target).resolve().as_uri()


def _inline(text: str, source_dir: Path, known_stems: frozenset[str] | None = None) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: (
            f'<img alt="{html.escape(m.group(1), quote=True)}" '
            f'src="{html.escape(_normalize_target(m.group(2), source_dir, known_stems), quote=True)}"/>'
        ),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: (
            f'<a href="{html.escape(_normalize_target(m.group(2), source_dir, known_stems), quote=True)}">'
            f"{m.group(1)}</a>"
        ),
        text,
    )
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = re.sub(r"\*([^*]+)\*", lambda m: f"<em>{m.group(1)}</em>", text)
    return text


def _render_table(lines: list[str], source_dir: Path, known_stems: frozenset[str] | None = None) -> str:
    rows = []
    for line in lines:
        stripped = line.strip().strip("|")
        rows.append([cell.strip() for cell in stripped.split("|")])
    header = rows[0]
    body = rows[2:]
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{_inline(cell, source_dir, known_stems)}</th>" for cell in header)
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        out.extend(f"<td>{_inline(cell, source_dir, known_stems)}</td>" for cell in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _render_markdown(
    text: str,
    source_dir: Path,
    anchor_prefix: str,
    known_stems: frozenset[str] | None = None,
) -> tuple[str, list[tuple[int, str, str]]]:
    lines = text.splitlines()
    i = 0
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    paragraph: list[str] = []
    list_stack: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{_inline(' '.join(part.strip() for part in paragraph), source_dir, known_stems)}</p>")
            paragraph = []

    def flush_lists() -> None:
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == r"\newpage":
            flush_paragraph()
            flush_lists()
            out.append('<div class="page-break"></div>')
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            flush_lists()
            i += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            flush_lists()
            fence_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                fence_lines.append(lines[i])
                i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(fence_lines))}</code></pre>")
            i += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_lists()
            level = len(heading_match.group(1))
            content = heading_match.group(2).strip()
            base_anchor = re.sub(r"[^a-z0-9]+", "-", content.lower()).strip("-")
            anchor = f"{anchor_prefix}-{base_anchor}" if base_anchor else anchor_prefix
            toc.append((level, content, anchor))
            out.append(f'<h{level} id="{anchor}">{_inline(content, source_dir, known_stems)}</h{level}>')
            i += 1
            continue

        if stripped.startswith("> "):
            flush_paragraph()
            flush_lists()
            quote_lines = [stripped[2:]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote_lines.append(lines[i].strip()[2:])
                i += 1
            out.append(f"<blockquote><p>{_inline(' '.join(quote_lines), source_dir, known_stems)}</p></blockquote>")
            continue

        if stripped.startswith("|") and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if sep.startswith("|") and re.fullmatch(r"[|\-: ]+", sep):
                flush_paragraph()
                flush_lists()
                table_lines = [lines[i], lines[i + 1]]
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                out.append(_render_table(table_lines, source_dir, known_stems))
                continue

        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        unordered_match = re.match(r"^-\s+(.*)$", stripped)
        if ordered_match or unordered_match:
            flush_paragraph()
            target = "ol" if ordered_match else "ul"
            if not list_stack or list_stack[-1] != target:
                flush_lists()
                list_stack.append(target)
                out.append(f"<{target}>")
            item_text = ordered_match.group(1) if ordered_match else unordered_match.group(1)
            out.append(f"<li>{_inline(item_text, source_dir, known_stems)}</li>")
            i += 1
            continue

        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    flush_lists()
    return "".join(out), toc


def _toc_html(entries: Iterable[tuple[int, str, str]]) -> str:
    parts = ['<section class="toc"><h2>Contents</h2><ul>']
    for level, title, anchor in entries:
        margin = 12 * (level - 1)
        parts.append(
            f'<li style="margin-left: {margin}px;"><a href="#{anchor}">{html.escape(title)}</a></li>'
        )
    parts.append("</ul></section>")
    return "".join(parts)


def _build_html(target: BuildTarget) -> Path:
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    body_parts: list[str] = []
    toc_entries: list[tuple[int, str, str]] = []

    # Stems of all source files in this build — used to rewrite cross-doc
    # .md links to internal #anchors so they work as clickable PDF links.
    known_stems: frozenset[str] = frozenset(p.stem for p in target.source_paths)

    for source_path in target.source_paths:
        rendered, toc = _render_markdown(
            source_path.read_text(encoding="utf-8"),
            source_path.parent,
            source_path.stem,
            known_stems,
        )
        toc_entries.extend(toc)
        # Emit a zero-height anchor at the file boundary so that cross-doc
        # links like #setup-guide and #user-manual resolve correctly.
        root_anchor = f'<div id="{source_path.stem}" style="height:0;margin:0;padding:0"></div>'
        body_parts.append(root_anchor + rendered)

    cover_html = ""
    if target.cover_image is not None:
        cover_html = (
            f'<img class="cover-art" src="{html.escape(target.cover_image.resolve().as_uri(), quote=True)}" '
            f'alt="{html.escape(target.title, quote=True)} cover art"/>'
        )

    if target.cover_only and target.cover_image is not None:
        title_page = f"""
        <section class="title-page cover-only">
          {cover_html}
        </section>
        """
    else:
        title_page = f"""
        <section class="title-page">
          <h1>{html.escape(target.title)}</h1>
          <div class="subtitle">{html.escape(target.subtitle)}</div>
          {cover_html}
          <div class="meta">Generated from the Markdown sources in gemstone-py/docs</div>
          <div class="meta">Assets are local SVG illustrations stored in the repository.</div>
        </section>
        """

    note = """
    <section class="doc-note">
      This PDF was generated locally from the Markdown sources in <code>docs/</code>.
      If you edit the source files, rerun <code>python docs/build_pdf_docs.py</code>.
    </section>
    """

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{html.escape(target.title)}</title>
  <link rel="stylesheet" href="{CSS_PATH.name}"/>
</head>
<body>
  <main>
    {title_page}
    {_toc_html(toc_entries)}
    {''.join(body_parts)}
    {note}
  </main>
</body>
</html>
"""

    html_path = HTML_DIR / f"{target.slug}.html"
    html_path.write_text(html_text, encoding="utf-8")
    css_dest = HTML_DIR / CSS_PATH.name
    css_dest.write_text(CSS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return html_path


def _render_pdf(target: BuildTarget) -> Path:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    html_path = _build_html(target)
    pdf_path = PDF_DIR / f"{target.slug}.pdf"
    subprocess.run(
        ["weasyprint", str(html_path), str(pdf_path)],
        cwd=str(HTML_DIR),
        check=True,
    )
    return pdf_path


def main() -> int:
    if HTML_DIR.exists():
        shutil.rmtree(HTML_DIR)
    funny_dir = DOCS_DIR / "funny-introduction"
    core_targets = (
        BuildTarget("setup-guide", "gemstone-py Setup Guide", "Installation, environment, and first successful login", (DOCS_DIR / "setup-guide.md",)),
        BuildTarget("user-manual", "gemstone-py User Manual", "Core APIs, transaction model, persistence helpers, and web integration", (DOCS_DIR / "user-manual.md",)),
        BuildTarget("examples-guide", "gemstone-py Examples Guide", "A tour of the examples tree with diagrams and screenshots", (DOCS_DIR / "examples-guide.md",)),
        BuildTarget("cookbook", "gemstone-py Cookbook", "Task-focused recipes for daily use", (DOCS_DIR / "cookbook.md",)),
        BuildTarget(
            "core-guides-companion",
            "gemstone-py Companion Manual",
            "Setup guide, user manual, examples guide, and cookbook in one volume",
            (
                DOCS_DIR / "README.md",
                DOCS_DIR / "setup-guide.md",
                DOCS_DIR / "user-manual.md",
                DOCS_DIR / "examples-guide.md",
                DOCS_DIR / "cookbook.md",
            ),
        ),
        BuildTarget(
            "funny-introduction-book",
            "A Funny but Thorough Introduction to gemstone-py",
            "A long-form user introduction with diagrams, screenshots, cartoons, and jokes",
            (
                funny_dir / "README.md",
                funny_dir / "part-01-why-gemstone-py-exists.md",
                funny_dir / "part-02-sessions-and-transactions.md",
                funny_dir / "part-03-persistent-root-and-friends.md",
                funny_dir / "part-04-queries-stores-and-logs.md",
                funny_dir / "part-05-web-apps-and-request-lifecycles.md",
                funny_dir / "part-06-concurrency-conflicts-and-retries.md",
                funny_dir / "part-07-benchmarks-releases-and-operator-survival.md",
            ),
            DOCS_DIR / "assets" / "cartoons" / "funny-introduction-cover.svg",
            True,
        ),
    )

    try:
        for target in core_targets:
            pdf_path = _render_pdf(target)
            print(pdf_path)
        return 0
    finally:
        if HTML_DIR.exists():
            shutil.rmtree(HTML_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
