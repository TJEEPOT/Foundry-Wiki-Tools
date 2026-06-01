#!/usr/bin/env python3
"""
fetch_patch.py — Fetch a Foundry patch note from the Steam API and convert it to wiki format.

Note: The GID in a Steam web URL (e.g. /view/670589610075619682) is DIFFERENT from
the API GID. Use --list to find the correct API GID for the post you want.

Usage:
    # List recent posts with their API GIDs
    python fetch_patch.py --list

    # Fetch a specific post by API GID
    python fetch_patch.py 1805065414331275

    # With options
    python fetch_patch.py 1805065414331275 --page-name "Update 2.1 (Early Access)"

Options:
    --list              Show recent posts with their API GIDs, then exit
    --count N           Number of posts to show with --list (default: 5)
    --page-name NAME    Wiki page name (default: inferred from post title)
    --stage STAGE       e=Early Access, a=Alpha, b=Beta, r=Release  (default: e)
    --channel CHANNEL   st=Stable, ex=Experimental, m=Major         (default: st)
    --out-dir DIR       Output directory                             (default: wiki_pages/patches/)
    --dry-run           Print to stdout instead of writing a file
    --no-images         Skip downloading images

By default, images are downloaded and saved alongside the wikitext with wiki-ready
filenames (e.g. "Update 2.1 (Early Access) 01.jpg") ready to upload to the wiki.
Discord and Reddit links are left as <!-- TODO --> comments.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request, urlopen

APP_ID = 983870
API_URL = (
    f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    f"?appid={APP_ID}&maxlength=0&format=json"
)
STEAM_CLAN_IMAGE = "https://clan.akamai.steamstatic.com/images"

STAGE_LABELS = {"e": "Early Access", "a": "Alpha", "b": "Beta", "r": "Release"}


# ---------------------------------------------------------------------------
# Steam API
# ---------------------------------------------------------------------------

def fetch_news(count: int = 50) -> list[dict]:
    """Fetch recent news items from the Steam API."""
    url = API_URL + f"&count={count}"
    req = Request(url, headers={"User-Agent": "FoundryWikiTools/1.0"})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["appnews"]["newsitems"]


def find_item(gid: str, items: list[dict]) -> dict | None:
    return next((i for i in items if i["gid"] == gid), None)


# ---------------------------------------------------------------------------
# BB code → wikitext converter
# ---------------------------------------------------------------------------

def bbcode_to_wikitext(bbcode: str, page_name: str) -> str:
    """Convert Steam API BB code to MediaWiki wikitext."""
    text = bbcode

    # Strip boilerplate social-media footer that appears at the end of Steam posts.
    # Everything from "Follow us on socials" onwards is not patch content.
    m = re.search(r'follow us on socials?', text, re.IGNORECASE)
    if m:
        text = text[:m.start()].rstrip()

    # Expand Steam clan image placeholder
    text = text.replace("{STEAM_CLAN_IMAGE}", STEAM_CLAN_IMAGE)

    # --- Images (handle before other tags, to detect captions) ---
    # Two formats exist in the API:
    #   [img]URL[/img]
    #   [img src="URL"][/img]
    # Either may be immediately followed by [i]caption[/i]

    image_count = [0]

    def make_image(url: str, caption: str | None) -> str:
        image_count[0] += 1
        raw_ext = Path(url.split("?")[0]).suffix.lower()
        ext = raw_ext if raw_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ".jpg"
        name = f"{page_name} {image_count[0]:02d}{ext}"
        cap_part = f"|{caption.strip()}" if caption and caption.strip() else ""
        return f"\n[[File:{name}|frameless|center|1200px{cap_part}]]\n"

    CAPTION = r"(?:\[i\](.*?)\[/i\])?"

    def repl_img_plain(m: re.Match) -> str:
        return make_image(m.group(1).strip(), m.group(2))

    def repl_img_attr(m: re.Match) -> str:
        return make_image(m.group(1).strip(), m.group(2))

    text = re.sub(
        r"\[img\]([^\[]+)\[/img\]\s*" + CAPTION,
        repl_img_plain, text, flags=re.DOTALL,
    )
    text = re.sub(
        r'\[img\s+src="([^"]+)"\s*\]\s*\[/img\]\s*' + CAPTION,
        repl_img_attr, text, flags=re.DOTALL,
    )

    # --- Headings ---
    text = re.sub(r"\[h1\](.*?)\[/h1\]", lambda m: f"\n== {_strip_bb(m.group(1))} ==\n",
                  text, flags=re.DOTALL)
    text = re.sub(r"\[h2\](.*?)\[/h2\]", lambda m: f"\n=== {_strip_bb(m.group(1))} ===\n",
                  text, flags=re.DOTALL)
    text = re.sub(r"\[h3\](.*?)\[/h3\]", lambda m: f"\n==== {_strip_bb(m.group(1))} ====\n",
                  text, flags=re.DOTALL)

    # --- Paragraphs ---
    text = re.sub(r"\[p\](.*?)\[/p\]", r"\1\n\n", text, flags=re.DOTALL)

    # --- Lists (depth-aware, handles nested [list] correctly) ---
    text = _process_lists(text)

    # --- Inline formatting ---
    text = re.sub(r"\[b\](.*?)\[/b\]", r"'''\1'''", text, flags=re.DOTALL)
    text = re.sub(r"\[i\](.*?)\[/i\]", r"''\1''", text, flags=re.DOTALL)
    text = re.sub(r"\[u\](.*?)\[/u\]", r"<u>\1</u>", text, flags=re.DOTALL)
    text = re.sub(r"\[strike\](.*?)\[/strike\]", r"<s>\1</s>", text, flags=re.DOTALL)

    # --- Links ---
    # [url="URL"]label[/url] and [url=URL]label[/url]
    def repl_url(m: re.Match) -> str:
        href = (m.group(1) or m.group(2) or "").strip()
        href = unquote(href)
        label = _strip_bb(m.group(3)).strip()
        if not label or label == href:
            return href
        return f"[{href} {label}]"

    text = re.sub(
        r'\[url=(?:"([^"]+)"|([^\]]+))\](.*?)\[/url\]',
        repl_url, text, flags=re.DOTALL,
    )

    # --- YouTube embeds ---
    # [previewyoutube=VIDEO_ID;full][/previewyoutube]  →  plain external link
    text = re.sub(
        r'\[previewyoutube=([^;]+);[^\]]*\]\[/previewyoutube\]',
        lambda m: f"\n[https://www.youtube.com/watch?v={m.group(1).strip()} Watch on YouTube]\n",
        text,
    )

    # --- Dynamic links (Steam store links embedded as BB) ---
    text = re.sub(r'\[dynamiclink\s+href="([^"]+)"\]\[/dynamiclink\]', r"\1", text)

    # --- Remove any remaining BB tags ---
    # Pattern is intentionally narrow: tag names are pure alphanumeric with an
    # optional =value or space+attrs section.  This avoids accidentally stripping
    # wikitext [[File:...]] links (which contain ':') or external links like
    # [https://... text] (which contain '://').
    text = re.sub(r"\[/?[a-zA-Z][a-zA-Z0-9]*(?:[=\s][^\]]+)?\]", "", text)

    # --- Tidy whitespace ---
    text = re.sub(r" +\n", "\n", text)           # strip trailing spaces
    text = re.sub(r"\n{3,}", "\n\n", text)        # collapse 3+ newlines → 2
    # MediaWiki only renders nested bullets correctly when list items are on
    # consecutive lines (no blank line between them).  The pattern starts on
    # the * itself (not on the leading \n) so after each replacement the cursor
    # lands on the next *, letting re.sub fix all pairs in a single pass.
    text = re.sub(r"(\*[^\n]*)\n\n(?=\*)", r"\1\n", text)

    return text.strip()


def _strip_bb(s: str) -> str:
    """Remove all BB code tags from a string (for use inside headings etc.)."""
    return re.sub(r"\[/?[^\]]+\]", "", s).strip()


def _process_lists(text: str) -> str:
    """Convert BB code list tags to wikitext with correct nesting depth.

    [list]...[*] item [list][*] sub [/list][/list]
    becomes:
    * item
    ** sub
    """
    depth = 0
    strip_next = False  # strip leading whitespace from the part after [*]
    parts = re.split(r"(\[/?(?:o?list|\*)\])", text, flags=re.IGNORECASE)
    result = []
    for part in parts:
        low = part.lower()
        if low in ("[list]", "[olist]"):
            depth += 1
            strip_next = False
        elif low in ("[/list]", "[/olist]"):
            depth = max(0, depth - 1)
            strip_next = False
        elif low == "[*]":
            result.append("\n" + "*" * max(1, depth) + " ")
            strip_next = True  # strip the space BB code puts after [*]
        elif low == "[/*]":
            pass  # closing list-item tag — ignore
        else:
            if strip_next:
                part = part.lstrip(" \t")
                strip_next = False
            result.append(part)
    return "".join(result)


# ---------------------------------------------------------------------------
# Image extraction and download
# ---------------------------------------------------------------------------

_IMG_PATTERN = re.compile(
    r'\[img\]([^\[]+)\[/img\]'          # [img]URL[/img]
    r'|'
    r'\[img\s+src="([^"]+)"\s*\]\s*\[/img\]',  # [img src="URL"][/img]
)


def extract_image_urls(bbcode: str) -> list[str]:
    """Return image URLs from BB code in document order, with placeholder expanded."""
    expanded = bbcode.replace("{STEAM_CLAN_IMAGE}", STEAM_CLAN_IMAGE)
    urls = []
    for m in _IMG_PATTERN.finditer(expanded):
        url = (m.group(1) or m.group(2) or "").strip()
        if url:
            urls.append(url)
    return urls


def _steam_image_description(description: str, date: str, steam_url: str) -> str:
    """Return wikitext for the file description page of a Steam-sourced image."""
    return (
        "=={{int:filedesc}}==\n"
        "{{Information\n"
        f"|description={{{{en|1={description}}}}}\n"
        f"|date={date}\n"
        f"|source={steam_url}\n"
        "|author=Channel 3 Entertainment\n"
        "}}\n"
        "\n"
        "=={{int:license-header}}==\n"
        "The license for this file was set manually by the author. "
        "The following text describes the license:\n"
        "{{Attribution|Channel 3 Entertainment}}\n"
    )


def download_images(
    urls: list[str],
    page_name: str,
    out_dir: Path,
    date: str = "",
    steam_url: str = "",
) -> None:
    """Download Steam patch images and save with wiki-ready filenames.

    If *date* and *steam_url* are provided a companion ``.wikitext`` sidecar
    file is written alongside each image containing the file description page
    content (author, licence, source URL).  The batch-upload tool reads these
    sidecars automatically when uploading images.
    """
    if not urls:
        return
    print(f"Downloading {len(urls)} image(s)…")
    for i, url in enumerate(urls, 1):
        raw_ext = Path(url.split("?")[0]).suffix.lower()
        ext = raw_ext if raw_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ".jpg"
        dest = out_dir / f"{page_name} {i:02d}{ext}"
        sidecar = dest.with_suffix(".wikitext")
        if dest.exists():
            print(f"  [{i}/{len(urls)}] {dest.name} (already exists, skipping)")
        else:
            try:
                req = Request(url, headers={"User-Agent": "FoundryWikiTools/1.0"})
                with urlopen(req, timeout=30) as resp:
                    dest.write_bytes(resp.read())
                print(f"  [{i}/{len(urls)}] {dest.name}")
            except Exception as exc:
                print(f"  [{i}/{len(urls)}] WARNING: could not download {url}: {exc}")
                continue

        # Write sidecar description (skip if already present)
        if date and steam_url and not sidecar.exists():
            description = f"{page_name} image {i:02d}"
            sidecar.write_text(
                _steam_image_description(description, date, steam_url),
                encoding="utf-8",
            )


# ---------------------------------------------------------------------------
# Page name inference
# ---------------------------------------------------------------------------

def infer_page_name(title: str, stage: str) -> str:
    """
    Derive a wiki page name from the Steam post title.

    Examples:
        "Update 2.1 is Live Now!"   + stage=e  →  "Update 2.1 (Early Access)"
        "Update 4 Hotfix #2 …"      + stage=e  →  "Update 4 Hotfix 2 (Early Access)"
        "DevBlog #104 | …"                     →  "DevBlog 104"
    """
    stage_label = STAGE_LABELS.get(stage, "")

    m = re.match(r"(Update\s+[\d.]+(?:\s+Hotfix\s+#?[\d]+)?)", title, re.I)
    if m:
        base = re.sub(r"#", "", m.group(1)).strip()
        base = re.sub(r"\s+", " ", base)
        return f"{base} ({stage_label})" if stage_label else base

    m = re.match(r"(DevBlog)\s+#?(\d+)", title, re.I)
    if m:
        return f"DevBlog {m.group(2)}"

    sanitised = re.sub(r"[^\w\s\-.()']+", "", title).strip()
    return re.sub(r"\s+", " ", sanitised)


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def fmt_date(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).date().isoformat()


def build_page(item: dict, page_name: str, stage: str, channel: str) -> str:
    steam_url = item["url"]
    date = fmt_date(item["date"])
    body = bbcode_to_wikitext(item["contents"], page_name)

    # == Update 2.1 == heading: strip the stage suffix from the page name
    version = re.sub(r"\s*\([^)]+\)\s*$", "", page_name).strip()
    body = f"== {version} ==\n\n==== {item['title']} ====\n\n" + body

    patch_header = (
        f"{{{{Patch|stage={stage}|channel={channel}"
        f"|date={date}"
        f"|steam={steam_url}"
        f"|reddit=<!-- TODO: add Reddit link -->"
        f"|discord=<!-- TODO: add Discord link -->"
        f"}}}}"
    )

    return "\n".join([
        patch_header,
        "__NOTOC__",
        "",
        body,
        "",
        "== Navigation ==",
        "{{Navbox Patches}}",
        "",
    ])


def is_devblog(title: str) -> bool:
    """Return True if the post title looks like a Foundry Fridays DevBlog."""
    return bool(re.match(r"DevBlog\s+#?\d+", title, re.I))


def build_devblog_page(item: dict, page_name: str) -> str:
    """Build a wiki page for a Foundry Fridays DevBlog entry.

    Title format: "DevBlog #104 | Foundry Fridays: Work in Progress"
    Becomes:
        == Foundry Fridays: Work in Progress ==
    (The page is already titled DevBlog 104, so the subtitle makes a better heading.)
    """
    steam_url = item["url"]
    date = fmt_date(item["date"])
    body = bbcode_to_wikitext(item["contents"], page_name)

    # Use the subtitle as the main heading; fall back to the full title if no subtitle
    raw_title = item["title"]
    m = re.match(r"DevBlog\s+#?\d+\s*[|:]\s*(.*)", raw_title, re.I)
    heading = f"== {m.group(1).strip()} ==" if m else f"== {raw_title} =="

    body = heading + "\n\n" + body

    devblog_header = (
        f"{{{{Devblog"
        f"|date={date}"
        f"|steam={steam_url}"
        f"}}}}"
    )

    return "\n".join([
        devblog_header,
        "__NOTOC__",
        "",
        body,
        "",
        "== Navigation ==",
        "{{Navbox Devblogs}}",
        "",
    ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_list(count: int = 5) -> None:
    print(f"Fetching {count} most recent posts…")
    items = fetch_news(count)
    print()
    print(f"{'API GID':<20} {'Date':<12} Title")
    print("-" * 80)
    for item in items:
        date = fmt_date(item["date"])
        gid = item["gid"]
        title = item["title"][:55]
        print(f"{gid:<20} {date:<12} {title}")
    print()
    print(f"Usage: python fetch_patch.py <API GID>")


def cmd_fetch(args: argparse.Namespace) -> None:
    gid = args.gid

    # How many items to fetch: first try 50, then all if not found
    print("Fetching recent posts…")
    items = fetch_news(50)
    item = find_item(gid, items)

    if item is None:
        print(f"  Not in first 50, fetching all posts…")
        items = fetch_news(250)
        item = find_item(gid, items)

    if item is None:
        sys.exit(
            f"Error: could not find API GID {gid!r}.\n"
            "Run with --list to see available posts and their GIDs."
        )

    page_name = args.page_name or infer_page_name(item["title"], args.stage)
    devblog = is_devblog(item["title"])
    post_type = "DevBlog" if devblog else "Patch note"
    print(f"Title      : {item['title']}")
    print(f"Type       : {post_type}")
    print(f"Page name  : {page_name}")
    print(f"Date       : {fmt_date(item['date'])}")

    if devblog:
        content = build_devblog_page(item, page_name)
    else:
        content = build_page(item, page_name, args.stage, args.channel)

    if args.dry_run:
        print("\n" + "─" * 60)
        print(content)
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = page_name.replace(" ", "_").replace("/", "-")
    out_file = out_dir / f"{safe_name}.wikitext"
    out_file.write_text(content, encoding="utf-8")
    print(f"Written    : {out_file}")

    if not getattr(args, "no_images", False):
        image_urls = extract_image_urls(item["contents"])
        download_images(
            image_urls, page_name, out_dir,
            date=fmt_date(item["date"]),
            steam_url=item["url"],
        )
    else:
        img_count = len(re.findall(r"\[\[File:", content))
        if img_count:
            print(f"Images     : {img_count} placeholder(s) — skipped (--no-images)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a Foundry Steam patch note and convert it to wiki format.",
    )
    parser.add_argument(
        "gid", nargs="?", default=None,
        help="Steam API GID of the post (use --list to find it)",
    )
    parser.add_argument("--list", action="store_true", help="List recent posts and exit")
    parser.add_argument("--count", type=int, default=5, metavar="N",
                        help="Number of posts to show with --list (default: 5)")
    parser.add_argument("--page-name", default="", help="Wiki page name (inferred if omitted)")
    parser.add_argument("--stage",   default="e",  help="e/a/b/r (default: e)")
    parser.add_argument("--channel", default="st", help="st/ex/m (default: st)")
    parser.add_argument("--out-dir", default="wiki_pages/patches/")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-images", action="store_true",
        help="Skip downloading images (placeholders remain in the wikitext)",
    )
    args = parser.parse_args()

    if args.list:
        cmd_list(args.count)
        return

    if not args.gid:
        parser.error("Provide an API GID, or use --list to see available posts.")

    cmd_fetch(args)


if __name__ == "__main__":
    main()
        )
    else:
        img_count = len(re.findall(r"\[\[File:", content))
        if img_count:
            print(f"Images     : {img_count} placeholder(s) — skipped (--no-images)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a Foundry Steam patch note and convert it to wiki format.",
    )
    parser.add_argument(
        "gid", nargs="?", default=None,
        help="Steam API GID of the post (use --list to find it)",
    )
    parser.add_argument("--list", action="store_true", help="List recent posts and exit")
    parser.add_argument("--count", type=int, default=5, metavar="N",
                        help="Number of posts to show with --list (default: 5)")
    parser.add_argument("--page-name", default="", help="Wiki page name (inferred if omitted)")
    parser.add_argument("--stage",   default="e",  help="e/a/b/r (default: e)")
    parser.add_argument("--channel", default="st", help="st/ex/m (default: st)")
    parser.add_argument("--out-dir", default="wiki_pages/patches/")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-images", action="store_true",
        help="Skip downloading images (placeholders remain in the wikitext)",
    )
    args = parser.parse_args()

    if args.list:
        cmd_list(args.count)
        return

    if not args.gid:
        parser.error("Provide an API GID, or use --list to see available posts.")

    cmd_fetch(args)


if __name__ == "__main__":
    main()
