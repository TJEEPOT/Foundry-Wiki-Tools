"""
Navbox Generator

Generates MediaWiki navbox templates from game data, grouping entities
by category/type for bottom-of-page navigation.

Uses {{Navbox2}} format compatible with the existing Foundry wiki.

Usage:
    from foundry_parser.navbox_generator import generate_all_navboxes
    from foundry_parser.game_data import GameData

    gd = GameData.from_game_dir(Path("..."))
    generate_all_navboxes(gd, Path("wiki_pages/navboxes/"))
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .game_data import GameData
from .models import Building, Item
from .page_generator import PageTitleRegistry


# ======================================================================
# Building type -> navbox group mapping
# ======================================================================

_BUILDING_GROUPS = {
    "Production": {
        "AutoProducer", "Producer", "ResourceConverter",
        "ModularEntityProducer", "BlastFurnace", "Dissolver",
        "QuarryBuilding",
    },
    "Modular Buildings": {
        "ModularEntityModule", "GenericModularBuilding",
    },
    "Assembly Lines": {
        "AL_EndConsumer", "AL_Merger", "AL_Producer",
        "AL_Rail", "AL_Splitter", "AL_Start",
    },
    "Power Generation": {
        "LvgGenerator", "BurnerGenerator", "Boiler",
        "SolarPanel", "NPP_Reactor", "NPP_SteamTurbine",
        "NPP_CoolingTower", "GeothermalGenerator",
    },
    "Power Distribution": {
        "PowerPole", "Transformer", "Battery",
    },
    "Solid Item Logistics": {
        "Conveyor", "ConveyorBalancer", "FreightElevator",
        "Loader", "ShippingPad", "DroneTransport",
        "LogisticsTower",
    },
    "Liquid Handling": {
        "Pipe", "Pump", "PipeIntake", "ModularFluidTank",
        "Tank", "FrackingTower", "Pumpjack",
    },
    "Storage": {
        "Storage",
    },
    "Resource Gathering": {
        "DroneMiner", "OreVeinMiner", "EndlessMiner",
        "ScanningEntity", "GeologicalScanner",
    },
    "Rail Transport": {
        "TrainStation", "TrainLoadingStation", "TrainSignal",
    },
    "Construction": {
        "ConstructionDronePort", "ConstructionWarehouse",
        "TransportDronePort",
    },
    "Data System": {
        "DataCable", "DataCompareEntity", "DataMemoryEntity",
        "DataProcessingEntity", "DataSourceEntity",
    },
    "Infrastructure": {
        "ElevatorStation", "Escalator", "Walkway", "Door",
        "BuildingPart", "Light", "Sign", "EmergencyBeacon",
        "BaseStation", "RadioTower", "StationProp",
        "StationShuttlePad",
    },
    "Science": {
        "ResearchEntity",
    },
    "Recycling": {
        "Recycler",
    },
    "Miscellaneous": {
        "Generic", "GenericPowerConsumer", "ManagedGenericEntity",
        "Workstation", "BuddyKennel",
    },
}

# Reverse lookup: type -> group name
_TYPE_TO_GROUP: dict[str, str] = {}
for group_name, types in _BUILDING_GROUPS.items():
    for t in types:
        _TYPE_TO_GROUP[t] = group_name

# Types that should NOT appear in navboxes
_BUILDING_SKIP_TYPES = frozenset([
    "TerrainBlock", "WorldDecorMineAble", "ResourceNode",
])


# ======================================================================
# Navbox formatting
# ======================================================================

def _navbox_header(title: str) -> str:
    """Generate the opening of a Navbox2 template."""
    return (
        "<includeonly>\n"
        "{{Navbox2\n"
        "| name =\n"
        f"| title = {title}\n"
        "| listclass = hlist\n"
        '| striped = "even"\n'
    )


def _navbox_group(num: int, group_name: str, items: list[tuple[str, str]]) -> str:
    """Generate a single group within a navbox.

    *items* is a list of ``(display_name, page_title)`` pairs.  When the two
    differ (e.g. "Stairs" / "Stairs (Research)") the link is rendered as
    ``[[page_title|display_name]]``; when they are the same a plain
    ``[[page_title]]`` is emitted.  Entries are sorted by display name.
    """
    lines = [f"\n| group{num} = {group_name}\n", f"| list{num} =\n"]
    for display_name, page_title in sorted(items, key=lambda x: x[0]):
        if page_title == display_name:
            lines.append(f"* [[{page_title}]]\n")
        else:
            lines.append(f"* [[{page_title}|{display_name}]]\n")
    return "".join(lines)


def _navbox_footer() -> str:
    """Generate the closing of a Navbox2 template."""
    return (
        "}}</includeonly><noinclude>\n"
        "{{doc}}\n"
        "[[Category:Navigation templates]]\n"
        "</noinclude>\n"
    )


# ======================================================================
# Navbox generators
# ======================================================================

def _format_cmc_name(cmc_id: str) -> str:
    """Convert a creative_mode_category identifier to a display name.

    e.g. "_base_cmct_robots_and_bots" -> "Robots and Bots"
    """
    name = cmc_id.replace("_base_cmct_", "").replace("_", " ").title()
    name = name.replace(" And ", " and ")
    return name


def generate_items_navbox(gd: GameData) -> str:
    """Generate the Items navbox, grouped by creative mode category."""
    groups: dict[str, list[tuple[str, str]]] = {}

    for item_id, item in gd.items.items():
        if not item.name or item.name.startswith("_"):
            continue
        # Skip items that don't merit pages
        if not _item_has_page(item, gd):
            continue

        # Group by creative mode category
        if item.creative_mode_category:
            cat_name = _format_cmc_name(item.creative_mode_category)
        else:
            cat_name = "Other"

        groups.setdefault(cat_name, []).append((item.name, item.name))

    # Add merged pages that don't come from individual items
    for merged_name in _MERGED_NAVBOX_NAMES:
        groups.setdefault("Other", []).append((merged_name, merged_name))

    # Order groups logically (roughly matching in-game creative menu order)
    group_order = [
        "Resources", "Components", "Blocks",
        "Handhelds", "Robots and Bots",
        "Assembly Line Components", "Science", "Trains",
        "Other",
    ]

    result = _navbox_header("Items")
    num = 1
    for group_name in group_order:
        if group_name in groups and groups[group_name]:
            result += _navbox_group(num, group_name, groups[group_name])
            num += 1
    # Any remaining groups not in the explicit order
    for group_name in sorted(groups.keys()):
        if group_name not in group_order and groups[group_name]:
            result += _navbox_group(num, group_name, groups[group_name])
            num += 1
    result += _navbox_footer()
    return result


def generate_buildings_navbox(gd: GameData) -> str:
    """Generate the Buildings navbox, grouped by building function."""
    registry = PageTitleRegistry()
    registry.build(gd)

    groups: dict[str, list[tuple[str, str]]] = {}
    seen_names: set[str] = set()

    for building_id, building in gd.buildings.items():
        if building.type in _BUILDING_SKIP_TYPES:
            continue
        name = gd.building_name(building_id)
        if not name or name.startswith("_"):
            continue
        # Skip dev/preview entries — they have no real wiki pages
        if "PREVIEW" in name or "do not use" in name.lower():
            continue
        if name in seen_names:
            continue
        seen_names.add(name)

        page_title = registry.get_title("Building", name)
        group = _TYPE_TO_GROUP.get(building.type, "Other")
        groups.setdefault(group, []).append((name, page_title))

    # Ordered groups
    group_order = [
        "Production", "Modular Buildings", "Assembly Lines",
        "Power Generation", "Power Distribution",
        "Solid Item Logistics", "Liquid Handling",
        "Resource Gathering", "Storage",
        "Rail Transport", "Construction",
        "Data System", "Science", "Infrastructure",
        "Recycling", "Miscellaneous",
    ]

    result = _navbox_header("Buildings")
    num = 1
    for group_name in group_order:
        if group_name in groups and groups[group_name]:
            result += _navbox_group(num, group_name, groups[group_name])
            num += 1
    for group_name in sorted(groups.keys()):
        if group_name not in group_order and groups[group_name]:
            result += _navbox_group(num, group_name, groups[group_name])
            num += 1
    result += _navbox_footer()
    return result


def generate_research_navbox(gd: GameData) -> str:
    """Generate the Research navbox, grouped by dependency tier."""
    registry = PageTitleRegistry()
    registry.build(gd)

    # Compute tiers: tier 0 = no dependencies, tier N = depends on tier N-1
    tiers: dict[str, int] = {}

    def get_tier(res_id: str, visited: set[str] | None = None) -> int:
        if res_id in tiers:
            return tiers[res_id]
        if visited is None:
            visited = set()
        if res_id in visited:
            return 0  # cycle guard
        visited.add(res_id)

        res = gd.research.get(res_id)
        if not res or not res.dependencies:
            tiers[res_id] = 0
            return 0
        max_dep_tier = 0
        for dep in res.dependencies:
            max_dep_tier = max(max_dep_tier, get_tier(dep, visited))
        tier = max_dep_tier + 1
        tiers[res_id] = tier
        return tier

    for res_id in gd.research:
        get_tier(res_id)

    # Group by tier — store (display_name, page_title) tuples
    tier_groups: dict[int, list[tuple[str, str]]] = {}
    for res_id, tier in tiers.items():
        res = gd.research.get(res_id)
        if res and res.name and not res.name.startswith("_"):
            page_title = registry.get_title("Research", res.name)
            tier_groups.setdefault(tier, []).append((res.name, page_title))

    # Name tiers
    tier_names = {
        0: "Tier 1 (Starting)",
        1: "Tier 2",
        2: "Tier 3",
        3: "Tier 4",
        4: "Tier 5",
        5: "Tier 6",
    }

    result = _navbox_header("Research")
    num = 1
    for tier in sorted(tier_groups.keys()):
        group_name = tier_names.get(tier, f"Tier {tier + 1}")
        if tier_groups[tier]:
            result += _navbox_group(num, group_name, tier_groups[tier])
            num += 1
    result += _navbox_footer()
    return result


def generate_elements_navbox(gd: GameData) -> str:
    """Generate the Elements navbox, grouped by state (gas/liquid)."""
    groups: dict[str, list[tuple[str, str]]] = {"Gases": [], "Liquids": [], "Other": []}

    for elem_id, elem in gd.elements.items():
        if not elem.name or elem.name.startswith("_"):
            continue
        if elem.pipe_content_type == 1:
            groups["Gases"].append((elem.name, elem.name))
        elif elem.pipe_content_type == 2:
            groups["Liquids"].append((elem.name, elem.name))
        else:
            groups["Other"].append((elem.name, elem.name))

    result = _navbox_header("Elements")
    num = 1
    for group_name in ["Liquids", "Gases", "Other"]:
        if groups[group_name]:
            result += _navbox_group(num, group_name, groups[group_name])
            num += 1
    result += _navbox_footer()
    return result


# ======================================================================
# Research tree page
# ======================================================================

def generate_research_tree_page(gd: GameData) -> str:
    """Generate a dedicated Research Tree page showing full dependency structure."""
    lines = []
    lines.append("{{DISPLAYTITLE:Research Tree}}")
    lines.append("")
    lines.append(
        "This page shows the full research tree for Foundry, "
        "organised by dependency tier. Each tier's technologies "
        "require at least one technology from the previous tier."
    )
    lines.append("")

    # Compute tiers (same logic as navbox)
    tiers: dict[str, int] = {}

    def get_tier(res_id: str, visited: set[str] | None = None) -> int:
        if res_id in tiers:
            return tiers[res_id]
        if visited is None:
            visited = set()
        if res_id in visited:
            return 0
        visited.add(res_id)
        res = gd.research.get(res_id)
        if not res or not res.dependencies:
            tiers[res_id] = 0
            return 0
        max_dep_tier = 0
        for dep in res.dependencies:
            max_dep_tier = max(max_dep_tier, get_tier(dep, visited))
        tier = max_dep_tier + 1
        tiers[res_id] = tier
        return tier

    for res_id in gd.research:
        get_tier(res_id)

    tier_groups: dict[int, list[tuple[str, str]]] = {}
    for res_id, tier in tiers.items():
        res = gd.research.get(res_id)
        if res and res.name and not res.name.startswith("_"):
            tier_groups.setdefault(tier, []).append((res.name, res_id))

    for tier in sorted(tier_groups.keys()):
        tier_name = f"Tier {tier + 1}"
        if tier == 0:
            tier_name = "Tier 1 (No Prerequisites)"
        lines.append(f"== {tier_name} ==")
        lines.append("")
        lines.append('{| class="wikitable sortable" style="width:100%"')
        lines.append("! Research !! Unlocks !! Prerequisites !! Science Cost")

        for res_name, res_id in sorted(tier_groups[tier]):
            res = gd.research[res_id]

            # Unlocks
            unlocks = []
            for recipe_id in (res.crafting_unlocks or []):
                recipe = gd.recipes.get(recipe_id)
                if recipe and recipe.outputs:
                    out_name = gd.item_name(recipe.outputs[0].identifier)
                    unlocks.append(f"[[{out_name}]]")
                elif recipe:
                    unlocks.append(recipe.name)
            unlock_str = ", ".join(unlocks[:5])
            if len(unlocks) > 5:
                unlock_str += f" (+{len(unlocks) - 5} more)"

            # Prerequisites
            prereqs = []
            for dep_id in (res.dependencies or []):
                dep = gd.research.get(dep_id)
                if dep:
                    prereqs.append(f"[[{dep.name}]]")
            prereq_str = ", ".join(prereqs) if prereqs else "—"

            # Cost
            costs = []
            for cost in (res.costs or []):
                item_name = gd.item_name(cost.identifier)
                costs.append(f"{cost.amount}x {item_name}")
            cost_str = ", ".join(costs) if costs else "—"

            lines.append("|-")
            lines.append(
                f"| [[{res_name}]] || {unlock_str} || {prereq_str} || {cost_str}"
            )

        lines.append("|}")
        lines.append("")

    lines.append("{{Navbox Research}}")
    lines.append("")
    lines.append("[[Category:Research]]")
    lines.append("[[Category:Game Mechanics]]")

    return "\n".join(lines)


# ======================================================================
# World object filtering (mirrors page_generator logic)
# ======================================================================

_WORLD_OBJECT_ID_PATTERNS = (
    "_forest_plant", "_forest_tree", "_forest_rock", "_forest_mushroom",
    "_forest_grouprock",
    "_jungle_palm", "_jungle_tree", "_jungle_plant",
    "_rocky_desert_plant", "_rocky_desert_rock", "_rocky_desert_tree",
    "_sandy_desert_plant", "_sandy_desert_rock", "_sandy_desert_tree",
    "_tundra_tree", "_tundra_large_plant", "_tundra_large_rock",
    "_tundra_medium_rock", "_tundra_rock_pillar",
    "_cave_crystal", "_caveplant", "_cave_stalactite", "_cave_stalagmite",
    "_stalagmite", "_coral_plant", "_kelp_",
    "_mussel_",
    "_gl_birch_", "_gl_fansy_plant",
)

_WORLD_OBJECT_NAMES = frozenset([
    "Tree", "Plant", "Jungle Tree",
    "Boreal Forest Tree", "Boreal Forest Plant", "Boreal Forest Plant Large",
    "Boreal Forest Plant Small", "Boreal Forest Rock",
    "Rocky Desert Plant", "Rocky Desert Rock", "Rocky Desert Tree",
    "Sandy Desert Plant", "Sandy Desert Rock", "Sandy Desert Tree",
    "Tundra Tree 01", "Tundra Tree 02", "Tundra Tree 03",
    "Tundra Large Plant 01", "Tundra Large Plant 02",
    "Tundra Large Rock 01", "Tundra Medium Rock 01", "Tundra Medium Rock 02",
    "Tundra Rock Pillar 01", "Tundra Rock Pillar 02",
    "Cave Plant", "Coral Plant", "Kelp",
    "Stalactite", "Stalagmite",
    "Mussel Small", "Mussel Medium", "Mussel Large",
    "Crystals", "Debris", "Debris I",
    "Large Xeno-Scrap", "Xeno-Scrap Remnants",
    "Commands", "Emotes",
])

_MERGED_PAGE_ITEMS = frozenset([
    "Forest Seed (Plants)", "Forest Seed (Trees)",
    "Rocky Desert Seed (Plants)", "Rocky Desert Seed (Trees)",
    "Sandy Desert Seed (Plants)", "Sandy Desert Seed (Trees)",
    "Tundra Seed (Plants)", "Tundra Seed (Trees)",
    "Tropical Rainforest Seed (Plants)", "Tropical Rainforest Seed (Trees)",
    "Forest Critter", "Jungle Critter", "Rocky Desert Critter",
    "Sandy DesertCritter", "Shrublands Critter", "Tundra Critter",
    "Tropical Rainforest Dirt", "Tundra Dirt", "Rocky Desert Dirt",
    "Dirt",
])

# Merged page navbox names (the combined pages that DO appear)
_MERGED_NAVBOX_NAMES = [
    "Boreal Forest Seed", "Rocky Desert Seed", "Sandy Desert Seed",
    "Tundra Seed", "Tropical Rainforest Seed", "Critter", "Dirt",
]


def _is_world_object(item: Item) -> bool:
    """Return True if item is a world vegetation/decoration not page-worthy."""
    if item.name in _WORLD_OBJECT_NAMES:
        return True
    if item.name in _MERGED_PAGE_ITEMS:
        return True
    item_id_lower = item.identifier.lower()
    for pattern in _WORLD_OBJECT_ID_PATTERNS:
        if pattern in item_id_lower:
            return True
    return False


# ======================================================================
# Helpers
# ======================================================================

def _item_has_page(item: Item, gd: GameData) -> bool:
    """Check if an item merits its own wiki page (mirrors page_generator logic).

    Items that place buildings are excluded — they get a building page instead.
    World objects (plants, trees, rocks) and merged-page items are excluded.
    """
    if not item.name or item.name.startswith("_"):
        return False
    # Filter out world objects and merged-page items
    if _is_world_object(item):
        return False
    # Items that place buildings are covered by building pages
    building = gd.building_for_item(item.identifier)
    if building and building.type not in _BUILDING_SKIP_TYPES:
        bname = gd.building_name(building.identifier)
        if bname and not bname.startswith("_"):
            return False
    producing = gd.recipes_producing(item.identifier)
    consuming = gd.recipes_consuming(item.identifier)
    if not producing and not consuming and not item.can_be_traded:
        if not item.flags or all(f in ("", "NONE") for f in item.flags):
            return False
    return True


# ======================================================================
# Main export
# ======================================================================

def _format_category_name(category_id: str) -> str:
    """Convert a _base_<slug> category identifier to a display name.

    e.g. "_base_personal_mining_drones" -> "Personal Mining Drones"
    """
    name = category_id.replace("_base_", "", 1).replace("_", " ").title()
    name = name.replace(" And ", " and ")
    name = name.replace("Rd ", "R&D ")
    return name


def generate_exploration_unlocks_navbox(gd: GameData) -> str:
    """Generate the Exploration Unlocks navbox, grouped by category."""
    registry = PageTitleRegistry()
    registry.build(gd)

    groups: dict[str, list[tuple[str, str]]] = {}

    for unlock_id, unlock in gd.exploration_unlocks.items():
        if not unlock.title or unlock.title.startswith("_"):
            continue
        cat_name = (
            _format_category_name(unlock.category_id)
            if unlock.category_id
            else "Other"
        )
        page_title = registry.get_title("Exploration Unlock", unlock.title)
        groups.setdefault(cat_name, []).append((unlock.title, page_title))

    parts = [_navbox_header("Exploration Unlocks")]
    for i, (group_name, items) in enumerate(sorted(groups.items()), start=1):
        parts.append(_navbox_group(i, group_name, items))
    parts.append(_navbox_footer())
    return "".join(parts)


def generate_sky_platform_navbox(gd: GameData) -> str:
    """Generate the Space Station Upgrades navbox, grouped by category."""
    registry = PageTitleRegistry()
    registry.build(gd)

    groups: dict[str, list[tuple[str, str]]] = {}

    for upgrade_id, upgrade in gd.sky_platform_upgrades.items():
        if not upgrade.name or upgrade.name.startswith("_"):
            continue
        cat_name = (
            _format_category_name(upgrade.category_id)
            if upgrade.category_id
            else "Other"
        )
        page_title = registry.get_title("Sky Platform", upgrade.name)
        groups.setdefault(cat_name, []).append((upgrade.name, page_title))

    parts = [_navbox_header("Space Station Upgrades")]
    for i, (group_name, items) in enumerate(sorted(groups.items()), start=1):
        # Sort items within each group by display name
        items_sorted = sorted(items, key=lambda x: x[0])
        parts.append(_navbox_group(i, group_name, items_sorted))
    parts.append(_navbox_footer())
    return "".join(parts)


def generate_all_navboxes(
    gd: GameData,
    wiki_modules_dir: Path,
    pages_dir: Path | None = None,
    verbose: bool = True,
) -> dict[str, str]:
    """
    Generate all navbox templates and the research tree page.

    Template_Navbox_*.wikitext files are written to *wiki_modules_dir* so they
    are picked up by the batch-upload Phase 3 (wiki modules) alongside all other
    templates.  The Research Tree page (main namespace, not a Template) is written
    to *pages_dir* if provided, otherwise to *wiki_modules_dir*.

    Returns dict of wiki title -> description.
    """
    wiki_modules_dir.mkdir(parents=True, exist_ok=True)
    tree_dir = pages_dir if pages_dir is not None else wiki_modules_dir
    if pages_dir is not None:
        pages_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    results = {}

    navboxes = [
        ("Template_Navbox_Items.wikitext",                generate_items_navbox,              "Template:Navbox Items",                "Items navigation"),
        ("Template_Navbox_Buildings.wikitext",             generate_buildings_navbox,           "Template:Navbox Buildings",            "Buildings navigation"),
        ("Template_Navbox_Research.wikitext",              generate_research_navbox,            "Template:Navbox Research",             "Research navigation"),
        ("Template_Navbox_Elements.wikitext",              generate_elements_navbox,            "Template:Navbox Elements",             "Elements navigation"),
        ("Template_Navbox_Exploration_Unlocks.wikitext",   generate_exploration_unlocks_navbox, "Template:Navbox Exploration Unlocks",  "Exploration Unlocks navigation"),
        ("Template_Navbox_Space_Station_Upgrades.wikitext",generate_sky_platform_navbox,        "Template:Navbox Space Station Upgrades","Space Station Upgrades navigation"),
    ]

    for filename, generator_fn, title, description in navboxes:
        content = generator_fn(gd)
        (wiki_modules_dir / filename).write_text(content, encoding="utf-8")
        results[title] = description
        log(f"  Generated: {title}")

    # Research Tree page — main namespace, goes to pages_dir
    content = generate_research_tree_page(gd)
    (tree_dir / "Research_Tree.wikitext").write_text(content, encoding="utf-8")
    results["Research Tree"] = "Full research dependency tree"
    log(f"  Generated: Research Tree page")

    log(f"\n  Total: {len(results)} navbox/navigation files")
    return results
