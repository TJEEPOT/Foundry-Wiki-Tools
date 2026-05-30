# Foundry Wiki Tools

A Python toolkit for extracting game data from [Foundry](https://store.steampowered.com/app/983870/FOUNDRY/) (the factory-building game) and generating content for its [community wiki](https://wiki.foundry-game.com). The pipeline reads YAML template files shipped with the game, builds a cross-referenced data model, and produces Lua data modules, wikitext pages, navigation templates, and a local preview site - everything needed to keep a MediaWiki instance up to date as the game evolves.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Python Package - `foundry_parser`](#python-package--foundry_parser)
- [Wiki Modules - `wiki_modules/`](#wiki-modules--wiki_modules)
- [Generated Output Directories](#generated-output-directories)
- [Wiki Data Architecture](#wiki-data-architecture)
- [Workflow: Game Update to Wiki Update](#workflow-game-update-to-wiki-update)
- [Configuration and Conventions](#configuration-and-conventions)
- [Dependencies](#dependencies)
- [License](#license)

---

## Overview

Foundry stores its game data as ~2,750 YAML files across 68+ categories in `foundry_Data/StreamingAssets/Templates/`. This toolkit:

1. **Parses** all YAML templates into typed Python dataclasses
2. **Cross-references** entities (which recipes produce an item, which buildings craft a recipe, which research unlocks what)
3. **Exports Lua data modules** for the wiki's Scribunto engine (`mw.loadData()`)
4. **Generates wikitext pages** with contextual lead paragraphs, infobox/recipe template calls, navbox includes, and categories
5. **Generates navigation templates** (navboxes grouped by function, research tree page)
6. **Produces a local HTML preview** so you can review pages without wiki access
7. **Diffs generated pages** against a wiki backup to see what's new or changed
8. **Uploads pages** to the wiki via the MediaWiki API (with dry-run safety)

---

## Installation

Requires Python 3.10+.

```bash
cd Foundry-Wiki-Tools
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -e .              # Core (YAML parsing, page generation, preview)
pip install -e ".[wiki]"     # Also installs `requests` for wiki upload/backup
```

The `foundry-parser` command becomes available after installation, or you can use `python -m foundry_parser`.

---

## Quick Start

```bash
# Point at your Foundry game directory
GAME_DIR="C:/Program Files/Steam/SteamApps/common/FOUNDRY"
F:\SteamLibrary\SteamApps\common\FOUNDRY
# 1. Generate Lua data modules for the wiki
foundry-parser generate-lua "$GAME_DIR" --output lua_modules

# 2. Generate all wiki pages
foundry-parser generate-pages "$GAME_DIR" --output wiki_pages

# 3. Generate navbox templates and research tree
foundry-parser generate-navboxes "$GAME_DIR" --output wiki_pages/navboxes

# 4. Preview locally in your browser
foundry-parser preview --pages wiki_pages --output preview
# Open preview/index.html

# 5. Back up the live wiki for comparison
foundry-parser backup-wiki --output wiki_backup

# 6. See what changed
foundry-parser diff-wiki --pages wiki_pages --backup wiki_backup --output diff_report
```

---

## CLI Commands

All commands are accessed via `foundry-parser <command>` or `python -m foundry_parser <command>`.

### `parse`

Parse all game data and print a summary. Optionally export the full data model as JSON.

```bash
foundry-parser parse <game_dir> [--output data.json]
```

### `summary`

Print a quick count of entities by category.

```bash
foundry-parser summary <game_dir>
```

### `lookup`

Look up a single entity by type and identifier. Shows full details with cross-references (recipes that produce/consume it, research that unlocks it, building it places, etc.).

```bash
foundry-parser lookup <game_dir> item _base_xf_steel_beams
foundry-parser lookup <game_dir> building _base_advanced_smelter
foundry-parser lookup <game_dir> recipe _base_recipe_steel_beams
foundry-parser lookup <game_dir> research _base_research_basic_steelmaking
```

### `generate-lua`

Export game data as Lua modules compatible with MediaWiki's Scribunto (`mw.loadData()`). Produces one `.lua` file per data category plus a NameIndex for display-name lookups.

```bash
foundry-parser generate-lua <game_dir> [--output lua_modules]
```

### `generate-pages`

Generate complete wikitext pages for items, buildings, research, and elements. Each page includes an infobox template call, a contextual lead paragraph (not generic filler), recipe sections, tech tree context, navbox, and categories.

```bash
foundry-parser generate-pages <game_dir> [--output wiki_pages]
```

### `generate-navboxes`

Generate navbox templates (Items, Buildings, Research, Elements) and a dedicated Research Tree page with sortable tier tables.

```bash
foundry-parser generate-navboxes <game_dir> [--output wiki_pages/navboxes]
```

### `preview`

Generate a static HTML site from the wikitext pages for local browsing. Dark-themed, with working cross-page links, template placeholders, and per-type index pages.

```bash
foundry-parser preview [--pages wiki_pages] [--output preview]
```

### `backup-wiki`

Download all pages from the live wiki via the MediaWiki API. Organises them by namespace. Used as the baseline for diff comparisons.

```bash
foundry-parser backup-wiki [--url https://wiki.foundry-game.com] [--output wiki_backup] [--rate-limit 0.5]
```

### `diff-wiki`

Compare your generated pages against the wiki backup. Produces a report of new, changed, unchanged, and removed pages, plus unified diffs for changed pages.

```bash
foundry-parser diff-wiki [--pages wiki_pages] [--backup wiki_backup] [--output diff_report]
```

### `upload-wiki`

Upload generated pages to the wiki via the MediaWiki API. Defaults to dry-run mode (no changes made). Pass `--commit` to actually upload.

```bash
# Dry run (safe - just reports what would happen)
foundry-parser upload-wiki --pages wiki_pages --username BotUser --password BotPass

# Actually upload
foundry-parser upload-wiki --pages wiki_pages --username BotUser --password BotPass --commit
```

---

## Architecture

The system uses a three-layer architecture on the wiki side:

```
┌─────────────────────────────────────────────────┐
│  Layer 3: MediaWiki Templates                   │
│  Thin wrappers - just {{#invoke:Module|func}}   │
├─────────────────────────────────────────────────┤
│  Layer 2: Lua Rendering Modules (hand-written)  │
│  Infobox, RecipeTable, ItemLink                 │
├─────────────────────────────────────────────────┤
│  Layer 1: Lua Data Modules (auto-generated)     │
│  Module:Data/Items, Module:Data/Buildings, etc. │
└─────────────────────────────────────────────────┘
```

When the game updates, only Layer 1 needs regenerating. The rendering modules and templates remain stable.

The Python side handles:

```
YAML game files -> Parser -> GameData (cross-referenced) -> Generators
                                    │                             │
                                    ├-> Lua exporter              ├-> .lua files
                                    ├-> Page generator            ├-> .wikitext files
                                    ├-> Navbox generator          ├-> navbox .wikitext
                                    └-> Preview generator         └-> .html site
```

---

## Project Structure

```
Foundry-Wiki-Tools/
├── foundry_parser/          # Python package (core toolkit)
│   ├── __init__.py
│   ├── __main__.py          # Enables `python -m foundry_parser`
│   ├── cli.py               # CLI entry point (argparse, all commands)
│   ├── models.py            # Dataclass definitions for all entity types
│   ├── loader.py            # YAML loading and batch parsing
│   ├── game_data.py         # GameData class with cross-reference indices
│   ├── lua_export.py        # Lua data module generator
│   ├── page_generator.py    # Wiki page wikitext generator
│   ├── navbox_generator.py  # Navigation template generator
│   ├── preview.py           # Static HTML preview site generator
│   ├── wiki_backup.py       # MediaWiki API backup tool
│   ├── wiki_diff.py         # Diff tool (generated vs. backup)
│   └── wiki_upload.py       # MediaWiki API upload tool
│
├── wiki_modules/            # Lua modules and templates for the wiki
│   ├── Module_Infobox.lua           # Renders infoboxes for all entity types
│   ├── Module_ItemLink.lua          # Inline icon+name links
│   ├── Module_RecipeTable.lua       # Recipe tables with rates and crafters
│   ├── TemplateStyles_Infobox.css   # Dark-theme CSS for infoboxes
│   ├── Template_Infobox.wikitext            # Auto-detecting infobox wrapper
│   ├── Template_Infobox_Item.wikitext       # Item-specific infobox
│   ├── Template_Infobox_Building.wikitext   # Building-specific infobox
│   ├── Template_Infobox_Research.wikitext   # Research-specific infobox
│   ├── Template_Infobox_Element.wikitext    # Element-specific infobox
│   ├── Template_ItemLink.wikitext           # Inline link wrapper
│   ├── Template_RecipeTable.wikitext        # Recipe table (by item)
│   └── Template_RecipeTable_Building.wikitext  # Recipe table (by building)
│
├── pyproject.toml           # Project metadata and dependencies
├── test_lua_modules.lua     # Lua test script for verifying modules locally
│
├── lua_modules/             # (generated) Lua data files for wiki upload
├── wiki_pages/              # (generated) Wikitext page files
│   └── navboxes/            # (generated) Navbox templates
├── wiki_backup/             # (generated) Downloaded wiki pages
├── diff_report/             # (generated) Diff analysis output
└── preview/                 # (generated) HTML preview site
```

---

## Python Package - `foundry_parser`

### `models.py`

Defines typed dataclasses for every entity the parser handles:

- **`Item`** - name, identifier, stack size, weight, icon, category, trade prices, flags
- **`Building`** - type, size (x/y/z), power consumption, power type/subtype, recipe tags, modules, name override
- **`CraftingRecipe`** - inputs, outputs (both items and elements/fluids), time, tags, category
- **`Research`** - name, description, costs, dependencies, crafting unlocks, seconds per science item
- **`Element`** - name, pipe content type (gas/liquid), properties
- **`ItemCategory`**, **`RecipeCategory`**, **`CraftingTag`** - supporting lookup tables
- **`TerrainBlock`**, **`OreVein`**, **`Quest`**, **`SkyPlatformUpgrade`**, etc. - additional categories

Helper types: `CraftingIO` (amount + identifier for recipe inputs/outputs).

### `loader.py`

Low-level YAML loading. Reads the `StreamingAssets/Templates/` directory structure, identifies category directories, and parses YAML files into raw dictionaries. Handles Unity-specific quirks (embedded references, `_str` suffix fields).

### `game_data.py`

The central `GameData` class. Constructed via `GameData.from_game_dir(path)`, it:

- Loads all template categories via `loader.py`
- Instantiates model objects from raw YAML
- Builds cross-reference indices:
  - `_recipe_output_index` - item identifier -> recipes that produce it
  - `_recipe_input_index` - item identifier -> recipes that consume it
  - `_building_to_item_index` - building identifier -> item that places it
  - `_building_recipe_index` - building identifier -> recipes it can craft (via tag matching)
  - `_research_unlock_index` - recipe/item identifier -> research that unlocks it

Key lookup methods:

- `recipes_producing(item_id)` -> list of recipes
- `recipes_consuming(item_id)` -> list of recipes
- `building_for_item(item_id)` -> Building or None
- `recipes_for_building(building_id)` -> list of recipes
- `research_unlocking(item_id)` -> list of Research
- `item_name(item_id)` / `building_name(building_id)` / `element_name(elem_id)` -> display name
- `summary()` -> dict of category counts
- `export_json(path)` -> full JSON export

### `lua_export.py`

Converts GameData into Lua source files compatible with `mw.loadData()`. Each module is a Lua table keyed by entity identifier. Produces ~24 modules including:

- `Items.lua`, `Buildings.lua`, `Recipes.lua`, `Research.lua`, `Elements.lua`
- `ItemCategories.lua`, `RecipeCategories.lua`, `CraftingTags.lua`
- `TerrainBlocks.lua`, `OreVeins.lua`, `Quests.lua`, `SkyPlatformUpgrades.lua`
- `BuildingRecipeIndex.lua` - maps building ID -> list of recipe IDs it can craft
- `ItemBuildingIndex.lua` - maps building ID -> item ID that places it
- `NameIndex.lua` - maps display names -> `{type, id}` for resolving page names to data keys

### `page_generator.py`

Generates complete wikitext for every entity that merits a wiki page (~962 pages total):

- ~512 item pages
- ~249 building pages (deduplicated by display name)
- ~173 research pages
- ~28 element pages

Each page includes:
- Infobox template call with the entity's identifier
- **Contextual lead paragraph** - not generic filler but sentences like "Steel Beams can be produced by 2 recipes, crafted in buildings such as Advanced Smelter. It is a component in 75 recipes. Unlocked by the Basic Steelmaking research."
- Recipe/crafting sections
- Tech tree context (what research unlocks it, what it enables)
- Navbox template
- Wiki categories

Filtering logic skips entities that don't warrant pages (internal items without recipes, unnamed entities, terrain blocks, etc.).

### `navbox_generator.py`

Generates five navigation files:

- **Template:Navbox Items** - items grouped by category (Resources, Components, Products, etc.)
- **Template:Navbox Buildings** - buildings grouped by function (Production, Power Generation, Logistics, Storage, etc.) using a 16-group mapping from building types
- **Template:Navbox Research** - research grouped by dependency tier (computed via recursive BFS)
- **Template:Navbox Elements** - elements grouped by state (Gases, Liquids)
- **Research Tree** - a dedicated page with sortable wikitables per tier showing unlocks, prerequisites, and costs

Uses the `{{Navbox2}}` format compatible with the existing wiki.

### `preview.py`

Generates a static HTML site from wikitext pages for local browsing without wiki access:

- Dark theme matching the wiki's aesthetic
- Cross-page links (blue for existing pages, red for missing)
- Template placeholders rendered as styled blocks (infobox sidebar, recipe card, navbox bar)
- Handles wikitext syntax: headings, bold/italic, internal links, bullet lists, wiki tables, categories
- Index pages: main index + per-type indexes (items, buildings, research, elements, navboxes)
- Open `preview/index.html` in any browser to browse

### `wiki_backup.py`

Downloads all pages from a MediaWiki site via the API for local reference:

- Uses `action=query&list=allpages` to enumerate all pages across namespaces
- Downloads page content via the revisions API
- Organises output by namespace (main/, Template/, Module/, etc.)
- Configurable rate limiting (default 0.5s between requests)

### `wiki_diff.py`

Compares generated pages against a wiki backup:

- Categorises pages as new, changed, unchanged, or removed
- Produces unified diffs for changed pages
- Outputs: `summary.txt`, `report.json`, `new_pages.txt`, `changed_pages.txt`, `removed_pages.txt`, and individual `.diff` files
- Normalises whitespace for fair comparison
- "Removed" pages are those in the backup but not generated (hand-written content, redirects, etc.)

### `wiki_upload.py`

Handles authenticated page uploads to a MediaWiki site:

- **Login flow**: login token -> authenticate -> CSRF token for editing
- **Dry-run mode** (default): reports what would change without touching the wiki
- **Incremental mode**: fetches current page content and skips unchanged pages
- **Bot flag**: marks edits as bot edits (hidden from recent changes by default)
- **Rate limiting**: configurable delay between edits (default 1s)
- **Lua module upload**: dedicated method for `Module:Data/*` namespace
- Edit summary: "Auto-generated by Foundry Wiki Tools"

---

## Wiki Modules - `wiki_modules/`

These files are designed to be uploaded to the wiki and used by the generated pages. They form the rendering layer that transforms raw data into formatted HTML.

### `Module_Infobox.lua`

The main infobox renderer. Entry points:

- `p.item(frame)` - item infobox (icon, stack size, weight, category, trade prices)
- `p.building(frame)` - building infobox (type, size, power, recipe tags)
- `p.research(frame)` - research infobox (costs, prerequisites, unlocks)
- `p.element(frame)` - element infobox (state, pipe type)
- `p.auto(frame)` - auto-detects entity type from NameIndex and dispatches

Resolves entity identifiers via NameIndex (so `{{Infobox}}` on a page named "Steel Beams" will find the correct data). Handles power grid display (Low Voltage/PCM vs High Voltage), auto-categorization, and image resolution via ItemBuildingIndex.

### `Module_ItemLink.lua`

Renders inline icon+name links like `[[File:steel_beams.png|16px|link=Steel Beams]] [[Steel Beams]]`. Supports:

- Lookup by identifier (`_base_xf_steel_beams`) or display name (`Steel Beams`)
- Options: `size` (icon px), `noicon`, `notext`, `nolink`, `amount` (prefix like "5x")
- Lazy-loads data modules to avoid circular dependencies
- Exposes `p._resolveEntity(input)` for other modules to reuse

### `Module_RecipeTable.lua`

Renders recipe information in two formats:

- **Recipe table**: wikitable showing inputs -> outputs with amounts, base crafting time, which buildings can craft it, and what research unlocks it
- **Rate table**: per-crafter comparison showing items/minute at different building speeds

Entry points:

- `p.forItem(frame)` - all recipes that produce or consume a given item
- `p.forBuilding(frame)` - all recipes a given building can craft
- `p.single(frame)` - a specific recipe by identifier

Handles both solid item I/O and fluid/elemental I/O (displayed in litres).

### `TemplateStyles_Infobox.css`

Dark-theme CSS loaded via `<templatestyles>`. Styles the infobox, item links, recipe tables, and rate tables. Uses the wiki's existing dark colour palette.

### Template Wrappers (`.wikitext` files)

Thin wrappers that page authors use. Each is just a `<includeonly>{{#invoke:...}}</includeonly>` call:

| Template | Invokes | Purpose |
|----------|---------|---------|
| `{{Infobox}}` | `Module:Infobox\|auto` | Auto-detecting infobox |
| `{{Infobox Item}}` | `Module:Infobox\|item` | Item-specific |
| `{{Infobox Building}}` | `Module:Infobox\|building` | Building-specific |
| `{{Infobox Research}}` | `Module:Infobox\|research` | Research-specific |
| `{{Infobox Element}}` | `Module:Infobox\|element` | Element-specific |
| `{{RecipeTable}}` | `Module:RecipeTable\|forItem` | Recipes for an item |
| `{{RecipeTable Building}}` | `Module:RecipeTable\|forBuilding` | Recipes for a building |
| `{{ItemLink}}` | `Module:ItemLink\|main` | Inline icon+name link |

---

## Generated Output Directories

These directories are created by running the CLI commands and are not checked into version control:

| Directory | Created by | Contents |
|-----------|-----------|----------|
| `lua_modules/` | `generate-lua` | ~24 `.lua` files for wiki upload to `Module:Data/*` |
| `wiki_pages/` | `generate-pages` | ~962 `.wikitext` files (one per entity page) |
| `wiki_pages/navboxes/` | `generate-navboxes` | 4 navbox templates + Research Tree page |
| `wiki_backup/` | `backup-wiki` | Downloaded wiki pages organised by namespace |
| `diff_report/` | `diff-wiki` | Diff analysis (summary, JSON report, individual diffs) |
| `preview/` | `preview` | Static HTML site (open `index.html` in browser) |

---

## Wiki Data Architecture

The wiki uses MediaWiki v1.43.1 with Scribunto (Lua) and ParserFunctions. It does **not** have Cargo or Semantic MediaWiki.

### Data flow on the wiki

```
Module:Data/Items (mw.loadData)  ->  Module:Infobox  ->  {{Infobox Item}}
Module:Data/Buildings             ->  Module:RecipeTable  ->  {{RecipeTable}}
Module:Data/Recipes               ->  Module:ItemLink  ->  {{ItemLink}}
Module:Data/NameIndex             ->  (name resolution)
Module:Data/BuildingRecipeIndex   ->  (crafter lookup)
Module:Data/ItemBuildingIndex     ->  (building-item mapping)
```

### Key design decisions

- **`mw.loadData()`** is used for all data modules - it returns read-only tables that are shared across all `#invoke` calls on a page, saving memory.
- **NameIndex** maps display names to `{type, id}` pairs so that templates on a page named "Steel Beams" can find the data keyed by `_base_xf_steel_beams`.
- **No recipe pages** - recipes are embedded in item and building pages rather than having their own pages.
- **Building names** are resolved from `name_override` (if set) or by looking up the item that places the building via ItemBuildingIndex.
- **Power system** has two voltage levels: Low Voltage (power_type = "PCM", uses building blocks for distribution) and High Voltage (power_type = "NONE", uses power lines).

---

## Workflow: Game Update to Wiki Update

When Foundry releases a patch:

```bash
# 1. Regenerate data modules (picks up new/changed YAML)
foundry-parser generate-lua "$GAME_DIR" -o lua_modules

# 2. Regenerate pages
foundry-parser generate-pages "$GAME_DIR" -o wiki_pages

# 3. Regenerate navboxes
foundry-parser generate-navboxes "$GAME_DIR" -o wiki_pages/navboxes

# 4. Preview locally to spot-check
foundry-parser preview --pages wiki_pages -o preview

# 5. Diff against the live wiki
foundry-parser backup-wiki -o wiki_backup
foundry-parser diff-wiki --pages wiki_pages --backup wiki_backup -o diff_report

# 6. Review the diff report
cat diff_report/summary.txt

# 7. Upload when satisfied (requires wiki bot credentials)
foundry-parser upload-wiki --pages wiki_pages --username Bot --password Pass --commit
```

---

## Configuration and Conventions

### Game directory

The toolkit expects the standard Steam installation layout:

```
FOUNDRY/
└── foundry_Data/
    └── StreamingAssets/
        └── Templates/
            ├── Items/
            ├── Buildings/
            ├── CraftingRecipes/
            ├── Research/
            ├── Elements/
            └── ... (68+ category directories)
```

### Entity identifiers

All entities have a unique string identifier (e.g., `_base_xf_steel_beams`, `_base_advanced_smelter`). These are used as keys in Lua data modules and as lookup parameters in templates.

### Page naming

Wiki pages use the entity's display name (e.g., "Steel Beams", "Advanced Smelter"). The NameIndex module bridges display names back to identifiers for data lookup.

### Icon convention

Item icons on the wiki follow the pattern `{icon_field_value}.png` (e.g., `steel_beams.png`). The `icon` field from the Items data provides this filename.

### Building type classification

Buildings are classified by their `type` field into functional groups for navbox organisation. The mapping is defined in `navbox_generator.py`'s `_BUILDING_GROUPS` dictionary and covers 16 groups: Production, Modular Buildings, Assembly Lines, Power Generation, Power Distribution, Solid Item Logistics, Liquid Handling, Storage, Resource Gathering, Rail Transport, Construction, Data System, Infrastructure, Science, Recycling, and Miscellaneous.

---

## Dependencies

**Core** (always required):
- Python 3.10+
- `pyyaml` - YAML parsing

**Wiki features** (optional, install with `pip install -e ".[wiki]"`):
- `requests` - wiki backup and upload via MediaWiki API

**Development** (optional, install with `pip install -e ".[dev]"`):
- `pytest` - testing
- `requests`

---

## License

GNU GPL v3
