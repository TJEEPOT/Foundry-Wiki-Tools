"""
Wiki Diff Tool

Compares generated wiki pages against the existing wiki backup to produce
a report of new, changed, and unchanged pages. Generates unified diffs
for changed pages.

Usage:
    from foundry_parser.wiki_diff import diff_against_backup

    report = diff_against_backup(
        generated_dir=Path("wiki_pages/"),
        backup_dir=Path("wiki_backup/"),
        output_path=Path("diff_report/"),
    )
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PageDiff:
    """Represents the diff status of a single page."""
    title: str
    status: str  # "new", "changed", "unchanged", "removed"
    generated_path: Path | None = None
    backup_path: Path | None = None
    diff_lines: list[str] = field(default_factory=list)
    generated_size: int = 0
    backup_size: int = 0

    @property
    def size_delta(self) -> int:
        return self.generated_size - self.backup_size


@dataclass
class DiffReport:
    """Full report comparing generated pages against wiki backup."""
    timestamp: str
    new_pages: list[PageDiff] = field(default_factory=list)
    changed_pages: list[PageDiff] = field(default_factory=list)
    unchanged_pages: list[PageDiff] = field(default_factory=list)
    removed_pages: list[PageDiff] = field(default_factory=list)

    @property
    def total_generated(self) -> int:
        return len(self.new_pages) + len(self.changed_pages) + len(self.unchanged_pages)

    @property
    def total_backup(self) -> int:
        return len(self.changed_pages) + len(self.unchanged_pages) + len(self.removed_pages)

    def summary(self) -> str:
        lines = [
            f"Wiki Diff Report — {self.timestamp}",
            "=" * 50,
            f"  New pages:       {len(self.new_pages)}",
            f"  Changed pages:   {len(self.changed_pages)}",
            f"  Unchanged pages: {len(self.unchanged_pages)}",
            f"  Removed pages:   {len(self.removed_pages)}",
            f"  Total generated: {self.total_generated}",
            f"  Total in backup: {self.total_backup}",
        ]
        return "\n".join(lines)


def _normalize_wikitext(text: str) -> str:
    """Normalize wikitext for comparison (strip trailing whitespace, normalize newlines)."""
    lines = text.replace("\r\n", "\n").split("\n")
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in lines]
    # Remove trailing blank lines
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _find_backup_page(title: str, backup_dir: Path) -> Path | None:
    """Find a page in the backup directory by title.

    The backup stores pages as: namespace_dir/SafeFilename.wikitext
    Main namespace pages are in main/, templates in Template/, etc.
    """
    # Try main namespace first (most common)
    main_dir = backup_dir / "main"
    if main_dir.exists():
        # Try exact match
        candidate = main_dir / (title + ".wikitext")
        if candidate.exists():
            return candidate
        # Try with spaces replaced
        candidate = main_dir / (title.replace(" ", "_") + ".wikitext")
        if candidate.exists():
            return candidate

    # Try Module namespace
    if title.startswith("Module:"):
        module_dir = backup_dir / "Module"
        if module_dir.exists():
            module_name = title[7:]  # strip "Module:"
            candidate = module_dir / (module_name + ".wikitext")
            if candidate.exists():
                return candidate

    # Try Template namespace
    if title.startswith("Template:"):
        template_dir = backup_dir / "Template"
        if template_dir.exists():
            template_name = title[9:]  # strip "Template:"
            candidate = template_dir / (template_name + ".wikitext")
            if candidate.exists():
                return candidate

    return None


def _compute_diff(old_text: str, new_text: str, title: str) -> list[str]:
    """Compute unified diff between old and new text."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    return list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"backup/{title}",
        tofile=f"generated/{title}",
        lineterm="",
    ))


def diff_against_backup(
    generated_dir: Path,
    backup_dir: Path,
    output_path: Path | None = None,
    verbose: bool = True,
) -> DiffReport:
    """
    Compare all generated pages against the wiki backup.

    Args:
        generated_dir: Directory containing generated .wikitext files (can have subdirs).
        backup_dir: Directory containing the wiki backup (from backup-wiki command).
        output_path: If provided, write diff files and report here.
        verbose: Print progress.

    Returns:
        DiffReport with categorised page diffs.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = DiffReport(timestamp=timestamp)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # Collect all generated pages
    generated_pages: dict[str, Path] = {}
    for wikitext_file in generated_dir.rglob("*.wikitext"):
        # Use the filename (without extension) as the page title
        title = wikitext_file.stem
        generated_pages[title] = wikitext_file

    log(f"Found {len(generated_pages)} generated pages")

    # Collect all backup main-namespace pages for "removed" detection
    backup_main_pages: set[str] = set()
    main_dir = backup_dir / "main"
    if main_dir.exists():
        for f in main_dir.glob("*.wikitext"):
            backup_main_pages.add(f.stem)

    # Compare each generated page against backup
    for title, gen_path in sorted(generated_pages.items()):
        gen_text = gen_path.read_text(encoding="utf-8")
        gen_normalized = _normalize_wikitext(gen_text)

        backup_path = _find_backup_page(title, backup_dir)

        if backup_path is None:
            # New page
            diff = PageDiff(
                title=title,
                status="new",
                generated_path=gen_path,
                generated_size=len(gen_normalized),
            )
            report.new_pages.append(diff)
        else:
            # Existing page — compare
            backup_text = backup_path.read_text(encoding="utf-8")
            backup_normalized = _normalize_wikitext(backup_text)

            if gen_normalized == backup_normalized:
                diff = PageDiff(
                    title=title,
                    status="unchanged",
                    generated_path=gen_path,
                    backup_path=backup_path,
                    generated_size=len(gen_normalized),
                    backup_size=len(backup_normalized),
                )
                report.unchanged_pages.append(diff)
            else:
                diff_lines = _compute_diff(backup_normalized, gen_normalized, title)
                diff = PageDiff(
                    title=title,
                    status="changed",
                    generated_path=gen_path,
                    backup_path=backup_path,
                    diff_lines=diff_lines,
                    generated_size=len(gen_normalized),
                    backup_size=len(backup_normalized),
                )
                report.changed_pages.append(diff)

    # Detect removed pages (in backup but not generated)
    # Only check pages that look like entity pages (not meta/system pages)
    generated_titles = set(generated_pages.keys())
    for backup_title in sorted(backup_main_pages):
        if backup_title not in generated_titles:
            backup_path = main_dir / (backup_title + ".wikitext")
            if backup_path.exists():
                backup_text = backup_path.read_text(encoding="utf-8")
                diff = PageDiff(
                    title=backup_title,
                    status="removed",
                    backup_path=backup_path,
                    backup_size=len(backup_text),
                )
                report.removed_pages.append(diff)

    # Output
    log(report.summary())

    if output_path:
        output_path.mkdir(parents=True, exist_ok=True)

        # Write summary
        summary_path = output_path / "summary.txt"
        summary_path.write_text(report.summary() + "\n\n" + _detailed_summary(report), encoding="utf-8")

        # Write diffs for changed pages
        diffs_dir = output_path / "diffs"
        diffs_dir.mkdir(exist_ok=True)
        for page_diff in report.changed_pages:
            safe_name = page_diff.title.replace("/", "_").replace(" ", "_")
            diff_path = diffs_dir / (safe_name + ".diff")
            diff_path.write_text("\n".join(page_diff.diff_lines), encoding="utf-8")

        # Write lists
        (output_path / "new_pages.txt").write_text(
            "\n".join(p.title for p in report.new_pages) + "\n", encoding="utf-8"
        )
        (output_path / "changed_pages.txt").write_text(
            "\n".join(p.title for p in report.changed_pages) + "\n", encoding="utf-8"
        )
        (output_path / "removed_pages.txt").write_text(
            "\n".join(p.title for p in report.removed_pages) + "\n", encoding="utf-8"
        )

        # Write JSON report
        json_report = {
            "timestamp": timestamp,
            "counts": {
                "new": len(report.new_pages),
                "changed": len(report.changed_pages),
                "unchanged": len(report.unchanged_pages),
                "removed": len(report.removed_pages),
            },
            "new_pages": [p.title for p in report.new_pages],
            "changed_pages": [
                {"title": p.title, "size_delta": p.size_delta}
                for p in report.changed_pages
            ],
            "removed_pages": [p.title for p in report.removed_pages],
        }
        json_path = output_path / "report.json"
        json_path.write_text(
            json.dumps(json_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        log(f"\n  Report written to: {output_path}/")
        log(f"  Diffs: {len(report.changed_pages)} files in diffs/")

    return report


def _detailed_summary(report: DiffReport) -> str:
    """Generate a detailed text summary."""
    lines = []

    if report.new_pages:
        lines.append(f"\n--- NEW PAGES ({len(report.new_pages)}) ---")
        for p in sorted(report.new_pages, key=lambda x: x.title)[:50]:
            lines.append(f"  + {p.title} ({p.generated_size} bytes)")
        if len(report.new_pages) > 50:
            lines.append(f"  ... and {len(report.new_pages) - 50} more")

    if report.changed_pages:
        lines.append(f"\n--- CHANGED PAGES ({len(report.changed_pages)}) ---")
        for p in sorted(report.changed_pages, key=lambda x: x.title):
            delta = f"+{p.size_delta}" if p.size_delta >= 0 else str(p.size_delta)
            lines.append(f"  ~ {p.title} ({delta} bytes)")

    if report.removed_pages:
        lines.append(f"\n--- IN BACKUP BUT NOT GENERATED ({len(report.removed_pages)}) ---")
        lines.append("  (These may be hand-written pages, redirects, or disambiguation)")
        for p in sorted(report.removed_pages, key=lambda x: x.title)[:30]:
            lines.append(f"  - {p.title}")
        if len(report.removed_pages) > 30:
            lines.append(f"  ... and {len(report.removed_pages) - 30} more")

    return "\n".join(lines)
