"""
Command-line interface for the Foundry parser.

Usage:
    python -m foundry_parser parse <game_dir> [--output <json_path>]
    python -m foundry_parser summary <game_dir>
    python -m foundry_parser lookup <game_dir> <type> <identifier>
    python -m foundry_parser generate-pages <game_dir> [--output <dir>]
    python -m foundry_parser generate-navboxes <game_dir> [--output <dir>]
    python -m foundry_parser generate-lua <game_dir> [--output <dir>]
    python -m foundry_parser diff-wiki [--pages <dir>] [--backup <dir>]
    python -m foundry_parser preview [--pages <dir>]
    python -m foundry_parser upload-wiki --username <user> --password <pass> [--url <url>]
    python -m foundry_parser batch-upload <game_dir> [--url <url>] [--commit] [--generate]
    python -m foundry_parser backup-wiki [--url <wiki_url>] [--output <dir>]

Batch upload phases (in order):
    1. Lua data modules   → Module:Data/*
    2. Rendering modules   → Module:Infobox, Module:ItemLink, etc.
    3. Template wrappers   → Template:Infobox Item, etc.
    4. Navbox templates    → Template:Navbox Items, etc.
    5. Content pages       → Item, Building, Research, Element, Exploration, Sky Platform pages
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

from .game_data import GameData


# ---------------------------------------------------------------------------
# Image description helpers
# ---------------------------------------------------------------------------

def _game_asset_description(filename: str, upload_date: str | None = None) -> str:
    """Generate a file description page for a game-asset image (item icons etc.).

    *filename* should be the bare filename, e.g. ``Item_Assembler_I.png``.
    The description is derived from the stem: ``Item_Assembler_I`` →
    ``"Assembler I"``.  The category is inferred from the filename prefix
    (``Item_`` → ``[[Category:Item Icon]]``).
    """
    stem = Path(filename).stem                         # "Item_Assembler_I"
    name = stem.replace("_", " ")                      # "Item Assembler I"
    # Strip known prefix for cleaner description
    for prefix in ("Item ", "Building "):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    today = upload_date or _date.today().isoformat()

    # Infer category from filename prefix
    category = ""
    if filename.startswith("Item_"):
        category = "\n[[Category:Item Icon]]"

    return (
        "=={{int:filedesc}}==\n"
        "{{Information\n"
        f"|description={{{{en|1={name}}}}}\n"
        f"|date={today}\n"
        "|source=FOUNDRY\n"
        "|author=Channel 3 Entertainment\n"
        "}}\n"
        "\n"
        "=={{int:license-header}}==\n"
        "The license for this file was set manually by the author. "
        "The following text describes the license:\n"
        "{{Attribution|Channel 3 Entertainment}}"
        f"{category}\n"
    )


def cmd_parse(args: argparse.Namespace) -> None:
    """Parse all game data and optionally export to JSON."""
    gd = GameData.from_game_dir(Path(args.game_dir))

    summary = gd.summary()
    total = sum(summary.values())
    print(f"\nParsed {total} entities across {len(summary)} categories:")
    for category, count in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {category}: {count}")

    if args.output:
        output_path = Path(args.output)
        gd.export_json(output_path)
        print(f"\nExported to {output_path}")


def cmd_summary(args: argparse.Namespace) -> None:
    """Print a quick summary of the game data."""
    gd = GameData.from_game_dir(Path(args.game_dir))
    summary = gd.summary()
    total = sum(summary.values())

    print(f"Foundry Game Data Summary")
    print(f"{'=' * 40}")
    print(f"Total entities: {total}")
    print()
    for category, count in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {category:30s} {count:>5d}")


def cmd_lookup(args: argparse.Namespace) -> None:
    """Look up a specific entity and print its details with cross-references."""
    gd = GameData.from_game_dir(Path(args.game_dir))

    entity_type = args.type.lower()
    identifier = args.identifier

    if entity_type == "item":
        item = gd.items.get(identifier)
        if not item:
            print(f"Item '{identifier}' not found.")
            return
        print(f"Item: {item.name} ({item.identifier})")
        print(f"  Stack size: {item.stack_size}")
        print(f"  Weight: {item.weight_grams}g")
        print(f"  Flags: {', '.join(item.flags) if item.flags else 'none'}")
        if item.category_id:
            cat = gd.item_categories.get(item.category_id)
            print(f"  Category: {cat.name if cat else item.category_id}")
        if item.can_be_traded:
            print(f"  Trade: buy={item.buy_price}, sell={item.sell_price}")

        # Cross-references
        produced_by = gd.recipes_producing(identifier)
        if produced_by:
            print(f"\n  Produced by {len(produced_by)} recipe(s):")
            for r in produced_by:
                inputs_str = " + ".join(
                    f"{i.amount}x {gd.item_name(i.identifier)}" for i in r.inputs
                )
                print(f"    {r.name}: {inputs_str} ({r.time_seconds}s)")

        used_in = gd.recipes_consuming(identifier)
        if used_in:
            print(f"\n  Used in {len(used_in)} recipe(s):")
            for r in used_in:
                outputs_str = " + ".join(
                    f"{o.amount}x {gd.item_name(o.identifier)}" for o in r.outputs
                )
                print(f"    {r.name} -> {outputs_str}")

        unlocked_by = gd.research_unlocking(identifier)
        if unlocked_by:
            print(f"\n  Unlocked by research:")
            for res in unlocked_by:
                print(f"    {res.name}")

        building = gd.building_for_item(identifier)
        if building:
            print(f"\n  Places building: {gd.building_name(building.identifier)}")
            print(f"    Size: {building.size['x']}x{building.size['y']}x{building.size['z']}")
            print(f"    Type: {building.type}")

    elif entity_type == "building":
        building = gd.buildings.get(identifier)
        if not building:
            print(f"Building '{identifier}' not found.")
            return
        name = gd.building_name(identifier)
        print(f"Building: {name} ({building.identifier})")
        print(f"  Type: {building.type}")
        print(f"  Size: {building.size['x']}x{building.size['y']}x{building.size['z']}")
        if building.energy_consumption_kw:
            print(f"  Power: {building.energy_consumption_kw} kW")
        if building.producer_recipe_tags:
            print(f"  Recipe tags: {', '.join(building.producer_recipe_tags)}")

        craftable = gd.recipes_for_building(identifier)
        if craftable:
            print(f"\n  Can craft {len(craftable)} recipe(s):")
            for r in craftable[:20]:
                print(f"    {r.name}")
            if len(craftable) > 20:
                print(f"    ... and {len(craftable) - 20} more")

    elif entity_type == "recipe":
        recipe = gd.recipes.get(identifier)
        if not recipe:
            print(f"Recipe '{identifier}' not found.")
            return
        print(f"Recipe: {recipe.name} ({recipe.identifier})")
        print(f"  Time: {recipe.time_seconds}s")
        print(f"  Tags: {', '.join(recipe.tags)}")
        print(f"  Inputs:")
        for inp in recipe.inputs:
            print(f"    {inp.amount}x {gd.item_name(inp.identifier)}")
        for inp in recipe.elemental_inputs:
            print(f"    {inp.amount}L {gd.element_name(inp.identifier)}")
        print(f"  Outputs:")
        for out in recipe.outputs:
            print(f"    {out.amount}x {gd.item_name(out.identifier)}")
        for out in recipe.elemental_outputs:
            print(f"    {out.amount}L {gd.element_name(out.identifier)}")

    elif entity_type == "research":
        res = gd.research.get(identifier)
        if not res:
            print(f"Research '{identifier}' not found.")
            return
        print(f"Research: {res.name} ({res.identifier})")
        print(f"  Description: {res.description}")
        print(f"  Seconds per science item: {res.seconds_per_science_item}")
        print(f"  Costs:")
        for cost in res.costs:
            print(f"    {cost.amount}x {gd.item_name(cost.identifier)}")
        if res.dependencies:
            print(f"  Prerequisites:")
            for dep in res.dependencies:
                dep_res = gd.research.get(dep)
                print(f"    {dep_res.name if dep_res else dep}")
        if res.crafting_unlocks:
            print(f"  Unlocks recipes:")
            for unlock in res.crafting_unlocks:
                recipe = gd.recipes.get(unlock)
                print(f"    {recipe.name if recipe else unlock}")

    else:
        print(f"Unknown type '{entity_type}'. Use: item, building, recipe, research")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="foundry_parser",
        description="Parse Foundry game data for wiki generation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse command
    p_parse = subparsers.add_parser("parse", help="Parse game data and export")
    p_parse.add_argument("game_dir", help="Path to Foundry game directory")
    p_parse.add_argument("--output", "-o", help="Output JSON file path")

    # summary command
    p_summary = subparsers.add_parser("summary", help="Print data summary")
    p_summary.add_argument("game_dir", help="Path to Foundry game directory")

    # lookup command
    p_lookup = subparsers.add_parser("lookup", help="Look up a specific entity")
    p_lookup.add_argument("game_dir", help="Path to Foundry game directory")
    p_lookup.add_argument("type", help="Entity type (item, building, recipe, research)")
    p_lookup.add_argument("identifier", help="Entity identifier")

    # generate-pages command
    p_pages = subparsers.add_parser(
        "generate-pages", help="Generate wiki page wikitext for all entities"
    )
    p_pages.add_argument("game_dir", help="Path to Foundry game directory")
    p_pages.add_argument(
        "--output",
        "-o",
        default="wiki_pages",
        help="Output directory for .wikitext files (default: wiki_pages/)",
    )

    # generate-navboxes command
    p_nav = subparsers.add_parser(
        "generate-navboxes", help="Generate navbox templates and research tree"
    )
    p_nav.add_argument("game_dir", help="Path to Foundry game directory")
    p_nav.add_argument(
        "--wiki-modules",
        default="wiki_modules",
        help="Directory for Template_Navbox_*.wikitext files (default: wiki_modules/)",
    )
    p_nav.add_argument(
        "--pages",
        default="wiki_pages",
        help="Directory for the Research Tree page (default: wiki_pages/)",
    )

    # generate-lua command
    p_lua = subparsers.add_parser(
        "generate-lua", help="Export game data as Lua modules for wiki"
    )
    p_lua.add_argument("game_dir", help="Path to Foundry game directory")
    p_lua.add_argument(
        "--output",
        "-o",
        default="lua_modules",
        help="Output directory for .lua files (default: lua_modules/)",
    )

    # diff-wiki command
    p_diff = subparsers.add_parser(
        "diff-wiki", help="Compare generated pages against wiki backup"
    )
    p_diff.add_argument(
        "--pages",
        default="wiki_pages",
        help="Generated pages directory (default: wiki_pages/)",
    )
    p_diff.add_argument(
        "--backup",
        default="wiki_backup",
        help="Wiki backup directory (default: wiki_backup/)",
    )
    p_diff.add_argument(
        "--output",
        "-o",
        default="diff_report",
        help="Output directory for diff report (default: diff_report/)",
    )

    # preview command
    p_preview = subparsers.add_parser(
        "preview", help="Generate a local HTML preview site"
    )
    p_preview.add_argument(
        "--pages",
        default="wiki_pages",
        help="Generated pages directory (default: wiki_pages/)",
    )
    p_preview.add_argument(
        "--output",
        "-o",
        default="preview",
        help="Output directory for HTML site (default: preview/)",
    )

    # upload-wiki command
    p_upload = subparsers.add_parser(
        "upload-wiki", help="Upload pages to wiki via MediaWiki API"
    )
    p_upload.add_argument(
        "--pages",
        default="wiki_pages",
        help="Pages directory to upload (default: wiki_pages/)",
    )
    p_upload.add_argument(
        "--url",
        default="https://wiki.foundry-game.com",
        help="Wiki base URL",
    )
    p_upload.add_argument("--username", required=True, help="Bot username")
    p_upload.add_argument("--password", required=True, help="Bot password")
    p_upload.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't actually upload (default: true)",
    )
    p_upload.add_argument(
        "--commit",
        action="store_true",
        help="Actually upload (disables dry-run)",
    )

    # batch-upload command
    p_batch = subparsers.add_parser(
        "batch-upload",
        help="Full pipeline: generate all content then upload to wiki",
    )
    p_batch.add_argument(
        "game_dir",
        help="Path to Foundry game directory",
    )
    p_batch.add_argument(
        "--url",
        default="http://localhost:4000",
        help="Wiki base URL (default: http://localhost:4000)",
    )
    p_batch.add_argument("--username", default="Admin", help="Bot username (default: Admin)")
    p_batch.add_argument("--password", default="", help="Bot password")
    p_batch.add_argument(
        "--pages",
        default="wiki_pages",
        help="Pages directory (default: wiki_pages/)",
    )
    p_batch.add_argument(
        "--lua",
        default="lua_modules",
        help="Lua data modules directory (default: lua_modules/)",
    )
    p_batch.add_argument(
        "--wiki-modules",
        default="wiki_modules",
        help="Wiki rendering modules directory (default: wiki_modules/)",
    )
    p_batch.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't actually upload (default: true)",
    )
    p_batch.add_argument(
        "--commit",
        action="store_true",
        help="Actually upload (disables dry-run)",
    )
    p_batch.add_argument(
        "--generate",
        action="store_true",
        help="Re-generate all content before uploading",
    )
    p_batch.add_argument(
        "--rate-limit",
        type=float,
        default=0.2,
        help="Seconds between API edits (default: 0.2 for localhost)",
    )
    p_batch.add_argument(
        "--skip-unchanged",
        action="store_true",
        default=True,
        help="Skip pages whose content matches the wiki (default: true)",
    )
    p_batch.add_argument(
        "--images",
        default=None,
        help="Directory of renamed wiki images to upload (e.g. wiki_images/). "
             "Omit to skip image upload.",
    )
    p_batch.add_argument(
        "--no-overwrite-images",
        action="store_true",
        default=False,
        help="Skip images that already exist on the wiki (default: overwrite)",
    )

    # backup-wiki command
    p_backup = subparsers.add_parser(
        "backup-wiki", help="Download all wiki pages for offline reference"
    )
    p_backup.add_argument(
        "--url",
        default="https://wiki.foundry-game.com",
        help="Wiki base URL (default: https://wiki.foundry-game.com)",
    )
    p_backup.add_argument(
        "--output",
        "-o",
        default="wiki_backup",
        help="Output directory (default: wiki_backup/)",
    )
    p_backup.add_argument(
        "--rate-limit",
        type=float,
        default=0.5,
        help="Seconds between API requests (default: 0.5)",
    )

    args = parser.parse_args()

    if args.command == "parse":
        cmd_parse(args)
    elif args.command == "summary":
        cmd_summary(args)
    elif args.command == "lookup":
        cmd_lookup(args)
    elif args.command == "generate-pages":
        cmd_generate_pages(args)
    elif args.command == "generate-navboxes":
        cmd_generate_navboxes(args)
    elif args.command == "generate-lua":
        cmd_generate_lua(args)
    elif args.command == "diff-wiki":
        cmd_diff_wiki(args)
    elif args.command == "preview":
        cmd_preview(args)
    elif args.command == "upload-wiki":
        cmd_upload_wiki(args)
    elif args.command == "batch-upload":
        cmd_batch_upload(args)
    elif args.command == "backup-wiki":
        cmd_backup_wiki(args)


def cmd_diff_wiki(args: argparse.Namespace) -> None:
    """Compare generated pages against wiki backup."""
    from .wiki_diff import diff_against_backup

    pages_dir = Path(args.pages)
    backup_dir = Path(args.backup)
    output_dir = Path(args.output)

    if not pages_dir.exists():
        print(f"Error: pages directory '{pages_dir}' not found.")
        print("Run 'generate-pages' first.")
        sys.exit(1)
    if not backup_dir.exists():
        print(f"Error: backup directory '{backup_dir}' not found.")
        print("Run 'backup-wiki' first.")
        sys.exit(1)

    print("Comparing generated pages against wiki backup...\n")
    diff_against_backup(pages_dir, backup_dir, output_dir)


def cmd_preview(args: argparse.Namespace) -> None:
    """Generate a local HTML preview site."""
    from .preview import generate_preview_site

    pages_dir = Path(args.pages)
    output_dir = Path(args.output)

    if not pages_dir.exists():
        print(f"Error: pages directory '{pages_dir}' not found.")
        print("Run 'generate-pages' first.")
        sys.exit(1)

    print("Generating HTML preview site...\n")
    count = generate_preview_site(pages_dir, output_dir)
    print(f"\nDone! {count} pages rendered.")
    print(f"Open {output_dir}/index.html in your browser to browse.")


def cmd_upload_wiki(args: argparse.Namespace) -> None:
    """Upload pages to wiki via MediaWiki API."""
    try:
        from .wiki_upload import WikiUploader
    except ImportError:
        print("Error: 'requests' package required. Install with: pip install requests")
        sys.exit(1)

    dry_run = not args.commit
    pages_dir = Path(args.pages)

    uploader = WikiUploader(
        site_url=args.url,
        username=args.username,
        password=args.password,
    )

    if not dry_run:
        print("Logging in...")
        uploader.login()

    print(f"Uploading from {pages_dir}...")
    results = uploader.upload_pages(pages_dir, dry_run=dry_run)

    if dry_run:
        print("\n(Dry run — no changes made. Use --commit to actually upload.)")


def cmd_generate_navboxes(args: argparse.Namespace) -> None:
    """Generate navbox templates and research tree page."""
    from .navbox_generator import generate_all_navboxes

    print("Loading game data...")
    gd = GameData.from_game_dir(Path(args.game_dir))
    summary = gd.summary()
    total = sum(summary.values())
    print(f"Parsed {total} entities.\n")

    print("Generating navboxes...")
    results = generate_all_navboxes(
        gd,
        wiki_modules_dir=Path(args.wiki_modules),
        pages_dir=Path(args.pages),
    )

    print(f"\nDone! {len(results)} navigation files generated.")


def cmd_generate_pages(args: argparse.Namespace) -> None:
    """Generate wiki page wikitext from game data."""
    from .page_generator import generate_all_pages

    print("Loading game data...")
    gd = GameData.from_game_dir(Path(args.game_dir))
    summary = gd.summary()
    total = sum(summary.values())
    print(f"Parsed {total} entities.\n")

    print("Generating wiki pages...")
    output_dir = Path(args.output)
    results = generate_all_pages(gd, output_dir)

    total_pages = sum(results.values())
    print(f"\nDone! {total_pages} pages generated.")


def cmd_generate_lua(args: argparse.Namespace) -> None:
    """Generate Lua data modules from game data."""
    from .lua_export import export_all_lua

    print("Loading game data...")
    gd = GameData.from_game_dir(Path(args.game_dir))
    summary = gd.summary()
    total = sum(summary.values())
    print(f"Parsed {total} entities.\n")

    print("Generating Lua modules...")
    output_dir = Path(args.output)
    results = export_all_lua(gd, output_dir)

    print(f"\nGenerated {len(results)} modules in {output_dir}/")
    total_entries = sum(results.values())
    print(f"Total entries: {total_entries}")


def cmd_batch_upload(args: argparse.Namespace) -> None:
    """Full batch upload: Lua modules → wiki modules → templates → navboxes → pages."""
    try:
        from .wiki_upload import WikiUploader
    except ImportError:
        print("Error: 'requests' package required. Install with: pip install requests")
        sys.exit(1)

    dry_run = not args.commit
    pages_dir = Path(args.pages)
    lua_dir = Path(args.lua)
    wiki_modules_dir = Path(args.wiki_modules)

    # --- Optionally regenerate everything first ---
    if args.generate:
        print("=" * 60)
        print("Step 0: Regenerating all content from game data")
        print("=" * 60)
        gd = GameData.from_game_dir(Path(args.game_dir))
        summary = gd.summary()
        total = sum(summary.values())
        print(f"Parsed {total} entities.\n")

        # Generate Lua data modules
        from .lua_export import export_all_lua
        print("Generating Lua data modules...")
        lua_dir.mkdir(parents=True, exist_ok=True)
        export_all_lua(gd, lua_dir)

        # Generate pages
        from .page_generator import generate_all_pages
        print("\nGenerating wiki pages...")
        generate_all_pages(gd, pages_dir)

        # Generate navboxes — templates go to wiki_modules/, Research Tree to pages_dir
        from .navbox_generator import generate_all_navboxes
        print("\nGenerating navboxes...")
        generate_all_navboxes(gd, wiki_modules_dir=wiki_modules_dir, pages_dir=pages_dir)

        print()

    # --- Set up uploader ---
    uploader = WikiUploader(
        site_url=args.url,
        username=args.username,
        password=args.password,
        rate_limit=args.rate_limit,
    )

    if dry_run:
        print("=" * 60)
        print("DRY RUN — no changes will be made")
        print(f"Target wiki: {args.url}")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"UPLOADING to {args.url}")
        print("=" * 60)
        print("Logging in...")
        uploader.login()
        print("Login successful.\n")

    all_results: list[str] = []

    def _upload_one(title: str, content: str, summary: str = "", idx: str = "",
                    content_model: str = "") -> str:
        """Upload a single page with skip-unchanged logic. Returns status string."""
        if args.skip_unchanged:
            current = uploader.get_page_content(title)
            if current is not None and current.rstrip() == content.rstrip():
                all_results.append("unchanged")
                print(f"  {idx}unchanged: {title}")
                return "unchanged"
        resp = uploader.edit_page(title, content, summary=summary,
                                  content_model=content_model)
        edit_data = resp.get("edit", {})
        if edit_data.get("result") == "Success":
            status = "created" if edit_data.get("new") else "updated"
            all_results.append(status)
            print(f"  {idx}{status}: {title}")
            return status
        else:
            all_results.append("error")
            print(f"  {idx}ERROR: {title} — {resp.get('error', edit_data)}")
            return "error"

    # If --images is supplied, skip all content phases and only upload images.
    if args.images:
        _run_phases = False
    else:
        _run_phases = True

    # --- Phases 1–5: Content upload (skipped when --images is supplied) ---
    if not _run_phases:
        print("\n  Skipping content phases — running in images-only mode (--images supplied).")

    # --- Phase 1: Lua data modules (Module:Data/*) ---
    print("\n" + "-" * 40)
    print("Phase 1: Lua Data Modules")
    print("-" * 40)
    if not _run_phases:
        print("  Skipped — images-only mode")
    elif lua_dir.exists():
        lua_files = sorted(lua_dir.glob("*.lua"))
        print(f"  Found {len(lua_files)} Lua data modules")
        for i, f in enumerate(lua_files, 1):
            title = f"Module:Data/{f.stem}"
            content = f.read_text(encoding="utf-8")
            if dry_run:
                print(f"  [{i}/{len(lua_files)}] would_upload: {title} ({len(content)} bytes)")
            else:
                _upload_one(title, content, summary="Update data module", idx=f"[{i}/{len(lua_files)}] ")
    else:
        print(f"  Skipped — {lua_dir}/ not found")

    # --- Phase 2: Wiki rendering modules (Module:Infobox, etc.) ---
    print("\n" + "-" * 40)
    print("Phase 2: Wiki Rendering Modules")
    print("-" * 40)
    if not _run_phases:
        print("  Skipped — images-only mode")
    elif wiki_modules_dir.exists():
        lua_modules = sorted(wiki_modules_dir.glob("Module_*.lua"))
        # Template_Infobox_styles.css  -> Template:Infobox/styles.css
        # Template_Navbox2_style.css   -> Template:Navbox2/style.css
        css_files = sorted(wiki_modules_dir.glob("Template_*_style*.css"))
        # Also collect module /doc pages (Module_Infobox_doc.wikitext → Module:Infobox/doc)
        module_doc_files = sorted(wiki_modules_dir.glob("Module_*_doc.wikitext"))
        print(f"  Found {len(lua_modules)} Lua modules, {len(css_files)} CSS files, {len(module_doc_files)} module doc pages")

        for i, f in enumerate(lua_modules, 1):
            # Module_Infobox.lua -> Module:Infobox
            title = "Module:" + f.stem.replace("Module_", "")
            content = f.read_text(encoding="utf-8")
            if dry_run:
                print(f"  [{i}] would_upload: {title} ({len(content)} bytes)")
            else:
                _upload_one(title, content, summary="Update rendering module", idx=f"[{i}] ")

        for i, f in enumerate(module_doc_files, 1):
            # Module_Infobox_doc.wikitext      -> Module:Infobox/doc
            # Module_Data_Buildings_doc.wikitext -> Module:Data/Buildings/doc
            stem = f.stem.replace("Module_", "")          # e.g. "Infobox_doc" or "Data_Buildings_doc"
            stem = stem[:-4]                               # strip "_doc" -> "Infobox" or "Data_Buildings"
            # "Data_Buildings" must become "Data/Buildings", not "Data Buildings"
            if stem.startswith("Data_"):
                stem = "Data/" + stem[5:]
            title = "Module:" + stem + "/doc"
            content = f.read_text(encoding="utf-8")
            if dry_run:
                print(f"  [{i}] would_upload: {title} ({len(content)} bytes)")
            else:
                _upload_one(title, content, summary="Update module documentation", idx=f"[{i}] ")

        for i, f in enumerate(css_files, 1):
            # Template_Infobox_styles.css        -> Template:Infobox/styles.css
            # Template_Navbox2_style.css         -> Template:Navbox2/style.css
            # Template_Navbox_Patches_styles.css -> Template:Navbox Patches/styles.css
            stem = f.stem.replace("Template_", "", 1)      # e.g. "Navbox_Patches_styles"
            name, suffix = stem.rsplit("_", 1)              # ("Navbox_Patches", "styles")
            name = name.replace("_", " ")                   # "Navbox Patches"
            title = f"Template:{name}/{suffix}.css"
            content = f.read_text(encoding="utf-8")
            if dry_run:
                print(f"  [{i}] would_upload: {title} ({len(content)} bytes, sanitized-css)")
            else:
                _upload_one(title, content, summary="Update template styles",
                            idx=f"[{i}] ", content_model="sanitized-css")
    else:
        print(f"  Skipped — {wiki_modules_dir}/ not found")

    # --- Phase 3: Template wrappers ---
    print("\n" + "-" * 40)
    print("Phase 3: Template Wrappers")
    print("-" * 40)
    if not _run_phases:
        print("  Skipped — images-only mode")
    elif wiki_modules_dir.exists():
        template_files = sorted(wiki_modules_dir.glob("Template_*.wikitext"))
        doc_count = sum(1 for f in template_files if f.stem.endswith("_doc"))
        print(f"  Found {len(template_files) - doc_count} templates, {doc_count} template doc pages")

        for i, f in enumerate(template_files, 1):
            stem = f.stem.replace("Template_", "")
            if stem.endswith("_doc"):
                # Template_Infobox_Item_doc.wikitext -> Template:Infobox Item/doc
                title = "Template:" + stem[:-4].replace("_", " ") + "/doc"
                summary = "Update template documentation"
            else:
                # Template_Infobox_Item.wikitext -> Template:Infobox Item
                title = "Template:" + stem.replace("_", " ")
                summary = "Update template wrapper"
            content = f.read_text(encoding="utf-8")
            if dry_run:
                print(f"  [{i}] would_upload: {title} ({len(content)} bytes)")
            else:
                _upload_one(title, content, summary=summary, idx=f"[{i}] ")
    else:
        print("  Skipped — no wiki_modules/ directory")

    # --- Phase 4: Research Tree (main-namespace navigation page) ---
    # Template_Navbox_*.wikitext files are now in wiki_modules/ and handled by Phase 3.
    print("\n" + "-" * 40)
    print("Phase 4: Research Tree")
    print("-" * 40)
    if not _run_phases:
        print("  Skipped — images-only mode")
    else:
        research_tree = pages_dir / "Research_Tree.wikitext"
        if research_tree.exists():
            content = research_tree.read_text(encoding="utf-8")
            if dry_run:
                print(f"  would_upload: Research Tree ({len(content)} bytes)")
            else:
                _upload_one("Research Tree", content, summary="Update research tree")
        else:
            print(f"  Skipped — Research_Tree.wikitext not found in {pages_dir}/")

    # --- Phase 5: Content pages (items, buildings, research, elements, etc.) ---
    print("\n" + "-" * 40)
    print("Phase 5: Content Pages")
    print("-" * 40)
    if not _run_phases:
        print("  Skipped — images-only mode")
    elif pages_dir.exists():
        import json as _json
        # Collect all page files from subdirectories (skip navboxes)
        page_files = []
        for subdir in sorted(pages_dir.iterdir()):
            if not subdir.is_dir():
                continue
            if subdir.name == "navboxes":
                continue  # handled in phase 4
            # Load the title manifest if present (maps stem -> actual page title,
            # needed for titles that contain characters sanitised in filenames,
            # e.g. colons replaced with underscores by _safe_filename).
            manifest_path = subdir / "_titles.json"
            title_map: dict[str, str] = {}
            if manifest_path.exists():
                try:
                    title_map = _json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            for f in sorted(subdir.glob("*.wikitext")):
                stem = f.stem
                if stem in title_map:
                    title = title_map[stem]
                else:
                    # Fallback: derive from filename (works for titles with no
                    # special characters beyond spaces stored as underscores)
                    title = stem.replace("_", " ")
                page_files.append((title, f))

        print(f"  Found {len(page_files)} content pages")

        for i, (title, filepath) in enumerate(page_files, 1):
            content = filepath.read_text(encoding="utf-8").rstrip()

            if dry_run:
                if i <= 5 or i == len(page_files):
                    print(f"  [{i}/{len(page_files)}] would_upload: {title} ({len(content)} bytes)")
                elif i == 6:
                    print(f"  ... ({len(page_files) - 10} more pages) ...")
            else:
                try:
                    _upload_one(title, content, idx=f"[{i}/{len(page_files)}] ")
                except Exception as e:
                    print(f"  [{i}/{len(page_files)}] ERROR: {title} — {e}")

    else:
        print(f"  Skipped — {pages_dir}/ not found")

    # --- Summary (content phases only) ---
    if _run_phases and not dry_run:
        from collections import Counter
        counts = Counter(all_results)
        total = sum(counts.values())
        parts = []
        for status in ("created", "updated", "unchanged", "error"):
            if counts[status]:
                parts.append(f"{counts[status]} {status}")
        print("\n" + "=" * 40)
        print("Upload complete: " + ", ".join(parts) if parts else "Upload complete: nothing to report")
        print("=" * 40)

    # --- Phase 6: Images ---
    print("\n" + "-" * 40)
    print("Phase 6: Images")
    print("-" * 40)
    if args.images:
        images_dir = Path(args.images)
        if images_dir.exists():
            image_files = sorted(
                f for f in images_dir.glob("*")
                if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
            )
            overwrite = not getattr(args, "no_overwrite_images", False)
            print(f"  Found {len(image_files)} image(s) in {images_dir}/")
            if not overwrite:
                print("  --no-overwrite-images set: existing files will be skipped")

            for i, f in enumerate(image_files, 1):
                dest = f.name  # already named Item_Foo.png etc.
                # Use a .wikitext sidecar if present (written by fetch_patch.py
                # for Steam images); otherwise generate game-asset description.
                sidecar = f.with_suffix(".wikitext")
                file_text = (
                    sidecar.read_text(encoding="utf-8")
                    if sidecar.exists()
                    else _game_asset_description(dest)
                )
                if dry_run:
                    sidecar_note = " (sidecar)" if sidecar.exists() else " (auto-desc)"
                    if i <= 5 or i == len(image_files):
                        print(f"  [{i}/{len(image_files)}] would_upload: File:{dest} ({f.stat().st_size} bytes){sidecar_note}")
                    elif i == 6:
                        print(f"  ... ({len(image_files) - 6} more) ...")
                else:
                    try:
                        result = uploader.upload_file(
                            file_path=f,
                            dest_filename=dest,
                            overwrite=overwrite,
                            text=file_text,
                        )
                        upload_info = result.get("upload", {})
                        if "error" in result:
                            code = result["error"].get("code", "?")
                            info = result["error"].get("info", "")
                            print(f"  [{i}/{len(image_files)}] ERROR: File:{dest} — {code}: {info}")
                        elif upload_info.get("result") == "Success":
                            print(f"  [{i}/{len(image_files)}] uploaded: File:{dest}")
                        else:
                            print(f"  [{i}/{len(image_files)}] ?: File:{dest} — {result}")
                    except Exception as e:
                        print(f"  [{i}/{len(image_files)}] ERROR: File:{dest} — {e}")
        else:
            print(f"  Images directory not found: {images_dir}")
    else:
        print("  Skipped — pass --images <dir> to upload images")
