# Foundry Wiki Tools

A Python toolkit for extracting game data from [Foundry](https://store.steampowered.com/app/983870/FOUNDRY/) (the factory-building game) and generating content for its [community wiki](https://wiki.foundry-game.com). The pipeline reads YAML template files shipped with the game, builds a cross-referenced data model, and produces Lua data modules, wikitext pages, navigation templates, and a local preview site — everything needed to keep a MediaWiki instance up to date as the game evolves.

A separate standalone script, `fetch_patch.py`, fetches patch notes and DevBlogs from the Steam API and converts them to wiki-ready wikitext.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [fetch\_patch.py](#fetch_patchpy)
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

Foundry stores its game data as YAML files in `StreamingAssets/Entities/`. This toolkit:

1. **Parses** all YAML templates into typed Python dataclasses
2. **Cross-references** entities (which recipes produce an item, which buildings craft a recipe, which research unlocks what)
3. **Exports Lua data modules** for the wiki's Scribunto engine (`mw.loadData()`)
4. **Generates wikitext pages** with contextual lead paragraphs, infobox/recipe template calls, navbox includes, and categories
5. **Generates navigation templates** (navboxes grouped by function, research tree page)
6. **Produces a local HTML preview** so you can review pages without wiki access
7. **Diffs generated pages** against a wiki backup to see what's new or changed
8. **Uploads pages** to the wiki via the MediaWiki API (with dry-run safety)
9. **Fetches patch notes and DevBlogs** from the Steam API and converts them to wikitext (`fetch_patch.py`)

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

`fetch_patch.py` is a standalone script with no extra dependencies beyond the Python standard library.

---

## Quick Start

```bash
# Point at your Foundry game directory
GAME_DIR="C:/Program Files/Steam/SteamApps/common/FOUNDRY"

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

Export game data as Lua modules compatible with MediaWiki's Scribunto (`mw.loadData()`). Produces ~27 modules including one per data category plus cross-reference index tables.

```bash
foundry-parser generate-lua <game_dir> [--output lua_modules]
```

### `generate-pages`

Generate complete wikitext pages for items, buildings, research, elements, exploration unlocks, and sky platform upgrades. Each page includes an infobox template call, a contextual lead paragraph, recipe sections, tech tree context, navbox, and categories. Produces ~1,437 pages total.

```bash
foundry-parser generate-pages <game_dir> [--output wiki_pages]
```

### `generate-navboxes`

Generate navbox templates (Items, Buildings, Research, Elements, Exploration Unlocks, Space Station Upgrades) and a dedicated Research Tree page.

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
# Dry run (safe — just reports what would happen)
foundry-parser upload-wiki --pages wiki_pages --username BotUser --password BotPass

# Actually upload
foundry-parser upload-wiki --pages wiki_pages --username BotUser --password BotPass --commit
```

### `batch-upload`

Full pipeline in one command: generate Lua modules, generate pages, generate navboxes, then upload everything to the wiki.

```bash
foundry-parser batch-upload <game_dir> --username BotUser --password BotPass [--commit]
```

---

## fetch_patch.py

A standalone script (no extra dependencies) that fetches patch notes and Foundry Fridays DevBlogs from the Steam API and converts them to wiki-ready wikitext.

> **Note:** The GID in a Steam web URL (e.g. `/view/670589610075619682`) is *different* from the API GID. Use `--list` to find the correct API GID for the post you want.

### Usage

```bash
# List the 5 most recent posts with their API GIDs (default)
python fetch_patch.py --list

# List more posts
python fetch_patch.py --list --count 20

# Fetch a specific post by API GID
python fetch_patch.py 1805065414331275

# Override the inferred wiki page name
python fetch_patch.py 1805065414331275 --page-name "Update 2.1 (Early Access)"
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--list` | — | Show recent posts with their API GIDs, then exit |
| `--count N` | `5` | Number of posts to show with `--list` |
| `--page-name NAME` | inferred | Wiki page name (inferred from post title if omitted) |
| `--stage STAGE` | `e` | Release stage: `e` Early Access, `a` Alpha, `b` Beta, `r` Release |
| `--channel CHANNEL` | `st` | Channel: `st` Stable, `ex` Experimental, `m` Major |
| `--out-dir DIR` | `wiki_pages/patches/` | Output directory for wikitext and images |
| `--dry-run` | — | Print wikitext to stdout instead of writing a file |
| `--no-images` | — | Skip downloading images (placeholders remain in the wikitext) |

### What it does

- Fetches the post's BBcode content from the Steam API and converts it to MediaWiki wikitext (headings, lists, bold/italic, links, image embeds, YouTube links)
- Infers the wiki page name from the post title (e.g. "Update 2.1 is Live Now!" → "Update 2.1 (Early Access)")
- Detects Foundry Fridays DevBlogs automatically and uses the appropriate template (`{{Devblog}}` vs `{{Patch}}`)
- Downloads images and saves them with wiki-ready filenames (e.g. `Update 2.1 (Early Access) 01.jpg`)
- Leaves Discord and Reddit links as `<!-- TODO -->` comments for manual entry

---

## Architecture

The system uses a three-layer architecture on the wiki side:

```
┌─────────────────────────────────────────────────┐
│  Layer 3: MediaWiki Templates                   │
│  Thin wrappers - just {{#invoke:Module|func}}   │
├─────────────────────────────────────────────────┤
│  Layer 2: Lua Rendering Modules (hand-written)  │
│  Infobox, RecipeCard, RecipeTable, ItemLink     │
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
├── foundry_parser/              # Python package (core toolkit)
│   ├── __init__.py
│   ├── __main__.py              # Enables `python -m foundry_parser`
│   ├── cli.py                   # CLI entry point (argparse, all commands)
│   ├── models.py                # Dataclass definitions for all entity types
│   ├── loader.py                # YAML loading and batch parsing
│   ├── game_data.py             # GameData class with cross-reference indices
│   ├── lua_export.py            # Lua data module generator
│   ├── page_generator.py        # Wiki page wikitext generator
│   ├── page_generator_standalone.py  # Standalone page generator variant
│   ├── navbox_generator.py      # Navigation template generator
│   ├── preview.py               # Static HTML preview site generator
│   ├── wiki_backup.py           # MediaWiki API backup tool
│   ├── wiki_diff.py             # Diff tool (generated vs. backup)
│   └── wiki_upload.py           # MediaWiki API upload tool
│
├── wiki_modules/                # Lua modules, templates, and CSS for the wiki
│   │
│   ├── # --- Lua rendering modules ---
│   ├── Module_Infobox.lua           # Renders infoboxes for all entity types
│   ├── Module_RecipeCard.lua        # Recipe cards with per-building rate breakdowns
│   ├── Module_RecipeTable.lua       # Recipe tables with rates and crafters
│   ├── Module_ItemLink.lua          # Inline icon+name links
│   ├── Module_Achievements.lua      # Achievements page renderer
│   ├── Module_Data_Buildings.lua    # Static building data (crafting time modifiers, etc.)
│   │
│   ├── # --- /doc subpages (uploaded as Module:Name/doc) ---
│   ├── Module_Infobox_doc.wikitext
│   ├── Module_RecipeCard_doc.wikitext
│   ├── Module_RecipeTable_doc.wikitext
│   ├── Module_ItemLink_doc.wikitext
│   ├── Module_Achievements_doc.wikitext
│   ├── Module_Data_Buildings_doc.wikitext
│   │
│   ├── # --- CSS (uploaded as Template:Name/styles.css) ---
│   ├── Template_Infobox_styles.css      # Infobox, item links, research card styles
│   ├── Template_RecipeCard_styles.css   # Recipe card layout (Design B)
│   ├── Template_Navbox2_style.css       # Navbox and hlist styles
│   │
│   ├── # --- Template wrappers ---
│   ├── Template_Infobox.wikitext
│   ├── Template_Infobox_Building.wikitext
│   ├── Template_Infobox_Element.wikitext
│   ├── Template_Infobox_Exploration_Unlock.wikitext
│   ├── Template_Infobox_Item.wikitext
│   ├── Template_Infobox_Research.wikitext
│   ├── Template_Infobox_Sky_Platform_Upgrade.wikitext
│   ├── Template_ItemLink.wikitext
│   ├── Template_RecipeCard.wikitext
│   ├── Template_RecipeCard_Building.wikitext
│   ├── Template_RecipeCard_Recipe.wikitext
│   ├── Template_RecipeTable.wikitext
│   ├── Template_RecipeTable_Building.wikitext
│   ├── Template_RecipeTable_Recipe.wikitext
│   ├── Template_Research_Card.wikitext
│   ├── Template_Navbox2.wikitext
│   ├── Template_Navbox_Buildings.wikitext
│   ├── Template_Navbox_Research.wikitext
│   ├── Template_Devblog.wikitext
│   └── Template_DevblogsNav.wikitext
│   │
│   └── # (plus matching _doc.wikitext files for each template above)
│
├── fetch_patch.py           # Standalone: fetch Steam patch notes → wikitext
├── rename_icons.py          # Utility: batch-rename icon files to wiki conventions
├── pyproject.toml           # Project metadata and dependencies
│
├── patch_notes/             # Patch note data
│   └── patches.xlsx
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

- **`Item`** — name, identifier, stack size, weight, icon, category, trade prices, flags
- **`Building`** — type, size (x/y/z), power consumption, power type/subtype, recipe tags, modules, name override
- **`CraftingRecipe`** — inputs, outputs (both items and elements/fluids), time, tags, category
- **`Research`** — name, description, costs, dependencies, crafting unlocks, seconds per science item
- **`Element`** — name, pipe content type (gas/liquid), properties
- **`ExplorationUnlock`** — title, category, prerequisites, crafting recipe unlocks
- **`SkyPlatformUpgrade`** — name, cost, effects, prerequisites
- **`ItemCategory`**, **`RecipeCategory`**, **`CraftingTag`** — supporting lookup tables
- **`TerrainBlock`**, **`OreVein`**, **`Quest`** — additional categories

Helper types: `CraftingIO` (amount + identifier for recipe inputs/outputs).

### `loader.py`

Low-level YAML loading. Reads the `StreamingAssets/Entities/` directory structure, identifies entity categories, and parses YAML files into raw dictionaries.

### `game_data.py`

The central `GameData` class. Constructed via `GameData.from_game_dir(path)`, it:

- Loads all entity categories via `loader.py`
- Instantiates model objects from raw YAML
- Builds cross-reference indices:
  - `_recipe_output_index` — item identifier → recipes that produce it
  - `_recipe_input_index` — item identifier → recipes that consume it
  - `_building_to_item_index` — building identifier → item that places it
  - `_building_recipe_index` — building identifier → recipes it can craft (via tag matching)
  - `_research_unlock_index` — recipe/item identifier → research that unlocks it

### `lua_export.py`

Converts `GameData` into Lua source files compatible with `mw.loadData()`. Each module is a Lua table keyed by entity identifier. Produces ~27 modules including:

- `Items.lua`, `Buildings.lua`, `Recipes.lua`, `Research.lua`, `Elements.lua`
- `ExplorationUnlocks.lua`, `SkyPlatformUpgrades.lua`
- `ItemCategories.lua`, `RecipeCategories.lua`, `CraftingTags.lua`
- `TerrainBlocks.lua`, `OreVeins.lua`, `Quests.lua`, `Achievements.lua`
- `BuildingRecipeIndex.lua`, `ItemBuildingIndex.lua`, `NameIndex.lua`
- `RecipeIndex.lua`, `ResearchIndex.lua`, `UpgradePaths.lua`

### `page_generator.py`

Generates complete wikitext for every entity that merits a wiki page (~1,437 pages total across six page types):

- **Item pages** — infobox, obtaining recipes, usage recipes, research unlock, navbox
- **Building pages** — infobox, construction recipe, usage recipes, research unlock, upgrade path, navbox
- **Research pages** — infobox, unlock list (recipe cards + non-recipe bullets), leads-to section, tech tree breadcrumb, navbox
- **Element pages** — infobox, produced-by and used-in recipe sections, transport info, navbox
- **Exploration Unlock pages** — infobox, description, prerequisite chain
- **Sky Platform Upgrade pages** — infobox, description, prerequisites

Each page includes a contextual lead paragraph (not generic filler) and handles disambiguation when multiple entities share a display name.

### `navbox_generator.py`

Generates navigation templates and supporting pages:

- **Navbox Items** — items grouped by category
- **Navbox Buildings** — 16 functional groups (Production, Power Generation, Logistics, etc.)
- **Navbox Research** — grouped by dependency tier (computed recursively)
- **Navbox Elements** — grouped by state (Gases, Liquids)
- **Navbox Exploration Unlocks** — exploration unlock categories
- **Navbox Space Station Upgrades** — upgrade categories
- **Research Tree** — sortable wikitables per tier showing unlocks, prerequisites, and costs

### `preview.py`

Generates a static HTML site from wikitext pages for local browsing without wiki access. Dark-themed, with cross-page links, template placeholder rendering, and per-type index pages.

### `wiki_backup.py`

Downloads all pages from a MediaWiki site via the API for local reference.

### `wiki_diff.py`

Compares generated pages against a wiki backup. Produces a report of new, changed, unchanged, and removed pages plus unified diffs.

### `wiki_upload.py`

Handles authenticated page uploads to a MediaWiki site. Supports dry-run mode, incremental updates (skips unchanged pages), bot flag, configurable rate limiting, and automatic CSRF token refresh.

---

## Wiki Modules - `wiki_modules/`

These files are uploaded to the wiki and form the rendering layer. All templates use `<noinclude>{{doc}}</noinclude>` to load their `/doc` subpage, and all doc pages are wrapped in `{{doc/start}}` / `{{doc/end}}`.

### Lua Rendering Modules

#### `Module_Infobox.lua`

The main infobox renderer. Entry points:

- `p.item(frame)` — item infobox (icon, stack size, weight, category, trade prices)
- `p.building(frame)` — building infobox (type, size, power, recipe tags, upgrade path, walkway connection)
- `p.research(frame)` — research infobox (tier, costs, prerequisites, total time)
- `p.element(frame)` — element infobox (state, pipe colour)
- `p.exploration_unlock(frame)` — exploration unlock infobox
- `p.sky_platform(frame)` — Space Station upgrade infobox
- `p.research_card(frame)` — compact inline research summary card

Styles loaded from `Template:Infobox/styles.css`.

#### `Module_RecipeCard.lua`

Renders visual recipe cards showing inputs → outputs, base craft time, and per-building throughput rates. Entry points:

- `p.main(frame)` — cards for all recipes producing or consuming a given item/element
- `p.building(frame)` — cards for all recipes a specific building can craft
- `p.recipe(frame)` — single card for a specific recipe by identifier

Styles loaded from `Template:RecipeCard/styles.css`.

#### `Module_RecipeTable.lua`

Renders recipe information as sortable wikitables. Entry points:

- `p.main(frame)` — table for all recipes producing or consuming an item/element
- `p.building(frame)` — table for all recipes a given building can craft
- `p.recipe(frame)` — single-row table for a specific recipe

#### `Module_ItemLink.lua`

Renders inline icon+name links. Supports lookup by identifier or display name, optional icon size, `noicon`, `notext`, `nolink`, and quantity prefix.

#### `Module_Achievements.lua`

Renders the Achievements page, grouping achievements by category with images and descriptions.

#### `Module_Data_Buildings.lua`

Static Lua data table (578 entries) containing building metadata not available from the auto-generated data modules: crafting time modifiers, power core slots, workstation effect tags, etc. **Do not edit directly** — regenerate via `foundry-parser generate-lua`.

### CSS Files

| Local file | Wiki title | Used by |
|---|---|---|
| `Template_Infobox_styles.css` | `Template:Infobox/styles.css` | `Module:Infobox` |
| `Template_RecipeCard_styles.css` | `Template:RecipeCard/styles.css` | `Module:RecipeCard` |
| `Template_Navbox2_style.css` | `Template:Navbox2/style.css` | `Template:Navbox2` |

### Template Wrappers

| Template | Invokes | Purpose |
|----------|---------|---------|
| `{{Infobox}}` | `Module:Infobox` | Generic dispatcher (routes by `type=` parameter) |
| `{{Infobox Item}}` | `Module:Infobox\|item` | Item infobox |
| `{{Infobox Building}}` | `Module:Infobox\|building` | Building infobox |
| `{{Infobox Research}}` | `Module:Infobox\|research` | Research infobox |
| `{{Infobox Element}}` | `Module:Infobox\|element` | Element infobox |
| `{{Infobox Exploration Unlock}}` | `Module:Infobox\|exploration_unlock` | Exploration unlock infobox |
| `{{Infobox Sky Platform Upgrade}}` | `Module:Infobox\|sky_platform` | Space Station upgrade infobox |
| `{{Research Card}}` | `Module:Infobox\|research_card` | Compact inline research summary |
| `{{RecipeCard}}` | `Module:RecipeCard\|main` | Recipe cards for an item/element |
| `{{RecipeCard Building}}` | `Module:RecipeCard\|building` | Recipe cards for a building |
| `{{RecipeCard Recipe}}` | `Module:RecipeCard\|recipe` | Single recipe card by identifier |
| `{{RecipeTable}}` | `Module:RecipeTable\|main` | Recipe table for an item/element |
| `{{RecipeTable Building}}` | `Module:RecipeTable\|building` | Recipe table for a building |
| `{{RecipeTable Recipe}}` | `Module:RecipeTable\|recipe` | Single-row recipe table |
| `{{ItemLink}}` | `Module:ItemLink\|main` | Inline icon+name link |
| `{{Navbox2}}` | `Module:Navbox` | Base navbox wrapper (used by all navboxes) |
| `{{Navbox Buildings}}` | via `{{Navbox2}}` | Buildings navigation box |
| `{{Navbox Research}}` | via `{{Navbox2}}` | Research navigation box |
| `{{Devblog}}` | — | Standard header for Foundry Fridays DevBlog pages |
| `{{DevblogsNav}}` | — | Navigation box for DevBlog pages |

---

## Generated Output Directories

These directories are created by running the CLI commands and are not checked into version control:

| Directory | Created by | Contents |
|-----------|-----------|----------|
| `lua_modules/` | `generate-lua` | ~27 `.lua` files for wiki upload to `Module:Data/*` |
| `wiki_pages/` | `generate-pages` | ~1,437 `.wikitext` files (one per entity page) |
| `wiki_pages/navboxes/` | `generate-navboxes` | Navbox templates and Research Tree page |
| `wiki_backup/` | `backup-wiki` | Downloaded wiki pages organised by namespace |
| `diff_report/` | `diff-wiki` | Diff analysis (summary, JSON report, individual diffs) |
| `preview/` | `preview` | Static HTML site (open `index.html` in browser) |

---

## Wiki Data Architecture

The wiki uses MediaWiki v1.43.1 with Scribunto (Lua 5.1) and ParserFunctions. It does **not** have Cargo or Semantic MediaWiki.

### Data flow on the wiki

```
Module:Data/Items (mw.loadData)   ->  Module:Infobox     ->  {{Infobox Item}}
Module:Data/Buildings              ->  Module:RecipeCard  ->  {{RecipeCard}}
Module:Data/Recipes                ->  Module:RecipeTable ->  {{RecipeTable}}
Module:Data/Research               ->  Module:ItemLink    ->  {{ItemLink}}
Module:Data/NameIndex              ->  (name resolution)
Module:Data/BuildingRecipeIndex    ->  (crafter lookup)
Module:Data/ItemBuildingIndex      ->  (building-item mapping)
```

### Key design decisions

- **`mw.loadData()`** is used for all data modules — it returns read-only tables shared across all `#invoke` calls on a page, saving memory. Because of this, `pairs()` does not work on data module tables; use direct key lookups only.
- **NameIndex** maps display names to `{type, id}` pairs so that templates can find the data keyed by `_base_xf_steel_beams` from a page named "Steel Beams".
- **No recipe pages** — recipes are embedded in item and building pages rather than having their own pages.
- **Building names** are resolved from `name_override` (if set) or by looking up the item that places the building via `ItemBuildingIndex`.
- **Power system** has two voltage levels: Low Voltage (PCM, distributed via building blocks) and High Voltage (uses power lines).
- **`mw.loadData()` proxy limitation** — data module tables are read-only proxies; `pairs()` and `ipairs()` do not work on them.

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

For patch notes, run `fetch_patch.py` separately after each update:

```bash
# See what's new
python fetch_patch.py --list

# Fetch the patch note
python fetch_patch.py <API_GID>

# Review the generated file, then upload via the wiki UI or upload-wiki
```

---

## Configuration and Conventions

### Game directory

The toolkit expects the standard Steam installation layout:

```
FOUNDRY/
└── StreamingAssets/
    └── Entities/
        ├── BuildableObjectTemplate/
        ├── ItemTemplate/
        ├── CraftingRecipeTemplate/
        ├── ResearchTemplate/
        ├── ElementTemplate/
        └── ... (many more entity categories)
```

### Entity identifiers

All entities have a unique string identifier (e.g. `_base_xf_steel_beams`, `_base_advanced_smelter`). These are used as keys in Lua data modules and as lookup parameters in templates.

### Page naming

Wiki pages use the entity's display name (e.g. "Steel Beams", "Advanced Smelter"). The `NameIndex` module bridges display names back to identifiers for data lookup. Disambiguation suffixes (e.g. `(Research)`, `(1)`, `(2)`) are added automatically when multiple entities share a name.

### Icon convention

Item icons on the wiki follow the naming convention `Item_<Page Name>.<ext>` (e.g. `Item_Steel_Beams.png`). The `rename_icons.py` utility handles batch renaming of exported icons to this format.

### Building type classification

Buildings are classified by their `type` field into functional groups for navbox organisation. The mapping is defined in `navbox_generator.py`'s `_BUILDING_GROUPS` dictionary and covers 16 groups: Production, Modular Buildings, Assembly Lines, Power Generation, Power Distribution, Solid Item Logistics, Liquid Handling, Storage, Resource Gathering, Rail Transport, Construction, Data System, Infrastructure, Science, Recycling, and Miscellaneous.

---

## Dependencies

**Core** (always required):
- Python 3.10+
- `pyyaml` — YAML parsing

**Wiki features** (optional, install with `pip install -e ".[wiki]"`):
- `requests` — wiki backup and upload via MediaWiki API

**`fetch_patch.py`**: no additional dependencies (uses Python standard library only).

---

## License

GNU GPL v3
