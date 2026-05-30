"""
Local HTML Preview Generator

Renders generated wikitext pages into a browseable static HTML site.
Provides a local mockup of what the wiki will look like, complete with
navigation, infobox styling, and cross-page links.

Usage:
    from foundry_parser.preview import generate_preview_site

    generate_preview_site(
        pages_dir=Path("wiki_pages/"),
        output_dir=Path("preview/"),
        navboxes_dir=Path("wiki_pages/navboxes/"),
    )
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


# ======================================================================
# Wikitext to HTML conversion (simplified)
# ======================================================================

def _wikitext_to_html(wikitext: str, all_pages: set[str]) -> str:
    """Convert wikitext to HTML with basic formatting support."""
    lines = wikitext.split("\n")
    output: list[str] = []
    in_table = False
    in_list = False
    table_lines: list[str] = []

    for line in lines:
        # Wiki tables
        if line.startswith("{|"):
            in_table = True
            table_lines = [line]
            continue
        if in_table:
            table_lines.append(line)
            if line.startswith("|}"):
                in_table = False
                output.append(_render_table(table_lines))
            continue

        # Headings
        heading_match = re.match(r"^(={2,6})\s*(.+?)\s*\1\s*$", line)
        if heading_match:
            if in_list:
                output.append("</ul>")
                in_list = False
            level = len(heading_match.group(1))
            text = _inline_format(heading_match.group(2), all_pages)
            output.append(f"<h{level}>{text}</h{level}>")
            continue

        # Bullet lists
        if line.startswith("* "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            text = _inline_format(line[2:], all_pages)
            output.append(f"  <li>{text}</li>")
            continue
        elif in_list and not line.startswith("*"):
            output.append("</ul>")
            in_list = False

        # Template calls (render as styled blocks)
        template_match = re.match(r"^\{\{(.+?)\}\}$", line.strip())
        if template_match:
            tmpl = template_match.group(1)
            output.append(_render_template_placeholder(tmpl, all_pages))
            continue

        # Categories (render as tags at bottom)
        cat_match = re.match(r"^\[\[Category:(.+?)\]\]$", line.strip())
        if cat_match:
            output.append(
                f'<span class="category-tag">{html.escape(cat_match.group(1))}</span>'
            )
            continue

        # Empty lines
        if not line.strip():
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append("")
            continue

        # Paragraph text
        text = _inline_format(line, all_pages)
        output.append(f"<p>{text}</p>")

    if in_list:
        output.append("</ul>")

    return "\n".join(output)


def _inline_format(text: str, all_pages: set[str]) -> str:
    """Apply inline wikitext formatting: bold, italic, links, templates."""
    # Bold + italic
    text = re.sub(r"'''''(.+?)'''''", r"<b><i>\1</i></b>", text)
    # Bold
    text = re.sub(r"'''(.+?)'''", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"''(.+?)''", r"<i>\1</i>", text)

    # Internal links [[Page|Display]] or [[Page]]
    def link_replace(m):
        full = m.group(1)
        if "|" in full:
            target, display = full.split("|", 1)
        else:
            target = display = full

        # File/Image links
        if target.startswith("File:") or target.startswith("Image:"):
            return _render_file_link(full)

        # Check if target exists in our pages
        safe_target = target.replace(" ", "_")
        if target in all_pages or safe_target in all_pages:
            href = safe_target + ".html"
            return f'<a href="{href}" class="wiki-link">{html.escape(display)}</a>'
        else:
            href = safe_target + ".html"
            return f'<a href="{href}" class="wiki-link redlink">{html.escape(display)}</a>'

    text = re.sub(r"\[\[(.+?)\]\]", link_replace, text)

    # Inline templates {{ItemLink|...}} etc
    def template_replace(m):
        content = m.group(1)
        parts = content.split("|")
        tmpl_name = parts[0].strip()
        if tmpl_name.lower() in ("itemlink", "item link"):
            item_name = parts[1].strip() if len(parts) > 1 else ""
            return f'<span class="item-link-preview">🔗 {html.escape(item_name)}</span>'
        elif tmpl_name.lower() == "main":
            target = parts[1].strip() if len(parts) > 1 else ""
            href = target.replace(" ", "_") + ".html"
            return f'<div class="hatnote">Main article: <a href="{href}">{html.escape(target)}</a></div>'
        return f'<span class="template-inline">{{{{{html.escape(content)}}}}}</span>'

    text = re.sub(r"\{\{(.+?)\}\}", template_replace, text)

    return text


def _render_file_link(content: str) -> str:
    """Render a [[File:...]] link as an image placeholder."""
    parts = content.split("|")
    filename = parts[0].replace("File:", "").replace("Image:", "")
    size = "200px"
    for p in parts[1:]:
        if p.endswith("px"):
            size = p
    return (
        f'<div class="file-placeholder" style="width:{size}">'
        f'<div class="file-icon">🖼️</div>'
        f'<div class="file-name">{html.escape(filename)}</div>'
        f'</div>'
    )


def _render_table(lines: list[str]) -> str:
    """Render a wiki table as HTML."""
    output = ['<table class="wikitable">']
    caption = ""
    current_row: list[str] = []
    in_row = False

    for line in lines:
        if line.startswith("{|"):
            # Extract classes
            classes = re.search(r'class="([^"]*)"', line)
            if classes:
                output[0] = f'<table class="{classes.group(1)}">'
            continue
        if line.startswith("|}"):
            if current_row:
                output.append("<tr>" + "".join(current_row) + "</tr>")
            break
        if line.startswith("|+"):
            caption = line[2:].strip()
            output.append(f"<caption>{html.escape(caption)}</caption>")
            continue
        if line.startswith("|-"):
            if current_row:
                output.append("<tr>" + "".join(current_row) + "</tr>")
            current_row = []
            continue
        if line.startswith("!"):
            # Header cells
            cells = line[1:].split("!!")
            for cell in cells:
                cell = cell.strip()
                # Handle style attributes
                if "|" in cell and not cell.startswith("[["):
                    attrs, content = cell.split("|", 1)
                    current_row.append(f"<th {attrs.strip()}>{html.escape(content.strip())}</th>")
                else:
                    current_row.append(f"<th>{html.escape(cell)}</th>")
            continue
        if line.startswith("|"):
            # Data cells
            cells = line[1:].split("||")
            for cell in cells:
                cell = cell.strip()
                if "|" in cell and not cell.startswith("[[") and not cell.startswith("<"):
                    # Check if it's attrs|content
                    possible_attrs, content = cell.split("|", 1)
                    if "=" in possible_attrs:
                        current_row.append(f"<td {possible_attrs.strip()}>{html.escape(content.strip())}</td>")
                    else:
                        current_row.append(f"<td>{html.escape(cell)}</td>")
                else:
                    current_row.append(f"<td>{html.escape(cell)}</td>")
            continue

    output.append("</table>")
    return "\n".join(output)


def _render_template_placeholder(template_str: str, all_pages: set[str]) -> str:
    """Render a template call as a styled placeholder block."""
    parts = template_str.split("|")
    tmpl_name = parts[0].strip()
    params = [p.strip() for p in parts[1:]]

    # Infobox templates — render as sidebar
    if tmpl_name.startswith("Infobox"):
        id_param = ""
        for p in params:
            if p.startswith("id="):
                id_param = p[3:]
        return (
            f'<div class="infobox-placeholder">'
            f'<div class="infobox-title">{html.escape(tmpl_name)}</div>'
            f'<div class="infobox-id">{html.escape(id_param)}</div>'
            f'<div class="infobox-note">Infobox renders from game data</div>'
            f'</div>'
        )

    # Recipe templates
    if tmpl_name.startswith("RecipeTable") or tmpl_name == "Recipe":
        id_param = ""
        for p in params:
            if p.startswith("id="):
                id_param = p[3:]
            elif not "=" in p:
                id_param = p
        return (
            f'<div class="recipe-placeholder">'
            f'<div class="recipe-title">📋 {html.escape(tmpl_name)}</div>'
            f'<div class="recipe-id">{html.escape(id_param)}</div>'
            f'</div>'
        )

    # Navbox templates
    if tmpl_name.startswith("Navbox"):
        return (
            f'<div class="navbox-placeholder">'
            f'<div class="navbox-title">🧭 {html.escape(tmpl_name)}</div>'
            f'</div>'
        )

    # DISPLAYTITLE
    if tmpl_name == "DISPLAYTITLE":
        return ""

    # Generic template
    return (
        f'<div class="template-placeholder">'
        f'{{{{{html.escape(template_str)}}}}}'
        f'</div>'
    )


# ======================================================================
# HTML page generation
# ======================================================================

_CSS = """
:root {
    --bg: #1a1a2e;
    --bg-surface: #16213e;
    --bg-elevated: #0f3460;
    --text: #e0e0e0;
    --text-muted: #a0a0a0;
    --accent: #4a9eff;
    --accent-dim: #2a5a9e;
    --border: #333;
    --link: #6cb4ff;
    --redlink: #ff6b6b;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 0;
}
.page-wrapper {
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem;
}
header {
    background: var(--bg-surface);
    border-bottom: 2px solid var(--accent);
    padding: 1rem 2rem;
    margin-bottom: 2rem;
}
header h1 { color: var(--accent); font-size: 1.3rem; }
header a { color: var(--link); text-decoration: none; }
header a:hover { text-decoration: underline; }
h1 { font-size: 2rem; margin: 1rem 0 0.5rem; color: #fff; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }
h2 { font-size: 1.5rem; margin: 1.5rem 0 0.5rem; color: #fff; border-bottom: 1px solid var(--border); padding-bottom: 0.2rem; }
h3 { font-size: 1.2rem; margin: 1.2rem 0 0.4rem; color: #ddd; }
h4, h5, h6 { font-size: 1rem; margin: 1rem 0 0.3rem; color: #ccc; }
p { margin: 0.5rem 0; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
a.redlink { color: var(--redlink); }
ul { margin: 0.5rem 0 0.5rem 1.5rem; }
li { margin: 0.2rem 0; }
.wikitable {
    border-collapse: collapse;
    margin: 1rem 0;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    width: auto;
}
.wikitable th, .wikitable td {
    border: 1px solid var(--border);
    padding: 6px 10px;
    text-align: left;
}
.wikitable th { background: var(--bg-elevated); font-weight: bold; }
.wikitable caption { font-weight: bold; padding: 6px; text-align: left; color: var(--accent); }
.infobox-placeholder {
    float: right;
    width: 280px;
    margin: 0 0 1rem 1.5rem;
    background: var(--bg-surface);
    border: 1px solid var(--accent-dim);
    border-radius: 6px;
    padding: 1rem;
    text-align: center;
}
.infobox-title { font-weight: bold; color: var(--accent); margin-bottom: 0.5rem; }
.infobox-id { font-family: monospace; font-size: 0.85rem; color: var(--text-muted); }
.infobox-note { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem; font-style: italic; }
.recipe-placeholder {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    padding: 0.8rem 1rem;
    margin: 0.5rem 0;
    border-radius: 4px;
}
.recipe-title { font-weight: bold; color: var(--accent); }
.recipe-id { font-family: monospace; font-size: 0.85rem; color: var(--text-muted); }
.navbox-placeholder {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    padding: 0.8rem;
    margin: 2rem 0 0.5rem;
    text-align: center;
    border-radius: 4px;
}
.navbox-title { color: var(--text-muted); }
.template-placeholder {
    background: var(--bg-surface);
    border: 1px dashed var(--border);
    padding: 0.5rem;
    margin: 0.3rem 0;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--text-muted);
}
.template-inline { font-family: monospace; font-size: 0.85rem; color: var(--accent); }
.item-link-preview { color: var(--link); }
.category-tag {
    display: inline-block;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 2px 8px;
    margin: 2px;
    font-size: 0.8rem;
    color: var(--text-muted);
}
.categories { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border); }
.hatnote { font-style: italic; color: var(--text-muted); margin: 0.5rem 0; padding-left: 1rem; }
.file-placeholder {
    display: inline-block;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1rem;
    text-align: center;
    margin: 0.5rem;
}
.file-icon { font-size: 2rem; }
.file-name { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem; }
.index-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 0.5rem;
    margin: 1rem 0;
}
.index-item { padding: 0.3rem 0; }
.index-section { margin: 1.5rem 0; }
.index-section h3 { color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.2rem; }
.stats { display: flex; gap: 2rem; margin: 1rem 0; flex-wrap: wrap; }
.stat-card { background: var(--bg-surface); border: 1px solid var(--border); border-radius: 6px; padding: 1rem 1.5rem; text-align: center; }
.stat-number { font-size: 2rem; font-weight: bold; color: var(--accent); }
.stat-label { font-size: 0.85rem; color: var(--text-muted); }
"""


def _page_html(title: str, body_html: str) -> str:
    """Wrap page content in a full HTML document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} — Foundry Wiki Preview</title>
    <style>{_CSS}</style>
</head>
<body>
    <header>
        <h1><a href="index.html">Foundry Wiki Preview</a></h1>
        <nav><a href="index.html">Home</a> · <a href="items_index.html">Items</a> · <a href="buildings_index.html">Buildings</a> · <a href="research_index.html">Research</a> · <a href="elements_index.html">Elements</a></nav>
    </header>
    <div class="page-wrapper">
        <h1>{html.escape(title)}</h1>
        {body_html}
    </div>
</body>
</html>"""


def _index_html(pages_by_type: dict[str, list[str]], total: int) -> str:
    """Generate the index/home page."""
    body = f"""
    <div class="stats">
        <div class="stat-card"><div class="stat-number">{total}</div><div class="stat-label">Total Pages</div></div>
        <div class="stat-card"><div class="stat-number">{len(pages_by_type.get('items', []))}</div><div class="stat-label">Items</div></div>
        <div class="stat-card"><div class="stat-number">{len(pages_by_type.get('buildings', []))}</div><div class="stat-label">Buildings</div></div>
        <div class="stat-card"><div class="stat-number">{len(pages_by_type.get('research', []))}</div><div class="stat-label">Research</div></div>
        <div class="stat-card"><div class="stat-number">{len(pages_by_type.get('elements', []))}</div><div class="stat-label">Elements</div></div>
    </div>
    <p>This is a local preview of the generated Foundry wiki pages. Templates render as placeholders showing what data they'll pull. Links between pages work within this preview.</p>
    """
    return _page_html("Foundry Wiki Preview", body)


def _type_index_html(page_type: str, pages: list[str]) -> str:
    """Generate an index page for a specific entity type."""
    items_html = []
    for page_title in sorted(pages):
        href = page_title.replace(" ", "_") + ".html"
        items_html.append(f'<div class="index-item"><a href="{href}">{html.escape(page_title)}</a></div>')

    body = f"""
    <div class="index-grid">
        {"".join(items_html)}
    </div>
    """
    title = page_type.replace("_", " ").title()
    return _page_html(f"{title} ({len(pages)})", body)


# ======================================================================
# Main export
# ======================================================================

def generate_preview_site(
    pages_dir: Path,
    output_dir: Path,
    verbose: bool = True,
) -> int:
    """
    Generate a static HTML preview site from generated wikitext pages.

    Args:
        pages_dir: Directory with generated .wikitext files (with subdirs).
        output_dir: Where to write the HTML site.
        verbose: Print progress.

    Returns:
        Number of pages generated.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # Collect all pages
    all_page_files: dict[str, Path] = {}  # title -> path
    pages_by_type: dict[str, list[str]] = {}

    for wikitext_file in pages_dir.rglob("*.wikitext"):
        title = wikitext_file.stem
        all_page_files[title] = wikitext_file

        # Determine type from parent directory
        parent = wikitext_file.parent.name
        if parent in ("items", "buildings", "research", "elements", "navboxes"):
            pages_by_type.setdefault(parent, []).append(title)
        else:
            pages_by_type.setdefault("other", []).append(title)

    all_page_titles = set(all_page_files.keys())
    log(f"Found {len(all_page_files)} pages to render")

    # Generate HTML for each page
    count = 0
    for title, wikitext_path in sorted(all_page_files.items()):
        wikitext = wikitext_path.read_text(encoding="utf-8")
        body_html = _wikitext_to_html(wikitext, all_page_titles)
        page_html = _page_html(title, body_html)

        safe_filename = title.replace(" ", "_") + ".html"
        (output_dir / safe_filename).write_text(page_html, encoding="utf-8")
        count += 1

    log(f"  Rendered {count} pages")

    # Generate index pages
    total = len(all_page_files)
    index_content = _index_html(pages_by_type, total)
    (output_dir / "index.html").write_text(index_content, encoding="utf-8")

    for page_type, pages in pages_by_type.items():
        if page_type == "other":
            continue
        idx_html = _type_index_html(page_type, pages)
        (output_dir / f"{page_type}_index.html").write_text(idx_html, encoding="utf-8")

    log(f"  Generated index pages")
    log(f"\n  Preview site: {output_dir}/index.html")
    log(f"  Open in browser to browse locally!")

    return count
