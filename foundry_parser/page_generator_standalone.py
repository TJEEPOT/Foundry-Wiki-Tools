"""
Wiki Page Generator

Generates complete MediaWiki page wikitext for all entities in the game data.
Pages include contextual lead paragraphs, infoboxes, recipe tables, and navigation.

Usage:
    from foundry_parser.page_generator import generate_all_pages
    from foundry_parser.game_data import GameData

    gd = GameData.from_game_dir(Path("..."))
    generate_all_pages(gd, Path("wiki_pages/"))
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# imports handled externally


# ======================================================================
# Helpers
# ======================================================================

def _safe_filename(title: str) -> str:
    """Convert a page title to a safe filename."""
    name = title.replace("/", "_").replace("\\", "_")
    import re
    name = re.sub(r'[<>"|?*:]', "_", name)
    if len(name) > 200:
        name = name[:200]
    return name


def _format_power(kw: float) -> str:
    """Format kilowatts for display."""
    if kw >= 1000:
        mw = kw / 1000
        if mw == int(mw):
            return f"{int(mw)} MW"
        return f"{mw:.1f} MW"
    return f"{int(kw)} kW"


def _item_link(name: str) -> str:
    """Generate an {{ItemLink|name}} template call."""
    return "{{ItemLink|" + name + "}}"


def _plural(count: int, word: str) -> str:
    """Simple English pluralisation."""
    if count == 1:
        return f"{count} {word}"
    return f"{count} {word}s"


# ======================================================================
# Lead paragraph generators (contextual, not generic)
# ======================================================================

def _item_lead(item, gd) -> str:
    """Generate a contextual lead paragraph for an item page."""
    parts = []
    name = item.name

    producing = gd.recipes_producing(item.identifier)
    consuming = gd.recipes_consuming(item.identifier)

    building = gd.building_for_item(item.identifier)

    if building:
        bname = gd.building_name(building.identifier)
        parts.append(f"'''{name}''' is a placeable item that constructs the [[{bname}]].")
        recipes_for = gd.recipes_for_building(building.identifier)
        if recipes_for:
            parts.append(f"The {bname} can process {_plural(len(recipes_for), 'recipe')}.")
    elif producing:
        primary_recipe = producing[0]
        crafters = _crafters_for_recipe(primary_recipe, gd)
        if crafters:
            crafter_names = [gd.building_name(c.identifier) for c in crafters[:3]]
            crafter_str = ", ".join(f"[[{cn}]]" for cn in crafter_names)
            if len(producing) == 1:
                inputs = primary_recipe.inputs
                if inputs:
                    input_names = [gd.item_name(i.identifier) for i in inputs]
                    input_links = " and ".join(f"[[{n}]]" for n in input_names[:3])
                    parts.append(f"'''{name}''' is crafted from {input_links} in the {crafter_str}.")
                else:
                    parts.append(f"'''{name}''' is produced in the {crafter_str}.")
            else:
                parts.append(f"'''{name}''' can be produced by {_plural(len(producing), 'recipe')}, crafted in buildings such as {crafter_str}.")
        else:
            parts.append(f"'''{name}''' is a craftable item.")
    elif item.can_be_traded:
        parts.append(f"'''{name}''' is a tradeable commodity.")
    else:
        if "AL_STARTER" in (item.flags or []):
            parts.append(f"'''{name}''' is a starting item available from the beginning of the game.")
        else:
            parts.append(f"'''{name}''' is a resource used in crafting.")

    if consuming:
        if len(consuming) <= 3:
            output_names = set()
            for r in consuming:
                for o in r.outputs:
                    output_names.add(gd.item_name(o.identifier))
            if output_names:
                out_links = ", ".join(f"[[{n}]]" for n in sorted(output_names)[:5])
                parts.append(f"It is used to craft {out_links}.")
        else:
            parts.append(f"It is a component in {_plural(len(consuming), 'recipe')}.")

    if producing:
        unlocks = gd.research_unlocking(producing[0].identifier)
        if unlocks:
            res_name = unlocks[0].name
            parts.append(f"Unlocked by the [[{res_name}]] research.")

    if item.can_be_traded and item.sales_industry:
        industry = item.sales_industry
        parts.append(f"It can be sold in the {industry} industry.")

    return " ".join(parts)


def _building_lead(building, gd) -> str:
    """Generate a contextual lead paragraph for a building page."""
    parts = []
    name = gd.building_name(building.identifier)

    recipes = gd.recipes_for_building(building.identifier)
    power_type = building.power_type
    power_sub = building.power_subtype

    if power_sub == "POWER_SOURCE":
        parts.append(f"The '''{name}''' is a power generation building")
        if power_type == "NONE":
            parts.append("on the high-voltage grid.")
        else:
            parts.append("on the low-voltage (PCM) grid.")
    elif recipes:
        parts.append(f"The '''{name}''' is a production building")
        tag_str = ", ".join(building.producer_recipe_tags) if building.producer_recipe_tags else ""
        if tag_str:
            parts.append(f"specialising in {tag_str} recipes.")
        else:
            parts.append(f"that can process {_plural(len(recipes), 'recipe')}.")
    elif building.type == "ConveyorBelt" or (building.conveyor_speed and building.conveyor_speed > 0):
        parts.append(f"The '''{name}''' is a logistics building for transporting items.")
    elif building.is_modular:
        parts.append(f"The '''{name}''' is a modular building component ({building.modular_type or 'module'}).")
    else:
        parts.append(f"The '''{name}''' is a building in Foundry.")

    if power_sub == "POWER_CONSUMER" and building.energy_consumption_kw:
        power_str = _format_power(building.energy_consumption_kw)
        grid = "low-voltage (PCM)" if power_type == "PCM" else "high-voltage"
        parts.append(f"It consumes {power_str} from the {grid} grid.")

    if building.producer_time_modifier and building.producer_time_modifier > 1:
        mod = building.producer_time_modifier
        mod_str = str(int(mod)) if mod == int(mod) else f"{mod:.1f}"
        parts.append(f"It operates at {mod_str}x speed compared to the base recipe time.")

    if recipes and len(recipes) > 3:
        parts.append(f"It can craft {_plural(len(recipes), 'recipe')} in total.")

    if building.size:
        sx = building.size.get("x", 0)
        sy = building.size.get("y", 0)
        sz = building.size.get("z", 0)
        parts.append(f"It occupies a {sx}x{sz}x{sy} footprint.")

    item = gd.item_for_building(building.identifier)
    if item:
        consuming = gd.recipes_consuming(item.identifier)
        if consuming:
            if len(consuming) <= 3:
                output_names = set()
                for r in consuming:
                    for o in r.outputs:
                        output_names.add(gd.item_name(o.identifier))
                if output_names:
                    out_links = ", ".join(f"[[{n}]]" for n in sorted(output_names)[:5])
                    parts.append(f"It is also used as a component to craft {out_links}.")
            else:
                parts.append(f"It is also used as a crafting ingredient in {_plural(len(consuming), 'recipe')}.")

    return " ".join(parts)


def _research_lead(research, gd) -> str:
    """Generate a contextual lead paragraph for a research page."""
    parts = []
    name = research.name

    if research.description:
        parts.append(f"'''{name}''' is a research technology. {research.description}")
    else:
        parts.append(f"'''{name}''' is a research technology.")

    if research.crafting_unlocks:
        unlocked_names = []
        for recipe_id in research.crafting_unlocks:
            recipe = gd.recipes.get(recipe_id)
            if recipe:
                if recipe.outputs:
                    out_name = gd.item_name(recipe.outputs[0].identifier)
                    unlocked_names.append(out_name)
                else:
                    unlocked_names.append(recipe.name)
        if unlocked_names:
            if len(unlocked_names) <= 4:
                links = ", ".join(f"[[{n}]]" for n in unlocked_names)
                parts.append(f"It unlocks the production of {links}.")
            else:
                links = ", ".join(f"[[{n}]]" for n in unlocked_names[:3])
                parts.append(f"It unlocks {_plural(len(unlocked_names), 'recipe')}, including {links}.")

    if research.dependencies:
        dep_names = []
        for dep_id in research.dependencies:
            dep = gd.research.get(dep_id)
            if dep:
                dep_names.append(dep.name)
        if dep_names:
            dep_links = " and ".join(f"[[{n}]]" for n in dep_names)
            parts.append(f"It requires {dep_links} to be completed first.")

    if research.costs:
        cost_parts = []
        for cost in research.costs:
            item_name = gd.item_name(cost.identifier)
            cost_parts.append(f"{cost.amount}x [[{item_name}]]")
        parts.append(f"It costs {', '.join(cost_parts)} to research.")

    return " ".join(parts)


def _element_lead(element, gd) -> str:
    """Generate a contextual lead paragraph for an element page."""
    parts = []
    name = element.name

    state = "fluid"
    if element.pipe_content_type == 1:
        state = "gas"
    elif element.pipe_content_type == 2:
        state = "liquid"

    is_fuel = "FUEL" in (element.flags or [])

    if is_fuel:
        parts.append(f"'''{name}''' is a {state} fuel")
        if element.fuel_value_kj_per_l:
            parts.append(f"with an energy density of {element.fuel_value_kj_per_l} kJ/L.")
        else:
            parts.append("used for power generation.")
    else:
        parts.append(f"'''{name}''' is a {state} transported through pipes.")

    produced_by = []
    consumed_by = []
    for recipe_id, recipe in gd.recipes.items():
        for eo in recipe.elemental_outputs:
            if eo.identifier == element.identifier:
                produced_by.append(recipe)
                break
        for ei in recipe.elemental_inputs:
            if ei.identifier == element.identifier:
                consumed_by.append(recipe)
                break

    if produced_by:
        producer_names = [r.name for r in produced_by[:3]]
        parts.append(f"It is produced by the {', '.join(producer_names)} {'recipe' if len(produced_by) == 1 else 'recipes'}.")
    if consumed_by:
        parts.append(f"It is consumed in {_plural(len(consumed_by), 'recipe')}.")

    return " ".join(parts)


# ======================================================================
# Helper: find crafters for a recipe
# ======================================================================

def _crafters_for_recipe(recipe, gd):
    """Find buildings that can craft a given recipe (via tag matching)."""
    crafters = []
    for building_id in gd._building_recipes_index:
        if recipe.identifier in gd._building_recipes_index[building_id]:
            building = gd.buildings.get(building_id)
            if building:
                crafters.append(building)
    return crafters


# ======================================================================
# Full page generators
# ======================================================================

def _generate_item_page(item, gd) -> str:
    """Generate complete wikitext for an item page."""
    lines = []
    name = item.name

    lines.append(f"{{{{Infobox Item|id={item.identifier}}}}}")
    lines.append("")

    lead = _item_lead(item, gd)
    lines.append(lead)
    lines.append("")

    producing = gd.recipes_producing(item.identifier)
    if producing:
        lines.append("== Obtaining ==")
        lines.append("")
        lines.append(f"{{{{RecipeTable|id={item.identifier}|mode=producing}}}}")
        lines.append("")

    consuming = gd.recipes_consuming(item.identifier)
    if consuming:
        lines.append("== Usage ==")
        lines.append("")
        lines.append(f"{{{{RecipeTable|id={item.identifier}|mode=consuming}}}}")
        lines.append("")

    research_nodes = {}
    for recipe in producing:
        for res in gd.research_unlocking(recipe.identifier):
            research_nodes[res.identifier] = res
    if research_nodes:
        lines.append("== Research ==")
        lines.append("")
        for res in sorted(research_nodes.values(), key=lambda r: r.name):
            lines.append(f"{{{{Research Card|id={res.identifier}}}}}")
            lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.append("{{Navbox Items}}")
    lines.append("")

    if item.category_id:
        cat = gd.item_categories.get(item.category_id)
        if cat:
            lines.append(f"[[Category:{cat.name}]]")

    return "\n".join(lines)


def _generate_building_page(building, gd) -> str:
    """Generate complete wikitext for a building page."""
    lines = []
    name = gd.building_name(building.identifier)

    lines.append(f"{{{{Infobox Building|id={building.identifier}}}}}")
    lines.append("")

    lead = _building_lead(building, gd)
    lines.append(lead)
    lines.append("")

    recipes = gd.recipes_for_building(building.identifier)
    if recipes:
        lines.append("== Recipes ==")
        lines.append("")
        lines.append(f"{{{{RecipeTable Building|id={building.identifier}}}}}")
        lines.append("")

    item = gd.item_for_building(building.identifier)
    if item:
        producing = gd.recipes_producing(item.identifier)
        if producing:
            lines.append("== Construction ==")
            lines.append("")
            lines.append(f"{{{{RecipeTable|id={item.identifier}|mode=producing}}}}")
            lines.append("")

    if item:
        consuming = gd.recipes_consuming(item.identifier)
        if consuming:
            lines.append("== Usage ==")
            lines.append("")
            lines.append(f"{{{{RecipeTable|id={item.identifier}|mode=consuming}}}}")
            lines.append("")

    if building.conversion_group:
        conv_group = gd.conversion_groups.get(building.conversion_group)
        if conv_group and len(conv_group.entries) > 1:
            lines.append("== Upgrades ==")
            lines.append("")
            lines.append("This building is part of an upgrade chain. It can be converted in-place to the following tiers:")
            lines.append("")
            for entry_id in conv_group.entries:
                entry_building = gd.buildings.get(entry_id)
                if entry_building:
                    entry_name = gd.building_name(entry_id)
                    if entry_name and entry_id != building.identifier:
                        lines.append(f"* [[{entry_name}]]")
            lines.append("")

    research_nodes = {}
    if item:
        for recipe in gd.recipes_producing(item.identifier):
            for res in gd.research_unlocking(recipe.identifier):
                research_nodes[res.identifier] = res
    if research_nodes:
        lines.append("== Research ==")
        lines.append("")
        for res in sorted(research_nodes.values(), key=lambda r: r.name):
            lines.append(f"{{{{Research Card|id={res.identifier}}}}}")
            lines.append("")

    lines.append("== Tips ==")
    lines.append("")
    lines.append("<!-- Tips and strategies can be added here by editors. -->")
    lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.append("{{Navbox Buildings}}")
    lines.append("")

    return "\n".join(lines)


def _generate_research_page(research, gd) -> str:
    """Generate complete wikitext for a research page."""
    lines = []
    name = research.name

    lines.append(f"{{{{Infobox Research|id={research.identifier}}}}}")
    lines.append("")

    lead = _research_lead(research, gd)
    lines.append(lead)
    lines.append("")

    if research.dependencies:
        lines.append("== Prerequisites ==")
        lines.append("")
        for dep_id in research.dependencies:
            dep = gd.research.get(dep_id)
            if dep:
                lines.append(f"* [[{dep.name}]]")
        lines.append("")

    if research.crafting_unlocks:
        lines.append("== Unlocks ==")
        lines.append("")
        for recipe_id in research.crafting_unlocks:
            recipe = gd.recipes.get(recipe_id)
            if recipe:
                lines.append(f"{{{{Recipe|id={recipe_id}}}}}")
                lines.append("")

    dependants = []
    for rid, res in gd.research.items():
        if research.identifier in res.dependencies:
            dependants.append(res)
    if dependants:
        lines.append("== Leads To ==")
        lines.append("")
        for dep in sorted(dependants, key=lambda r: r.name):
            lines.append(f"* [[{dep.name}]]")
        lines.append("")

    tree_layers = gd.research_dependencies_tree(research.identifier)
    if tree_layers and len(tree_layers) > 1:
        lines.append("== Tech Tree ==")
        lines.append("")
        breadcrumb_ids = []
        for layer in reversed(tree_layers):
            if layer:
                breadcrumb_ids.append(layer[0])
        breadcrumb_names = []
        for rid in breadcrumb_ids:
            res = gd.research.get(rid)
            if res:
                breadcrumb_names.append(f"[[{res.name}]]")
        breadcrumb_names.append(f"'''[[{name}]]'''")
        lines.append(" -> ".join(breadcrumb_names))
        lines.append("")
        lines.append("<!-- Interactive tech tree embedding placeholder -->")
        lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.append("{{Navbox Research}}")
    lines.append("")

    return "\n".join(lines)


def _generate_element_page(element, gd) -> str:
    """Generate complete wikitext for an element page."""
    lines = []
    name = element.name

    lines.append(f"{{{{Infobox Element|id={element.identifier}}}}}")
    lines.append("")

    lead = _element_lead(element, gd)
    lines.append(lead)
    lines.append("")

    produced_by = []
    used_in = []
    for recipe_id, recipe in gd.recipes.items():
        for eo in recipe.elemental_outputs:
            if eo.identifier == element.identifier:
                produced_by.append(recipe)
                break
        for ei in recipe.elemental_inputs:
            if ei.identifier == element.identifier:
                used_in.append(recipe)
                break

    if produced_by:
        lines.append("== Produced By ==")
        lines.append("")
        for recipe in produced_by:
            lines.append(f"{{{{Recipe|id={recipe.identifier}}}}}")
            lines.append("")

    if used_in:
        lines.append("== Used In ==")
        lines.append("")
        for recipe in used_in:
            lines.append(f"{{{{Recipe|id={recipe.identifier}}}}}")
            lines.append("")

    lines.append("== Transport ==")
    lines.append("")
    state = "fluid"
    if element.pipe_content_type == 1:
        state = "gas"
    elif element.pipe_content_type == 2:
        state = "liquid"
    lines.append(f"{name} is a {state} and is transported through the pipe network. Use [[Pipe]]s to connect buildings that produce or consume this element, and [[Pump]]s to maintain flow pressure over long distances.")
    lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.append("{{Navbox Elements}}")
    lines.append("")

    return "\n".join(lines)


# ======================================================================
# Filtering: which entities get pages?
# ======================================================================

_BUILDING_SKIP_TYPES = frozenset([
    "TerrainBlock",
    "NaturalResource",
    "WorldDecorMineAble",
])

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


def _is_world_object(item) -> bool:
    if item.name in _WORLD_OBJECT_NAMES:
        return True
    if item.name in _MERGED_PAGE_ITEMS:
        return True
    id_lower = item.identifier.lower()
    for pattern in _WORLD_OBJECT_ID_PATTERNS:
        if pattern in id_lower:
            return True
    return False


def _should_have_page_item(item, gd) -> bool:
    if not item.name:
        return False
    if item.name.startswith("_"):
        return False
    if _is_world_object(item):
        return False
    building = gd.building_for_item(item.identifier)
    if building:
        bname = gd.building_name(building.identifier)
        if bname and not bname.startswith("_") and building.type not in _BUILDING_SKIP_TYPES:
            return False
    producing = gd.recipes_producing(item.identifier)
    consuming = gd.recipes_consuming(item.identifier)
    if not producing and not consuming and not item.can_be_traded:
        if not item.flags or all(f in ("", "NONE") for f in item.flags):
            return False
    return True


def _should_have_page_building(building, gd) -> bool:
    name = gd.building_name(building.identifier)
    if not name or name.startswith("_"):
        return False
    if building.type in _BUILDING_SKIP_TYPES:
        return False
    if "forest" in building.identifier or "decor" in building.identifier:
        item = gd.item_for_building(building.identifier)
        if not item:
            return False
    return True


def _should_have_page_research(research) -> bool:
    return bool(research.name and not research.name.startswith("_"))


def _should_have_page_element(element) -> bool:
    return bool(element.name and not element.name.startswith("_"))


# ======================================================================
# Exploration Unlock pages
# ======================================================================

def _generate_exploration_unlock_page(unlock, gd) -> str:
    lines = []
    name = unlock.title

    lines.append(f"{{{{Infobox Exploration Unlock|id={unlock.identifier}}}}}")
    lines.append("")

    lines.append(f"'''{name}''' is an exploration unlock in [[Foundry]]. It is discovered through exploration and grants the player new abilities or upgrades.")
    lines.append("")

    if unlock.description:
        lines.append("== Description ==")
        lines.append("")
        lines.append(unlock.description)
        lines.append("")

    if unlock.requirements:
        lines.append("== Requirements ==")
        lines.append("")
        for req in unlock.requirements:
            if isinstance(req, dict):
                item_id = req.get("itemTemplateIdentifier", req.get("identifier", ""))
                amount = req.get("amount", 1)
                item_name = gd.item_name(item_id) if item_id else "Unknown"
                lines.append(f"* {amount}x [[{item_name}]]")
            else:
                lines.append(f"* {req}")
        lines.append("")

    if unlock.unlock_dependencies:
        lines.append("== Prerequisites ==")
        lines.append("")
        for _dep_entry in unlock.unlock_dependencies:
            dep_id = _dep_entry.get('explorationUnlockTemplateIdentifier', '') if isinstance(_dep_entry, dict) else _dep_entry
            dep = gd.exploration_unlocks.get(dep_id)
            if dep:
                lines.append(f"* [[{dep.title}]]")
            elif dep_id:
                lines.append(f"* {dep_id}")
        lines.append("")

    if unlock.crafting_recipe_unlocks:
        lines.append("== Unlocks ==")
        lines.append("")
        for recipe_id in unlock.crafting_recipe_unlocks:
            recipe = gd.recipes.get(recipe_id)
            if recipe:
                lines.append(f"{{{{Recipe|id={recipe_id}}}}}")
                lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.append("[[Category:Exploration Unlocks]]")

    return "\n".join(lines)


# ======================================================================
# Space Station (Sky Platform) Upgrade pages
# ======================================================================

def _generate_sky_platform_page(upgrade, gd) -> str:
    lines = []
    name = upgrade.name

    lines.append(f"{{{{Infobox Sky Platform Upgrade|id={upgrade.identifier}}}}}")
    lines.append("")

    lines.append(f"'''{name}''' is a [[Space Station]] upgrade in [[Foundry]].")
    lines.append("")

    if upgrade.description:
        lines.append("== Description ==")
        lines.append("")
        lines.append(upgrade.description)
        lines.append("")

    if upgrade.costs:
        lines.append("== Costs ==")
        lines.append("")
        for cost in upgrade.costs:
            if isinstance(cost, dict):
                item_id = cost.get("itemTemplateIdentifier", cost.get("identifier", ""))
                amount = cost.get("amount", 1)
                item_name = gd.item_name(item_id) if item_id else "Unknown"
                lines.append(f"* {amount}x [[{item_name}]]")
            else:
                lines.append(f"* {cost}")
        lines.append("")

    if upgrade.requirements:
        lines.append("== Prerequisites ==")
        lines.append("")
        for req_id in upgrade.requirements:
            req = gd.sky_platform_upgrades.get(req_id)
            if req:
                lines.append(f"* [[{req.name}]]")
            else:
                lines.append(f"* {req_id}")
        lines.append("")

    effects = []
    if upgrade.power_increase_mw:
        effects.append(f"Increases power capacity by {upgrade.power_increase_mw} MW")
    if upgrade.construction_drone_increase:
        effects.append(f"Adds {upgrade.construction_drone_increase} construction drone(s)")
    if upgrade.sector_unlocks:
        effects.append(f"Unlocks {upgrade.sector_unlocks} new sector(s)")
    if upgrade.trade_license_unlocks:
        effects.append(f"Unlocks {upgrade.trade_license_unlocks} trade license(s)")
    if upgrade.hangar_space_increase:
        effects.append(f"Increases hangar space by {upgrade.hangar_space_increase}")
    if effects:
        lines.append("== Effects ==")
        lines.append("")
        for effect in effects:
            lines.append(f"* {effect}")
        lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.append("[[Category:Space Station Upgrades]]")

    return "\n".join(lines)


# ======================================================================
# Merged page generators
# ======================================================================

_SEED_BIOMES = [
    ("Boreal Forest", "_base_boreal_forest_seed_plants", "_base_boreal_forest_seed_trees"),
    ("Rocky Desert", "_base_rocky_desert_seed_plants", "_base_rocky_desert_seed_trees"),
    ("Sandy Desert", "_base_sandy_desert_seed_plants", "_base_sandy_desert_seed_trees"),
    ("Tundra", "_base_tundra_seed_plants", "_base_tundra_seed_trees"),
    ("Tropical Rainforest", "_base_tropical_rainforest_seed_plants", "_base_tropical_rainforest_seed_trees"),
]

_CRITTER_IDS = [
    "_base_critter_forest",
    "_base_critter_jungle",
    "_base_critter_rocky_desert",
    "_base_critter_sandy_desert",
    "_base_critter_shrublands",
    "_base_critter_tundra",
]

_BIOME_DIRT_IDS = [
    "_base_tropical_rainforest_dirt",
    "_base_tundra_dirt",
    "_base_rocky_desert_dirt",
]


def _generate_seed_page(biome, plants_id, trees_id, gd) -> str:
    lines = []

    lines.append(f"{{{{Infobox Item|id={plants_id}}}}}")
    lines.append("")

    lines.append(f"'''{biome} Seed''' is a plantable item that comes in two variants: one for plants and one for trees. Seeds can be obtained by destroying existing {biome.lower()} vegetation or produced in a [[Greenhouse]] after researching the appropriate technology.")
    lines.append("")

    plants_item = gd.items.get(plants_id)
    trees_item = gd.items.get(trees_id)

    producing_plants = gd.recipes_producing(plants_id) if plants_item else []
    producing_trees = gd.recipes_producing(trees_id) if trees_item else []

    if producing_plants or producing_trees:
        lines.append("== Production ==")
        lines.append("")
        if producing_plants:
            lines.append(f"{{{{RecipeTable|id={plants_id}}}}}")
            lines.append("")
        if producing_trees and trees_id != plants_id:
            lines.append(f"{{{{RecipeTable|id={trees_id}}}}}")
            lines.append("")

    consuming_plants = gd.recipes_consuming(plants_id) if plants_item else []
    consuming_trees = gd.recipes_consuming(trees_id) if trees_item else []

    if consuming_plants or consuming_trees:
        lines.append("== Usage ==")
        lines.append("")
        lines.append("Seeds are consumed when planted, placing vegetation in the world. Plants and trees grow over time and can be harvested for [[Biomass]].")
        lines.append("")

    lines.append("{{Navbox Items}}")
    lines.append("")
    lines.append("[[Category:Resources]]")
    lines.append("[[Category:Seeds]]")

    return "\n".join(lines)


def _generate_critter_page(gd) -> str:
    lines = []

    lines.append("{{Infobox Item|id=_base_critter_forest}}")
    lines.append("")

    lines.append("'''Critters''' are small creatures found across the various biomes of Foundry. They are passive wildlife that inhabit the world and do not interact with the player's factory infrastructure.")
    lines.append("")

    lines.append("== Variants ==")
    lines.append("")
    lines.append('{| class="wikitable"')
    lines.append("! Critter !! Biome")

    critter_data = [
        ("Forest Critter", "Boreal Forest"),
        ("Jungle Critter", "Tropical Rainforest"),
        ("Rocky Desert Critter", "Rocky Desert"),
        ("Sandy Desert Critter", "Sandy Desert"),
        ("Shrublands Critter", "Shrublands"),
        ("Tundra Critter", "Tundra"),
    ]
    for critter_name, biome in critter_data:
        lines.append("|-")
        lines.append(f"| {critter_name} || {biome}")

    lines.append("|}")
    lines.append("")

    lines.append("{{Navbox Items}}")
    lines.append("")
    lines.append("[[Category:Wildlife]]")

    return "\n".join(lines)


def _generate_dirt_page(gd) -> str:
    lines = []

    lines.append("{{Infobox Item|id=_base_dirt}}")
    lines.append("")

    lines.append("'''Dirt''' is a natural resource obtained by digging terrain. It appears in several biome-specific textures (Tropical Rainforest Dirt, Tundra Dirt, Rocky Desert Dirt) but all variants produce the same Dirt item when excavated. Dirt has no crafting uses and is primarily encountered as a byproduct of terrain modification.")
    lines.append("")

    lines.append("== Variants ==")
    lines.append("")
    lines.append("Different biomes feature visually distinct dirt textures, but they are functionally identical:")
    lines.append("")
    lines.append("* Tropical Rainforest Dirt - dark, rich soil")
    lines.append("* Tundra Dirt - pale, frozen ground")
    lines.append("* Rocky Desert Dirt - dry, reddish earth")
    lines.append("")

    lines.append("{{Navbox Items}}")
    lines.append("")
    lines.append("[[Category:Resources]]")

    return "\n".join(lines)


# ======================================================================
# Main export
# ======================================================================

def generate_all_pages(gd, output_dir, verbose=True):
    """Generate wiki pages for all entities."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {
        "items": 0, "buildings": 0, "research": 0, "elements": 0,
        "exploration_unlocks": 0, "sky_platform_upgrades": 0,
    }

    def log(msg):
        if verbose:
            print(msg)

    # --- Items ---
    items_dir = output_dir / "items"
    items_dir.mkdir(exist_ok=True)
    for item_id, item in sorted(gd.items.items()):
        if not _should_have_page_item(item, gd):
            continue
        page = _generate_item_page(item, gd)
        filename = _safe_filename(item.name) + ".wikitext"
        (items_dir / filename).write_text(page, encoding="utf-8")
        counts["items"] += 1

    # --- Merged item pages (seeds, critters, dirt) ---
    for biome, plants_id, trees_id in _SEED_BIOMES:
        page = _generate_seed_page(biome, plants_id, trees_id, gd)
        filename = _safe_filename(f"{biome} Seed") + ".wikitext"
        (items_dir / filename).write_text(page, encoding="utf-8")
        counts["items"] += 1

    page = _generate_critter_page(gd)
    (items_dir / "Critter.wikitext").write_text(page, encoding="utf-8")
    counts["items"] += 1

    page = _generate_dirt_page(gd)
    (items_dir / "Dirt.wikitext").write_text(page, encoding="utf-8")

    log(f"  Items: {counts['items']} pages")

    # --- Buildings ---
    buildings_dir = output_dir / "buildings"
    buildings_dir.mkdir(exist_ok=True)
    generated_building_names = set()
    for building_id, building in sorted(gd.buildings.items()):
        if not _should_have_page_building(building, gd):
            continue
        name = gd.building_name(building.identifier)
        if name in generated_building_names:
            continue
        generated_building_names.add(name)
        page = _generate_building_page(building, gd)
        filename = _safe_filename(name) + ".wikitext"
        (buildings_dir / filename).write_text(page, encoding="utf-8")
        counts["buildings"] += 1

    log(f"  Buildings: {counts['buildings']} pages")

    # --- Research ---
    research_dir = output_dir / "research"
    research_dir.mkdir(exist_ok=True)
    for res_id, research in sorted(gd.research.items()):
        if not _should_have_page_research(research):
            continue
        page = _generate_research_page(research, gd)
        filename = _safe_filename(research.name) + ".wikitext"
        (research_dir / filename).write_text(page, encoding="utf-8")
        counts["research"] += 1

    log(f"  Research: {counts['research']} pages")

    # --- Elements ---
    elements_dir = output_dir / "elements"
    elements_dir.mkdir(exist_ok=True)
    for elem_id, element in sorted(gd.elements.items()):
        if not _should_have_page_element(element):
            continue
        page = _generate_element_page(element, gd)
        filename = _safe_filename(element.name) + ".wikitext"
        (elements_dir / filename).write_text(page, encoding="utf-8")
        counts["elements"] += 1

    log(f"  Elements: {counts['elements']} pages")

    # --- Exploration Unlocks ---
    unlocks_dir = output_dir / "exploration_unlocks"
    unlocks_dir.mkdir(exist_ok=True)
    for unlock_id, unlock in sorted(gd.exploration_unlocks.items()):
        if not unlock.title or unlock.title.startswith("_"):
            continue
        page = _generate_exploration_unlock_page(unlock, gd)
        filename = _safe_filename(unlock.title) + ".wikitext"
        (unlocks_dir / filename).write_text(page, encoding="utf-8")
        counts["exploration_unlocks"] += 1

    log(f"  Exploration Unlocks: {counts['exploration_unlocks']} pages")

    # --- Sky Platform Upgrades ---
    sky_dir = output_dir / "sky_platform_upgrades"
    sky_dir.mkdir(exist_ok=True)
    for upgrade_id, upgrade in sorted(gd.sky_platform_upgrades.items()):
        if not upgrade.name or upgrade.name.startswith("_"):
            continue
        page = _generate_sky_platform_page(upgrade, gd)
        filename = _safe_filename(upgrade.name) + ".wikitext"
        (sky_dir / filename).write_text(page, encoding="utf-8")
        counts["sky_platform_upgrades"] += 1

    log(f"  Sky Platform Upgrades: {counts['sky_platform_upgrades']} pages")

    total = sum(counts.values())
    log(f"\n  Total: {total} pages generated in {output_dir}/")

    return counts
