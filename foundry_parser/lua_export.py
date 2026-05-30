"""
Lua Data Module Generator

Converts parsed GameData into Lua source files suitable for uploading
to the wiki as Module:Data/* pages. Each file is a valid Lua table
compatible with mw.loadData().

Usage:
    from foundry_parser.lua_export import export_all_lua
    from foundry_parser.game_data import GameData

    gd = GameData.from_game_dir(Path("..."))
    export_all_lua(gd, Path("lua_output/"))
"""

from __future__ import annotations

from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .game_data import GameData


# ======================================================================
# Lua serialisation
# ======================================================================

def lua_string(s: str) -> str:
    """Escape a string for Lua. Uses double brackets for multiline."""
    if "\n" in s or "\r" in s:
        # Find a level of long brackets that doesn't appear in the string
        level = 0
        while f"]{'=' * level}]" in s:
            level += 1
        eq = "=" * level
        return f"[{eq}[{s}]{eq}]"
    # Simple single-line string
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def lua_value(val: Any, indent: int = 0) -> str:
    """Serialise a Python value to a Lua literal."""
    if val is None:
        return "nil"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val == int(val) and abs(val) < 1e15:
            return str(int(val))
        return f"{val:g}"
    if isinstance(val, str):
        return lua_string(val)
    if isinstance(val, list):
        return _lua_list(val, indent)
    if isinstance(val, dict):
        return _lua_table(val, indent)
    return lua_string(str(val))


def _lua_list(items: list, indent: int) -> str:
    """Serialise a Python list as a Lua array table."""
    if not items:
        return "{}"
    # Short lists of simple values on one line
    if len(items) <= 4 and all(isinstance(v, (str, int, float)) for v in items):
        inner = ", ".join(lua_value(v) for v in items)
        return "{ " + inner + " }"
    pad = "  " * (indent + 1)
    lines = [f"{pad}{lua_value(v, indent + 1)}," for v in items]
    return "{\n" + "\n".join(lines) + "\n" + "  " * indent + "}"


def _lua_table(d: dict, indent: int) -> str:
    """Serialise a Python dict as a Lua table."""
    if not d:
        return "{}"
    pad = "  " * (indent + 1)
    lines = []
    for k, v in d.items():
        lk = k if k.isidentifier() and not _is_lua_keyword(k) else f'[{lua_string(k)}]'
        lines.append(f"{pad}{lk} = {lua_value(v, indent + 1)},")
    return "{\n" + "\n".join(lines) + "\n" + "  " * indent + "}"


_LUA_KEYWORDS = frozenset([
    "and", "break", "do", "else", "elseif", "end", "false", "for",
    "function", "goto", "if", "in", "local", "nil", "not", "or",
    "repeat", "return", "then", "true", "until", "while",
])

def _is_lua_keyword(s: str) -> bool:
    return s in _LUA_KEYWORDS


# ======================================================================
# Field filtering helpers
# ======================================================================

def _skip_default(val: Any) -> bool:
    """Return True if the value is a boring default not worth exporting."""
    if val is None:
        return True
    if val == "" or val == 0 or val == 0.0:
        return True
    if val is False:
        return True
    if isinstance(val, (list, dict)) and len(val) == 0:
        return True
    return False


def _entity_to_dict(obj: Any, include_defaults: set[str] | None = None) -> dict[str, Any]:
    """Convert a dataclass to a filtered dict, skipping _raw and defaults."""
    if include_defaults is None:
        include_defaults = set()
    result = {}
    for f in dc_fields(obj):
        if f.name.startswith("_"):
            continue
        val = getattr(obj, f.name)
        if f.name not in include_defaults and _skip_default(val):
            continue
        # Convert nested dataclass lists (CraftingIO, ElementalIO, etc.)
        if isinstance(val, list) and val and hasattr(val[0], "__dataclass_fields__"):
            val = [_entity_to_dict(v) for v in val]
        elif hasattr(val, "__dataclass_fields__"):
            val = _entity_to_dict(val)
        result[f.name] = val
    return result


# ======================================================================
# Per-category export definitions
# ======================================================================

# Fields that should ALWAYS be included even if zero/empty, because
# their absence would be misleading or they're essential keys.
_ALWAYS = {"identifier", "name"}


def _export_item(item) -> dict[str, Any]:
    """Export an Item for Lua, with curated field set."""
    d = _entity_to_dict(item, include_defaults=_ALWAYS)
    # Rename for wiki clarity
    if "weight_grams" in d:
        grams = d.pop("weight_grams")
        if grams >= 1000:
            d["weight_kg"] = grams / 1000
        else:
            d["weight_g"] = grams
    return d


def _export_building(building, gd: GameData | None = None) -> dict[str, Any]:
    """Export a Building for Lua."""
    d = _entity_to_dict(building, include_defaults=_ALWAYS)
    # Flatten size into top-level for easier Lua access.
    # Some modular buildings (e.g. Fracking Tower) store only a 1×1 anchor tile
    # in the top-level `size` field; their true footprint is in the first entry
    # of `additionalAABBs_input`.  When the top-level footprint is 1×1 and a
    # larger AABB is present, use the AABB dimensions instead.  Total height is
    # localOffset.y + aabb.size.y.
    if "size" in d:
        s = d.pop("size")
        sx, sy, sz = s.get("x", 0), s.get("y", 0), s.get("z", 0)
        raw = building._raw or {}
        aabbs = raw.get("additionalAABBs_input") or []
        if sx == 1 and sz == 1 and aabbs:
            ab = aabbs[0]
            ab_size = ab.get("size") or {}
            ab_off  = ab.get("localOffset") or {}
            ab_x = ab_size.get("x", 1)
            ab_z = ab_size.get("z", 1)
            if ab_x > 1 or ab_z > 1:
                sx = ab_x
                sz = ab_z
                sy = int((ab_off.get("y") or 0) + (ab_size.get("y") or sy))
        d["size_x"] = sx
        d["size_y"] = sy
        d["size_z"] = sz
    # Compute display name: prefer name_override, else placing item name
    if building.name_override:
        d["name"] = building.name_override
    elif gd:
        item_id = gd._building_to_item_index.get(building.identifier)
        if item_id:
            item = gd.items.get(item_id)
            if item:
                d["name"] = item.name
    # Ensure name field exists
    if "name" not in d:
        d["name"] = d.get("name_override", building.identifier)

    # Drop the raw io_fluid_boxes list (too complex for Lua) and replace
    # with computed pipe_slots_in / pipe_slots_out counts
    d.pop("io_fluid_boxes", None)
    if building.io_fluid_boxes:
        pipe_in = 0
        pipe_out = 0
        for box in building.io_fluid_boxes:
            connectors = box.get("connectors", [])
            n = max(len(connectors), 1) if connectors else 1
            if box.get("isInput", False):
                pipe_in += n
            else:
                pipe_out += n
        if pipe_in > 0:
            d["pipe_slots_in"] = pipe_in
        if pipe_out > 0:
            d["pipe_slots_out"] = pipe_out

    # Compute conveyor slot counts from item_buffer_slots
    if building.item_buffer_slots:
        conv_in = 0
        conv_out = 0
        for group in building.item_buffer_slots:
            slots = group.get("slots", [])
            for slot in slots:
                flavor = slot.get("flavorType", "")
                if flavor == "Input":
                    conv_in += 1
                elif flavor == "Output":
                    conv_out += 1
        if conv_in > 0:
            d["conveyor_slots_in"] = conv_in
        if conv_out > 0:
            d["conveyor_slots_out"] = conv_out

    # Drop item_buffer_slots raw data (complex nested structure)
    d.pop("item_buffer_slots", None)

    # Compute power generation for producer buildings
    if building.power_subtype == "POWER_SOURCE":
        # Solar panels
        if building.solar_output_max:
            d["power_generation_kw"] = building.solar_output_max
            if building.solar_output_min:
                d["power_generation_min_kw"] = building.solar_output_min
            d["power_gen_type"] = "Solar"
        # Burner generators (high voltage)
        elif building.burner_generator_rate:
            d["power_generation_kw"] = building.burner_generator_rate
            d["power_gen_type"] = "Burner"
        # LVG generators (biomass burner, low voltage)
        elif building.lvg_generator_rate:
            d["power_generation_kw"] = building.lvg_generator_rate
            d["power_gen_type"] = "Burner"
        # NPP steam turbine
        elif building.npp_turbine_rate:
            d["power_generation_kw"] = building.npp_turbine_rate
            d["power_gen_type"] = "Nuclear"

    # Battery capacity in MJ
    if building.battery_capacity_kj:
        d["capacity_mj"] = round(building.battery_capacity_kj / 1000, 2)

    # Transformer rate in kW
    if building.transformer_rate:
        d["transformer_rate_kw"] = building.transformer_rate

    return d


def _export_recipe(recipe) -> dict[str, Any]:
    """Export a CraftingRecipe for Lua."""
    d = _entity_to_dict(recipe, include_defaults=_ALWAYS)
    # Add computed time_seconds for convenience
    if recipe.time_ms:
        d["time_seconds"] = recipe.time_seconds
    return d


def _export_research(research) -> dict[str, Any]:
    """Export a Research node for Lua."""
    return _entity_to_dict(research, include_defaults=_ALWAYS)


def _export_generic(obj) -> dict[str, Any]:
    """Generic export for simpler entity types."""
    return _entity_to_dict(obj, include_defaults=_ALWAYS)


# ======================================================================
# Module file generation
# ======================================================================

def _generate_module(
    module_name: str,
    entities: dict[str, Any],
    export_fn,
    header_comment: str = "",
) -> str:
    """Generate a complete Lua module source string."""
    lines = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append(f"-- {module_name}")
    lines.append(f"-- Auto-generated by foundry_parser on {timestamp}")
    lines.append(f"-- {len(entities)} entries")
    if header_comment:
        lines.append(f"-- {header_comment}")
    lines.append("-- DO NOT EDIT - regenerate from game data instead")
    lines.append("")
    lines.append("return {")

    for identifier in sorted(entities.keys()):
        entity = entities[identifier]
        try:
            data = export_fn(entity)
        except Exception as e:
            lines.append(f"  -- SKIPPED {identifier}: {e}")
            continue

        lines.append(f"  [{lua_string(identifier)}] = {{")
        for key, val in data.items():
            lk = key if key.isidentifier() and not _is_lua_keyword(key) else f"[{lua_string(key)}]"
            lines.append(f"    {lk} = {lua_value(val, 2)},")
        lines.append("  },")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# ======================================================================
# Cross-reference index modules
# ======================================================================

def _generate_recipe_index(gd: GameData) -> str:
    """Generate Module:Data/RecipeIndex with output->recipe and input->recipe mappings."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "-- Module:Data/RecipeIndex",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- Cross-reference indices for recipe lookups",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
        "  -- item_id -> list of recipe_ids that produce it",
        "  outputs = {",
    ]
    for item_id in sorted(gd._recipe_outputs_index.keys()):
        recipe_ids = sorted(gd._recipe_outputs_index[item_id])
        vals = ", ".join(lua_string(r) for r in recipe_ids)
        lines.append(f"    [{lua_string(item_id)}] = {{ {vals} }},")
    lines.append("  },")
    lines.append("")
    lines.append("  -- item_id -> list of recipe_ids that consume it")
    lines.append("  inputs = {")
    for item_id in sorted(gd._recipe_inputs_index.keys()):
        recipe_ids = sorted(gd._recipe_inputs_index[item_id])
        vals = ", ".join(lua_string(r) for r in recipe_ids)
        lines.append(f"    [{lua_string(item_id)}] = {{ {vals} }},")
    lines.append("  },")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_building_recipe_index(gd: GameData) -> str:
    """Generate Module:Data/BuildingRecipeIndex: building_id -> recipe_ids."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "-- Module:Data/BuildingRecipeIndex",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- building_id -> list of recipe_ids the building can craft",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]
    for building_id in sorted(gd._building_recipes_index.keys()):
        recipe_ids = sorted(gd._building_recipes_index[building_id])
        vals = ", ".join(lua_string(r) for r in recipe_ids)
        lines.append(f"  [{lua_string(building_id)}] = {{ {vals} }},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_research_index(gd: GameData) -> str:
    """Generate Module:Data/ResearchIndex: recipe_id -> list of research_ids."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "-- Module:Data/ResearchIndex",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- recipe_id -> list of research_ids that unlock it",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]
    for recipe_id in sorted(gd._research_unlocks_index.keys()):
        research_ids = sorted(gd._research_unlocks_index[recipe_id])
        vals = ", ".join(lua_string(r) for r in research_ids)
        lines.append(f"  [{lua_string(recipe_id)}] = {{ {vals} }},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_recipe_building_names(gd: GameData) -> str:
    """Generate Module:Data/RecipeBuildingNames: recipe_id -> list of building display names.

    Pre-computes which buildings can craft each recipe so the Lua rendering
    code only needs a single key lookup — no iteration over mw.loadData()
    proxy tables required.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Only include building types that are actual player-facing crafting stations.
    # Other types (Door, ConstructionDronePort, StationProp, etc.) share recipe
    # tags for internal game logic but don't present a crafting UI to the player.
    CRAFTING_BUILDING_TYPES = {"Producer", "AutoProducer", "QuarryBuilding"}

    # Build tag -> set of building display names
    tag_to_names: dict[str, set[str]] = {}
    for building_id, building in gd.buildings.items():
        if building.type not in CRAFTING_BUILDING_TYPES:
            continue

        # Resolve display name
        name = (
            building.name_override
            if building.has_name_override and building.name_override
            else None
        )
        if not name:
            item_id = gd._building_to_item_index.get(building_id)
            if item_id:
                item = gd.items.get(item_id)
                if item:
                    name = item.name
        if not name:
            name = building_id

        # Collect all tag sources for this building
        all_tags: set[str] = set(building.producer_recipe_tags)
        if building.auto_producer_tag:
            all_tags.add(building.auto_producer_tag)
        all_tags.update(building.modular_producer_recipe_tags)

        for tag in all_tags:
            tag_to_names.setdefault(tag, set()).add(name)

    # Map each recipe to the buildings that can craft it
    recipe_to_buildings: dict[str, set[str]] = {}
    for recipe_id, recipe in gd.recipes.items():
        names: set[str] = set()
        for tag in recipe.tags:
            names.update(tag_to_names.get(tag, set()))
        if names:
            recipe_to_buildings[recipe_id] = names

    lines = [
        "-- Module:Data/RecipeBuildingNames",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- recipe_id -> list of building display names that can craft it",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]
    for recipe_id in sorted(recipe_to_buildings.keys()):
        names = sorted(recipe_to_buildings[recipe_id])
        vals = ", ".join(lua_string(n) for n in names)
        lines.append(f"  [{lua_string(recipe_id)}] = {{ {vals} }},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_recipe_crafting_data(gd: GameData) -> str:
    """Generate Module:Data/RecipeCraftingData: pre-computed per-building craft times.

    For each recipe, lists the buildings that can craft it along with each
    building's actual craft time (base_time / speed_modifier).  Uses a flat
    key layout (n, n1/t1, n2/t2, ...) to avoid nested mw.loadData() proxy
    iteration issues.

    Structure per recipe:
        ["recipe_id"] = { n = 3, n1 = "Hand", t1 = 3, n2 = "Assembler I", t2 = 3, ... }
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    CRAFTING_BUILDING_TYPES = {"Producer", "AutoProducer", "QuarryBuilding"}

    # Build tag -> list of (display_name, time_modifier)
    # AutoProducers have two modifier sets:
    #   producer_recipe_tags -> producer_time_modifier
    #   auto_producer_tag    -> auto_producer_time_modifier
    tag_to_buildings: dict[str, list[tuple[str, float]]] = {}

    for building_id, building in gd.buildings.items():
        if building.type not in CRAFTING_BUILDING_TYPES:
            continue

        # Resolve display name
        name = (
            building.name_override
            if building.has_name_override and building.name_override
            else None
        )
        if not name:
            item_id = gd._building_to_item_index.get(building_id)
            if item_id:
                item = gd.items.get(item_id)
                if item:
                    name = item.name
        if not name:
            name = building_id

        prod_mod = building.producer_time_modifier or 1.0
        auto_mod = building.auto_producer_time_modifier or 1.0

        # Producer tags use producer_time_modifier
        for tag in building.producer_recipe_tags:
            tag_to_buildings.setdefault(tag, []).append((name, prod_mod))

        # Auto-producer tag uses auto_producer_time_modifier
        if building.auto_producer_tag:
            tag_to_buildings.setdefault(building.auto_producer_tag, []).append(
                (name, auto_mod)
            )

        # Modular producer tags use producer_time_modifier
        for tag in building.modular_producer_recipe_tags:
            tag_to_buildings.setdefault(tag, []).append((name, prod_mod))

    # Sort building lists by name for deterministic output
    for tag in tag_to_buildings:
        tag_to_buildings[tag].sort(key=lambda x: x[0])

    # Build per-recipe data
    lines = [
        "-- Module:Data/RecipeCraftingData",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- recipe_id -> flat table of building names and craft times",
        "-- Access: entry.n = count, entry.n1/t1 = first building name/time, etc.",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]

    for recipe_id in sorted(gd.recipes.keys()):
        recipe = gd.recipes[recipe_id]
        base_time = recipe.time_seconds
        if not base_time or base_time <= 0:
            continue

        # Collect best modifier per building (highest = fastest)
        best_modifier: dict[str, float] = {}
        has_hand = False

        for tag in recipe.tags:
            if tag == "character":
                has_hand = True
                continue
            for bname, modifier in tag_to_buildings.get(tag, []):
                if bname not in best_modifier or modifier > best_modifier[bname]:
                    best_modifier[bname] = modifier

        # Build final list: Hand first, then machines sorted by name
        buildings: list[tuple[str, float]] = []
        if has_hand:
            hand_time = int(base_time) if base_time == int(base_time) else base_time
            buildings.append(("Hand", hand_time))

        for bname in sorted(best_modifier.keys()):
            modifier = best_modifier[bname]
            actual_time = round(base_time / modifier, 2)
            # Clean up floating point: use int if whole number
            if actual_time == int(actual_time):
                actual_time = int(actual_time)
            buildings.append((bname, actual_time))

        if not buildings:
            continue

        parts = [f"n = {len(buildings)}"]
        for i, (bname, btime) in enumerate(buildings, 1):
            parts.append(f"n{i} = {lua_string(bname)}")
            parts.append(f"t{i} = {btime}")

        lines.append(f"  [{lua_string(recipe_id)}] = {{ {', '.join(parts)} }},")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_item_building_index(gd: GameData) -> str:
    """Generate Module:Data/ItemBuildingIndex: bidirectional item<->building map."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "-- Module:Data/ItemBuildingIndex",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- Bidirectional mapping between items and buildings",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
        "  item_to_building = {",
    ]
    for item_id in sorted(gd._item_to_building_index.keys()):
        building_id = gd._item_to_building_index[item_id]
        lines.append(f"    [{lua_string(item_id)}] = {lua_string(building_id)},")
    lines.append("  },")
    lines.append("  building_to_item = {")
    for building_id in sorted(gd._building_to_item_index.keys()):
        item_id = gd._building_to_item_index[building_id]
        lines.append(f"    [{lua_string(building_id)}] = {lua_string(item_id)},")
    lines.append("  },")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_upgrade_paths(gd: GameData) -> str:
    """Generate Module:Data/UpgradePaths: building_id -> flat upgrade chain.

    For each building that belongs to a conversion group, stores the ordered
    list of building display names in the chain using flat keys (n, n1, n2, ...).
    Only includes buildings with resolved display names (filters out internal
    variant IDs like slope-down duplicates).

    When a single conversion group contains multiple distinct sub-chains
    (e.g. "Conveyor I-IV" and "Conveyor Slope I-IV"), they are split into
    separate upgrade paths by grouping on the name prefix before the trailing
    tier numeral (I, II, III, IV, V, etc.).
    """
    import re
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build conversion_group -> ordered list of (building_id, display_name)
    from collections import defaultdict

    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for building_id, building in gd.buildings.items():
        if not building.conversion_group:
            continue
        name = gd.building_name(building_id)
        # Filter out internal buildings whose name didn't resolve
        if name.startswith("_base_"):
            continue
        groups[building.conversion_group].append((building_id, name))

    # Split groups that contain multiple distinct sub-chains.
    # Detect by stripping trailing roman numerals from names and grouping
    # on the remaining prefix.  e.g. "Conveyor Slope III" -> "Conveyor Slope"
    _roman_suffix = re.compile(r'\s+(I{1,3}|IV|V|VI{0,3})$')

    def _name_prefix(name: str) -> str:
        """Return name without trailing tier numeral."""
        return _roman_suffix.sub('', name)

    split_chains: list[list[tuple[str, str]]] = []
    for _group_id, members in groups.items():
        # Group members by name prefix
        sub: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for bid, name in members:
            sub[_name_prefix(name)].append((bid, name))
        for chain in sub.values():
            if len(chain) >= 2:
                split_chains.append(chain)

    # Build per-building entries
    lines = [
        "-- Module:Data/UpgradePaths",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- building_id -> flat table of upgrade chain building names",
        "-- Access: entry.n = count, entry.n1 = first name, etc.",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]

    # Sort chains by first building_id for stable output
    split_chains.sort(key=lambda c: c[0][0])

    for members in split_chains:
        # Build the flat entry for each building in this chain
        for building_id, _name in members:
            parts = [f"n = {len(members)}"]
            for i, (_bid, bname) in enumerate(members, 1):
                parts.append(f"n{i} = {lua_string(bname)}")
            lines.append(
                f"  [{lua_string(building_id)}] = {{ {', '.join(parts)} }},"
            )

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_achievements_data(gd: GameData) -> str:
    """Generate Module:Data/Achievements from all AchievementDatabaseTemplate entries.

    Collects every achievement list from every database file, resolves
    display names for referenced items/buildings/research/upgrades/quests,
    and emits a flat keyed-by-internalId table sorted by (sortOrder, internalId).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Flatten all achievements from all 8 YAML files
    all_achievements: list[dict] = []
    for _db_id, db_data in gd.raw_categories.get("AchievementDatabaseTemplate", {}).items():
        for a in db_data.get("achievements", []):
            all_achievements.append(a)

    all_achievements.sort(
        key=lambda a: (a.get("sortOrder", 999), a.get("internalId", ""))
    )

    lines = [
        "-- Module:Data/Achievements",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        f"-- {len(all_achievements)} entries",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]

    for a in all_achievements:
        internal_id = a.get("internalId", "")
        if not internal_id:
            continue

        atype = a.get("achievementType", "")

        entry: dict[str, Any] = {
            "displayName": a.get("displayName", ""),
            "description": a.get("description", ""),
            "achievementType": atype,
            "sortOrder": a.get("sortOrder", 0),
        }

        icon = a.get("iconIdentifier", "")
        if icon:
            entry["iconIdentifier"] = icon

        if a.get("hiddenUntilUnlocked", False):
            entry["hiddenUntilUnlocked"] = True

        # ---- type-specific fields with resolved names ----

        if atype == "MULTI_ITEMCREATION":
            needed = a.get("multiItemCreationsNeeded", 0)
            if needed:
                entry["multiItemCreationsNeeded"] = needed
            raw_items = [
                x.get("itemIdentifier", "")
                for x in a.get("multiItemCreations", [])
                if x.get("itemIdentifier")
            ]
            if raw_items:
                filtered_ids, names = [], []
                for iid in raw_items:
                    item = gd.items.get(iid)
                    # Skip items with no resolvable display name (raw internal IDs)
                    name = item.name if item else iid
                    if name and not name.startswith("_"):
                        filtered_ids.append(iid)
                        names.append(name)
                if filtered_ids:
                    entry["multiItemCreations"] = filtered_ids
                    entry["multiItemCreationNames"] = names

        elif atype == "MULTI_BUILDINGBUILT":
            needed = a.get("multiBuildingsNeeded", 0)
            if needed:
                entry["multiBuildingsNeeded"] = needed
            raw_bldgs = [
                x.get("buildingIdentifier", "")
                for x in a.get("multiBuildings", [])
                if x.get("buildingIdentifier")
            ]
            if raw_bldgs:
                filtered_ids, names = [], []
                for bid in raw_bldgs:
                    bname = gd.building_name(bid)
                    # Skip buildings with no resolvable display name (raw internal IDs)
                    if bname and not bname.startswith("_"):
                        filtered_ids.append(bid)
                        names.append(bname)
                if filtered_ids:
                    entry["multiBuildings"] = filtered_ids
                    entry["multiBuildingNames"] = names

        elif atype == "MULTI_RESEARCH":
            resolved = []
            for r in a.get("multiResearch", []):
                rid = r.get("researchIdentifier", "")
                completions = r.get("researchCompletionsNeeded", 0)
                if rid:
                    res = gd.research.get(rid)
                    rname = res.name if res else rid
                    resolved.append({"id": rid, "name": rname, "needed": completions})
            if resolved:
                entry["multiResearch"] = resolved

        elif atype == "LIFETIME_EARNINGS":
            needed = a.get("lifetimeEarningsNeeded", 0)
            if needed:
                entry["lifetimeEarningsNeeded"] = needed

        elif atype == "MARKET_DOMINANCE":
            needed = a.get("planetsWithMarketDominanceNeeded", 0)
            if needed:
                entry["planetsWithMarketDominanceNeeded"] = needed

        elif atype == "SPACE_STATION":
            upgrade_id = a.get("spaceStationUpgradeIdentifier", "")
            if upgrade_id:
                entry["spaceStationUpgradeIdentifier"] = upgrade_id
                upgrade = gd.sky_platform_upgrades.get(upgrade_id)
                if upgrade and upgrade.name:
                    entry["spaceStationUpgradeName"] = upgrade.name

        elif atype == "QUESTS":
            raw_quests = [
                q.get("questIdentifier", "")
                for q in a.get("quests", [])
                if q.get("questIdentifier")
            ]
            if raw_quests:
                names = []
                for qid in raw_quests:
                    quest = gd.quests.get(qid)
                    names.append(quest.title if quest else qid)
                entry["quests"] = raw_quests
                entry["questNames"] = names

        lines.append(f"  [{lua_string(internal_id)}] = {{")
        for key, val in entry.items():
            lk = (
                key
                if key.isidentifier() and not _is_lua_keyword(key)
                else f"[{lua_string(key)}]"
            )
            lines.append(f"    {lk} = {lua_value(val, 2)},")
        lines.append("  },")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _generate_name_index(gd: GameData) -> str:
    """Generate Module:Data/NameIndex: display_name -> {type, id} for lookups by page title."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "-- Module:Data/NameIndex",
        f"-- Auto-generated by foundry_parser on {timestamp}",
        "-- Maps display names to entity type and identifier",
        "-- Used by rendering modules to resolve page names to data keys",
        "-- DO NOT EDIT - regenerate from game data instead",
        "",
        "return {",
    ]

    entries: dict[str, tuple[str, str]] = {}

    # Items
    for ident, item in gd.items.items():
        if item.name:
            entries[item.name] = ("item", ident)

    # Buildings (prefer name_override, else from placing item)
    for ident, building in gd.buildings.items():
        name = None
        if building.name_override:
            name = building.name_override
        else:
            item_id = gd._building_to_item_index.get(ident)
            if item_id and item_id in gd.items:
                name = gd.items[item_id].name
        if name and name not in entries:
            entries[name] = ("building", ident)

    # Elements
    for ident, elem in gd.elements.items():
        if elem.name and elem.name not in entries:
            entries[elem.name] = ("element", ident)

    # Research
    for ident, res in gd.research.items():
        if res.name and res.name not in entries:
            entries[res.name] = ("research", ident)

    for name in sorted(entries.keys()):
        etype, eid = entries[name]
        lines.append(f"  [{lua_string(name)}] = {{ type = {lua_string(etype)}, id = {lua_string(eid)} }},")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


# ======================================================================
# Main export function
# ======================================================================

_MODULE_DEFS = [
    ("Items",               "items",                _export_item),
    ("Buildings",           "buildings",             None),  # handled specially
    ("Recipes",             "recipes",               _export_recipe),
    ("Research",            "research",              _export_research),
    ("ItemCategories",      "item_categories",       _export_generic),
    ("RecipeCategories",    "recipe_categories",     _export_generic),
    ("RecipeRowGroups",     "recipe_row_groups",     _export_generic),
    ("CraftingTags",        "crafting_tags",         _export_generic),
    ("Elements",            "elements",              _export_generic),
    ("TerrainBlocks",       "terrain_blocks",        _export_generic),
    ("ExplorationUnlocks",  "exploration_unlocks",   _export_generic),
    ("SkyPlatformUpgrades", "sky_platform_upgrades", _export_generic),
    ("Quests",              "quests",                _export_generic),
    ("BlastFurnaceModes",   "blast_furnace_modes",   _export_generic),
    ("Industries",          "industries",            _export_generic),
    ("CompanyRanks",        "company_ranks",         _export_generic),
    ("OreVeins",            "ore_veins",             _export_generic),
    ("ConversionGroups",    "conversion_groups",     _export_generic),
    ("InfoDatabase",        "info_database",         _export_generic),
]


def export_all_lua(gd: GameData, output_dir: Path) -> dict[str, int]:
    """
    Export all game data as Lua module source files.

    Args:
        gd: Loaded GameData instance.
        output_dir: Directory to write .lua files into.

    Returns:
        Dict of module_name -> entity_count for each written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, int] = {}

    # Entity data modules
    for module_suffix, attr_name, export_fn in _MODULE_DEFS:
        entities = getattr(gd, attr_name)
        if not entities:
            continue
        module_name = f"Module:Data/{module_suffix}"
        # Buildings need gd for name resolution
        if module_suffix == "Buildings":
            bld_export = lambda b: _export_building(b, gd)
            source = _generate_module(module_name, entities, bld_export)
        else:
            source = _generate_module(module_name, entities, export_fn)
        filepath = output_dir / f"{module_suffix}.lua"
        filepath.write_text(source, encoding="utf-8")
        results[module_name] = len(entities)

    # Extra generated modules (index tables, upgrade paths, etc.)
    _EXTRA_GENERATORS: list[tuple[str, Any]] = [
        ("RecipeIndex",          _generate_recipe_index),
        ("BuildingRecipeIndex",  _generate_building_recipe_index),
        ("ResearchIndex",        _generate_research_index),
        ("ItemBuildingIndex",    _generate_item_building_index),
        ("RecipeBuildingNames",  _generate_recipe_building_names),
        ("RecipeCraftingData",   _generate_recipe_crafting_data),
        ("UpgradePaths",         _generate_upgrade_paths),
        ("NameIndex",            _generate_name_index),
        ("Achievements",         _generate_achievements_data),
    ]

    for module_suffix, gen_fn in _EXTRA_GENERATORS:
        module_name = f"Module:Data/{module_suffix}"
        source = gen_fn(gd)
        filepath = output_dir / f"{module_suffix}.lua"
        filepath.write_text(source, encoding="utf-8")
        # Count entries from the generated source
        count = source.count("\n  [")
        results[module_name] = count

    return results
