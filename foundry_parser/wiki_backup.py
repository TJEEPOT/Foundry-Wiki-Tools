"""
MediaWiki Backup Tool

Downloads all pages from a MediaWiki site via the API, preserving
wikitext content and metadata for offline reference and diffing.

Usage:
    from foundry_parser.wiki_backup import WikiBackup

    wb = WikiBackup("https://wiki.foundry-game.com")
    wb.run_backup(Path("wiki_backup/"))
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# MediaWiki namespace IDs we care about
NAMESPACES = {
    0: "main",
    1: "Talk",
    2: "User",
    3: "User_talk",
    4: "Project",
    6: "File",
    8: "MediaWiki",
    10: "Template",
    12: "Help",
    14: "Category",
    828: "Module",
}


@dataclass
class PageInfo:
    """Metadata and content for a single wiki page."""
    title: str
    page_id: int
    namespace: int
    namespace_name: str
    content: str
    timestamp: str
    user: str
    comment: str
    revision_id: int
    content_length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "page_id": self.page_id,
            "namespace": self.namespace,
            "namespace_name": self.namespace_name,
            "timestamp": self.timestamp,
            "user": self.user,
            "comment": self.comment,
            "revision_id": self.revision_id,
            "content_length": self.content_length,
        }


@dataclass
class WikiBackup:
    """Downloads and saves all pages from a MediaWiki site."""

    site_url: str
    api_url: str = field(init=False)
    session: requests.Session = field(default_factory=requests.Session, repr=False)
    rate_limit: float = 0.5
    batch_size: int = 50

    def __post_init__(self) -> None:
        self.api_url = self.site_url.rstrip("/") + "/api.php"
        self.session.headers.update({
            "User-Agent": "FoundryWikiTools/0.1 (wiki backup; contact: foundry-wiki-tools@github)",
            "Accept": "application/json",
        })

    def _api_get(self, params: dict[str, Any], retries: int = 3) -> dict[str, Any]:
        """Make a GET request to the MediaWiki API with rate limiting and retries."""
        params["format"] = "json"
        time.sleep(self.rate_limit)
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self.session.get(self.api_url, params=params, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                last_err = e
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Request failed ({e}), retrying in {wait}s...")
                    time.sleep(wait)
        raise ConnectionError(
            f"Failed after {retries} attempts: {last_err}"
        ) from last_err

    # ------------------------------------------------------------------
    # Page enumeration
    # ------------------------------------------------------------------

    def list_all_pages(self, namespace: int = 0) -> list[dict[str, Any]]:
        """List all pages in a namespace using allpages API."""
        pages: list[dict[str, Any]] = []
        params: dict[str, Any] = {
            "action": "query",
            "list": "allpages",
            "apnamespace": namespace,
            "aplimit": "max",
        }
        while True:
            data = self._api_get(params)
            batch = data.get("query", {}).get("allpages", [])
            pages.extend(batch)
            if "continue" in data:
                params["apcontinue"] = data["continue"]["apcontinue"]
            else:
                break
        return pages

    # ------------------------------------------------------------------
    # Content retrieval
    # ------------------------------------------------------------------

    def fetch_page_content(self, page_ids: list[int]) -> list[PageInfo]:
        """Fetch full wikitext and metadata for a batch of page IDs."""
        results: list[PageInfo] = []
        for i in range(0, len(page_ids), self.batch_size):
            chunk = page_ids[i : i + self.batch_size]
            ids_str = "|".join(str(pid) for pid in chunk)
            data = self._api_get({
                "action": "query",
                "pageids": ids_str,
                "prop": "revisions",
                "rvprop": "content|timestamp|user|comment|ids",
                "rvslots": "main",
            })
            pages = data.get("query", {}).get("pages", {})
            for pid_str, page_data in pages.items():
                if "missing" in page_data:
                    continue
                revisions = page_data.get("revisions", [])
                if not revisions:
                    continue
                rev = revisions[0]
                content = rev.get("slots", {}).get("main", {}).get("*", "")
                ns = page_data.get("ns", 0)
                results.append(PageInfo(
                    title=page_data["title"],
                    page_id=page_data["pageid"],
                    namespace=ns,
                    namespace_name=NAMESPACES.get(ns, f"ns{ns}"),
                    content=content,
                    timestamp=rev.get("timestamp", ""),
                    user=rev.get("user", ""),
                    comment=rev.get("comment", ""),
                    revision_id=rev.get("revid", 0),
                    content_length=len(content),
                ))
        return results

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_filename(title: str) -> str:
        """Convert a page title to a safe filename.

        Strips the namespace prefix (e.g. "Template:Foo" -> "Foo") since
        files are already stored in namespace subdirectories, then replaces
        any characters that are unsafe on Windows/Linux filesystems.
        """
        # Strip namespace prefix if present (everything up to first colon)
        if ":" in title:
            name = title.split(":", 1)[1]
        else:
            name = title
        # Replace path separators and filesystem-unsafe characters
        name = name.replace("/", "_").replace("\\", "_")
        name = re.sub(r'[<>"|?*:]', "_", name)
        # Truncate if absurdly long
        if len(name) > 200:
            name = name[:200]
        # Avoid empty filenames
        if not name.strip("_ "):
            name = "_unnamed_"
        return name

    def _save_page(self, page: PageInfo, base_dir: Path) -> Path:
        """Save a single page's wikitext to disk."""
        ns_dir = base_dir / page.namespace_name
        ns_dir.mkdir(parents=True, exist_ok=True)
        filename = self._safe_filename(page.title) + ".wikitext"
        filepath = ns_dir / filename
        filepath.write_text(page.content, encoding="utf-8")
        return filepath

    # ------------------------------------------------------------------
    # Full backup
    # ------------------------------------------------------------------

    def run_backup(
        self,
        output_dir: Path,
        namespaces: list[int] | None = None,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        """Run a full wiki backup."""
        if namespaces is None:
            namespaces = list(NAMESPACES.keys())

        output_dir.mkdir(parents=True, exist_ok=True)

        def log(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)
            else:
                print(msg)

        log(f"Starting backup of {self.site_url}")
        log(f"Output: {output_dir}")

        # Phase 1: enumerate all pages across namespaces
        all_pages: list[dict[str, Any]] = []
        for ns in namespaces:
            ns_name = NAMESPACES.get(ns, f"ns{ns}")
            pages = self.list_all_pages(namespace=ns)
            if pages:
                log(f"  {ns_name} (ns:{ns}): {len(pages)} pages")
                all_pages.extend(pages)

        if not all_pages:
            log("No pages found!")
            return {"total_pages": 0}

        log(f"\nTotal pages to download: {len(all_pages)}")

        # Phase 2: fetch content in batches
        page_ids = [p["pageid"] for p in all_pages]
        all_page_info: list[PageInfo] = []
        downloaded = 0
        for i in range(0, len(page_ids), self.batch_size):
            chunk = page_ids[i : i + self.batch_size]
            batch_info = self.fetch_page_content(chunk)
            all_page_info.extend(batch_info)
            downloaded += len(batch_info)
            log(f"  Downloaded {downloaded}/{len(all_pages)} pages...")

        # Phase 3: save to disk
        log(f"\nSaving {len(all_page_info)} pages to disk...")
        ns_counts: dict[str, int] = {}
        page_index: list[dict[str, Any]] = []
        for page in all_page_info:
            filepath = self._save_page(page, output_dir)
            ns_counts[page.namespace_name] = ns_counts.get(page.namespace_name, 0) + 1
            entry = page.to_dict()
            entry["local_path"] = str(filepath.relative_to(output_dir))
            page_index.append(entry)

        # Phase 4: write index and metadata
        backup_meta = {
            "site_url": self.site_url,
            "backup_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_pages": len(all_page_info),
            "namespace_counts": ns_counts,
            "namespaces_backed_up": {
                str(ns): NAMESPACES.get(ns, f"ns{ns}") for ns in namespaces
            },
        }
        meta_path = output_dir / "backup_metadata.json"
        meta_path.write_text(
            json.dumps(backup_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        index_path = output_dir / "page_index.json"
        index_path.write_text(
            json.dumps(page_index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        titles_path = output_dir / "page_titles.txt"
        titles_path.write_text(
            "\n".join(sorted(p.title for p in all_page_info)) + "\n",
            encoding="utf-8",
        )

        log(f"\nBackup complete!")
        log(f"  Pages: {len(all_page_info)}")
        for ns_name, count in sorted(ns_counts.items()):
            log(f"    {ns_name}: {count}")
        log(f"  Index: {index_path}")
        log(f"  Metadata: {meta_path}")
        log(f"  Titles: {titles_path}")

        return backup_meta
