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

import json
from pathlib import Path
from typing import Any

from .game_data import GameData
from collections import defaultdict

from .models import (
    Building,
    CraftingRecipe,
    Element,
    ExplorationUnlock,
    Item,
    Research,
    SkyPlatformUpgrade,
)


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
# Page Title Disambiguation
# ======================================================================

# Priority order: lower number = higher priority for keeping clean name.
_TYPE_PRIORITY = {
    "Item": 0,
    "Building": 1,
    "Element": 2,
    "Research": 3,
    "Exploration Unlock": 4,
    "Sky Platform": 5,
}

# Suffix added to page titles for disambiguation (matches Factorio wiki style).
_TYPE_SUFFIX = {
    "Item": "(Item)",
    "Building": "(Building)",
    "Element": "(Element)",
    "Research": "(Research)",
    "Exploration Unlock": "(Exploration Unlock)",
    "Sky Platform": "(Sky Platform Upgrade)",
}


class PageTitleRegistry:
    """
    Pre-scans all entities and assigns unique wiki page titles.

    When multiple entity types share a display name, the highest-priority
    type gets the clean name and the rest are suffixed:
      e.g. "Stairs" (Building), "Stairs (Research)"

    Also tracks cross-references so each page can emit a "See Also" section
    linking to its sibling pages with the same base name.
    """

    def __init__(self) -> None:
        # base_name -> {type_label: page_title}
        self._titles: dict[str, dict[str, str]] = {}
        # Resolved title for each (type_label, base_name)
        self._resolved: dict[tuple[str, str], str] = {}

    def build(self, gd: GameData) -> None:
        """Scan all entities and resolve page titles."""
        # Collect base names per type (only entities that would generate pages)
        raw: dict[str, set[str]] = defaultdict(set)

        for item_id, item in gd.items.items():
            if _should_have_page_item(item, gd):
                raw[item.name].add("Item")

        seen_building_names: set[str] = set()
        for building_id, building in sorted(gd.buildings.items()):
            if not _should_have_page_building(building, gd):
                continue
            name = _sanitize_wiki_title(gd.building_name(building.identifier))
            if name in seen_building_names:
                continue
            seen_building_names.add(name)
            raw[name].add("Building")

        for res_id, research in gd.research.items():
            if _should_have_page_research(research):
                raw[research.name].add("Research")

        for elem_id, element in gd.elements.items():
            if _should_have_page_element(element):
                raw[element.name].add("Element")

        for unlock_id, unlock in gd.exploration_unlocks.items():
            if unlock.title and not unlock.title.startswith("_"):
                raw[unlock.title].add("Exploration Unlock")

        for upgrade_id, upgrade in gd.sky_platform_upgrades.items():
            if upgrade.name and not upgrade.name.startswith("_"):
                raw[upgrade.name].add("Sky Platform")

        # Resolve titles
        for base_name, types in raw.items():
            if len(types) == 1:
                # No conflict — use the clean name
                the_type = next(iter(types))
                self._resolved[(the_type, base_name)] = base_name
                self._titles[base_name] = {the_type: base_name}
            else:
                # Conflict — highest-priority type gets clean name
                sorted_types = sorted(types, key=lambda t: _TYPE_PRIORITY[t])
                winner = sorted_types[0]
                mapping: dict[str, str] = {}
                self._resolved[(winner, base_name)] = base_name
                mapping[winner] = base_name
                for loser in sorted_types[1:]:
                    suffixed = f"{base_name} ({_TYPE_SUFFIX[loser].strip('()')})"
                    self._resolved[(loser, base_name)] = suffixed
                    mapping[loser] = suffixed
                self._titles[base_name] = mapping

    def get_title(self, type_label: str, base_name: str) -> str:
        """Get the resolved page title for an entity."""
        return self._resolved.get((type_label, base_name), base_name)

    def get_see_also(self, type_label: str, base_name: str) -> list[str]:
        """Get list of sibling page titles that share the same base name."""
        mapping = self._titles.get(base_name, {})
        result = []
        for t, title in sorted(mapping.items(), key=lambda x: _TYPE_PRIORITY[x[0]]):
            if t != type_label:
                result.append(title)
        return result

    def has_conflict(self, base_name: str) -> bool:
        """Check if a base name has page title conflicts."""
        mapping = self._titles.get(base_name, {})
        return len(mapping) > 1

    def get_all_redirects(self) -> list[tuple[str, str]]:
        """Generate redirect pairs for every page at a clean (unsuffixed) title.

        For each entity whose page lives at the base name (no suffix), we
        create a redirect from "Name (Type)" -> "Name" so that links in the
        suffixed form always work, even when there's no disambiguation conflict.

        For entities that already have a suffixed title (conflict losers),
        no redirect is needed — the page itself lives at the suffixed title.

        Returns list of (redirect_title, target_title) pairs.
        """
        redirects: list[tuple[str, str]] = []
        # Also track all real page titles so we don't create a redirect that
        # would clash with an actual content page.
        real_titles: set[str] = set(self._resolved.values())

        for (type_label, base_name), page_title in self._resolved.items():
            if page_title != base_name:
                continue  # already suffixed — no redirect needed
            suffix = _TYPE_SUFFIX.get(type_label, "")
            if not suffix:
                continue
            suffixed = f"{base_name} ({suffix.strip('()')})"
            if suffixed not in real_titles:
                redirects.append((suffixed, base_name))
        return redirects


def _render_see_also(registry: PageTitleRegistry | None, type_label: str, base_name: str) -> list[str]:
    """Generate 'See Also' wikitext lines.

    If the page has disambiguation siblings, emits a live == See Also == section.
    Otherwise emits a commented-out placeholder that editors can uncomment.
    """
    siblings = registry.get_see_also(type_label, base_name) if registry else []
    if siblings:
        lines = ["== See Also ==", ""]
        for title in siblings:
            lines.append(f"* [[{title}]]")
        lines.append("")
        return lines
    # Commented-out placeholder — visible in the source editor, hidden on the page
    return ["<!-- == See Also ==", "Feel free to uncomment this and add any pages that are related to this one, but not already linked from this page", "-->", ""]


# ======================================================================
# Lead paragraph generators (contextual, not generic)
# ======================================================================

def _item_lead(item: Item, gd: GameData) -> str:
    """Generate a contextual lead paragraph for an item page."""
    parts = []
    name = item.name

    # What produces this item?
    producing = gd.recipes_producing(item.identifier)
    consuming = gd.recipes_consuming(item.identifier)

    # Determine primary context
    building = gd.building_for_item(item.identifier)

    if building:
        # This item places a building
        bname = gd.building_name(building.identifier)
        parts.append(f"'''{name}''' is a placeable item that constructs the [[{bname}]].")
        # Add what building does
        recipes_for = gd.recipes_for_building(building.identifier)
        if recipes_for:
            parts.append(
                f"The {bname} can process {_plural(len(recipes_for), 'recipe')}."
            )
    elif producing:
        # It's a craftable item — describe how it's made
        primary_recipe = producing[0]
        # Find what building makes it
        crafters = _crafters_for_recipe(primary_recipe, gd)
        if crafters:
            crafter_names = [gd.building_name(c.identifier) for c in crafters[:3]]
            crafter_str = ", ".join(f"[[{cn}]]" for cn in crafter_names)
            if len(producing) == 1:
                # Single recipe — mention inputs
                inputs = primary_recipe.inputs
                if inputs:
                    input_names = [gd.item_name(i.identifier) for i in inputs]
                    input_links = " and ".join(f"[[{n}]]" for n in input_names[:3])
                    parts.append(
                        f"'''{name}''' is crafted from {input_links} "
                        f"in the {crafter_str}."
                    )
                else:
                    parts.append(f"'''{name}''' is produced in the {crafter_str}.")
            else:
                parts.append(
                    f"'''{name}''' can be produced by "
                    f"{_plural(len(producing), 'recipe')}, "
                    f"crafted in buildings such as {crafter_str}."
                )
        else:
            parts.append(f"'''{name}''' is a craftable item.")
    elif item.can_be_traded:
        parts.append(f"'''{name}''' is a tradeable commodity.")
    else:
        # Fallback: raw resource or uncraftable
        if "AL_STARTER" in (item.flags or []):
            parts.append(f"'''{name}''' is a starting item available from the beginning of the game.")
        else:
            parts.append(f"'''{name}''' is a resource used in crafting.")

    # How is it used?
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
            parts.append(
                f"It is a component in {_plural(len(consuming), 'recipe')}."
            )

    # Research unlock
    if producing:
        unlocks = gd.research_unlocking(producing[0].identifier)
        if unlocks:
            res_name = unlocks[0].name
            parts.append(f"Unlocked by the [[{res_name}]] research.")

    # Trade info
    if item.can_be_traded and item.sales_industry:
        industry = item.sales_industry
        parts.append(f"It can be sold in the {industry} industry.")

    return " ".join(parts)


def _building_lead(building: Building, gd: GameData) -> str:
    """Generate a contextual lead paragraph for a building page."""
    parts = []
    name = gd.building_name(building.identifier)

    # What type of building?
    recipes = gd.recipes_for_building(building.identifier)
    power_type = building.power_type
    power_sub = building.power_subtype

    # Categorise
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

    # Power consumption
    if power_sub == "POWER_CONSUMER" and building.energy_consumption_kw:
        power_str = _format_power(building.energy_consumption_kw)
        grid = "low-voltage (PCM)" if power_type == "PCM" else "high-voltage"
        parts.append(f"It consumes {power_str} from the {grid} grid.")

    # Speed modifier
    if building.producer_time_modifier and building.producer_time_modifier > 1:
        mod = building.producer_time_modifier
        mod_str = str(int(mod)) if mod == int(mod) else f"{mod:.1f}"
        parts.append(
            f"It operates at {mod_str}× speed "
            f"compared to the base recipe time."
        )

    # Recipe count
    if recipes and len(recipes) > 3:
        parts.append(f"It can craft {_plural(len(recipes), 'recipe')} in total.")

    # Dimensions
    if building.size:
        sx = building.size.get("x", 0)
        sy = building.size.get("y", 0)
        sz = building.size.get("z", 0)
        parts.append(f"It occupies a {sx}×{sz}×{sy} footprint.")

    # If the building's item is used as an ingredient in other recipes
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
                parts.append(
                    f"It is also used as a crafting ingredient in "
                    f"{_plural(len(consuming), 'recipe')}."
                )

    return " ".join(parts)


def _research_lead(research: Research, gd: GameData) -> str:
    """Generate a contextual lead paragraph for a research page."""
    parts = []
    name = research.name

    # Use the description if available
    if research.description:
        parts.append(f"'''{name}''' is a research technology. {research.description}")
    else:
        parts.append(f"'''{name}''' is a research technology.")

    # What does it unlock?
    if research.crafting_unlocks:
        unlocked_names = []
        for recipe_id in research.crafting_unlocks:
            recipe = gd.recipes.get(recipe_id)
            if recipe:
                # Get the primary output name
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
                parts.append(
                    f"It unlocks {_plural(len(unlocked_names), 'recipe')}, "
                    f"including {links}."
                )

    # Prerequisites
    if research.dependencies:
        dep_names = []
        for dep_id in research.dependencies:
            dep = gd.research.get(dep_id)
            if dep:
                dep_names.append(dep.name)
        if dep_names:
            dep_links = " and ".join(f"[[{n}]]" for n in dep_names)
            parts.append(f"It requires {dep_links} to be completed first.")

    # Costs
    if research.costs:
        cost_parts = []
        for cost in research.costs:
            item_name = gd.item_name(cost.identifier)
            cost_parts.append(f"{cost.amount}× [[{item_name}]]")
        parts.append(f"It costs {', '.join(cost_parts)} to research.")

    return " ".join(parts)


def _element_lead(element: Element, gd: GameData) -> str:
    """Generate a contextual lead paragraph for an element page."""
    parts = []
    name = element.name

    # State
    state = "fluid"
    if element.pipe_content_type == 1:
        state = "gas"
    elif element.pipe_content_type == 2:
        state = "liquid"

    # Fuel?
    is_fuel = "FUEL" in (element.flags or [])

    if is_fuel:
        parts.append(f"'''{name}''' is a {state} fuel")
        if element.fuel_value_kj_per_l:
            parts.append(f"with an energy density of {element.fuel_value_kj_per_l} kJ/L.")
        else:
            parts.append("used for power generation.")
    else:
        parts.append(f"'''{name}''' is a {state} transported through pipes.")

    # Check recipes that produce/consume this element
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
        parts.append(
            f"It is produced by the {', '.join(producer_names)} "
            f"{'recipe' if len(produced_by) == 1 else 'recipes'}."
        )
    if consumed_by:
        parts.append(
            f"It is consumed in {_plural(len(consumed_by), 'recipe')}."
        )

    return " ".join(parts)


# ======================================================================
# Helper: find crafters for a recipe
# ======================================================================

def _crafters_for_recipe(recipe: CraftingRecipe, gd: GameData) -> list[Building]:
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

def _generate_item_page(item: Item, gd: GameData, *, registry: PageTitleRegistry | None = None, page_title: str = "") -> str:
    """Generate complete wikitext for an item page."""
    lines = []
    name = item.name

    # Infobox
    lines.append(f"{{{{Infobox Item|id={item.identifier}|image={name}.png}}}}")
    lines.append("")

    # Lead paragraph
    lead = _item_lead(item, gd)
    lines.append(lead)
    lines.append("")

    # Obtaining section — recipes that produce this item
    producing = gd.recipes_producing(item.identifier)
    if producing:
        lines.append("== Obtaining ==")
        lines.append("")
        lines.append(f"{{{{RecipeCard|id={item.identifier}|mode=producing}}}}")
        lines.append("")

    # Usage section — recipes that consume this item
    consuming = gd.recipes_consuming(item.identifier)
    if consuming:
        lines.append("== Usage ==")
        lines.append("")
        lines.append(f"{{{{RecipeTable|id={item.identifier}|mode=consuming}}}}")
        lines.append("")

    # Research section — which research nodes unlock recipes for this item
    research_nodes: dict[str, Any] = {}
    for recipe in producing:
        for res in gd.research_unlocking(recipe.identifier):
            research_nodes[res.identifier] = res
    if research_nodes:
        lines.append("== Research ==")
        lines.append("")
        for res in sorted(research_nodes.values(), key=lambda r: r.name):
            lines.append(f"{{{{Research Card|id={res.identifier}}}}}")
            lines.append("")

    # Tips placeholder — commented out so editors can uncomment and fill in
    lines.append("<!-- == Tips ==")
    lines.append("Feel free to uncomment this and add any tips for using this item")
    lines.append("-->")
    lines.append("")

    # History section (placeholder for patch notes)
    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    # See Also — real section if disambiguation siblings exist, placeholder otherwise
    lines.extend(_render_see_also(registry, "Item", item.name))

    # Navigation
    lines.append("{{Navbox Items}}")
    lines.append("")

    # Categories
    if item.category_id:
        cat = gd.item_categories.get(item.category_id)
        if cat:
            lines.append(f"[[Category:{cat.name}]]")

    return "\n".join(lines)


def _generate_building_page(building: Building, gd: GameData, *, registry: PageTitleRegistry | None = None, page_title: str = "") -> str:
    """Generate complete wikitext for a building page."""
    lines = []
    name = gd.building_name(building.identifier)

    # Infobox — use the page title as the image name so that modular buildings
    # whose page is titled "Blast Furnace Base" look up Item_Blast_Furnace_Base.png
    # rather than Item_Blast_Furnace.png.
    image_name = page_title if page_title else name
    lines.append(f"{{{{Infobox Building|id={building.identifier}|image={image_name}.png}}}}")
    lines.append("")

    # Lead paragraph
    lead = _building_lead(building, gd)
    lines.append(lead)
    lines.append("")

    # Construction section — how to build this building
    item = gd.item_for_building(building.identifier)
    if item:
        producing = gd.recipes_producing(item.identifier)
        if producing:
            lines.append("== Construction ==")
            lines.append("")
            lines.append(f"{{{{RecipeCard|id={item.identifier}|mode=producing}}}}")
            lines.append("")

    # Usage section — recipes that consume this building's item
    if item:
        consuming = gd.recipes_consuming(item.identifier)
        if consuming:
            lines.append("== Usage ==")
            lines.append("")
            lines.append(f"{{{{RecipeTable|id={item.identifier}|mode=consuming}}}}")
            lines.append("")

    # Research section — what research unlocks this building
    research_nodes: dict[str, Any] = {}
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

    # Tips placeholder — commented out so editors can uncomment and fill in
    lines.append("<!-- == Tips ==")
    lines.append("Feel free to uncomment this and add any tips for using this research")
    lines.append("-->")
    lines.append("")

    # History section (placeholder for patch notes)
    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    # See Also — real section if disambiguation siblings exist, placeholder otherwise
    lines.extend(_render_see_also(registry, "Building", gd.building_name(building.identifier)))

    # Navigation
    lines.append("{{Navbox Buildings}}")
    lines.append("")

    return "\n".join(lines)


def _generate_research_page(research: Research, gd: GameData, *, registry: PageTitleRegistry | None = None, page_title: str = "") -> str:
    """Generate complete wikitext for a research page."""
    lines = []
    name = research.name

    # Infobox (with image param)
    lines.append(f"{{{{Infobox Research|id={research.identifier}|image={name} (Research).png}}}}")
    lines.append("")

    # Lead paragraph
    lead = _research_lead(research, gd)
    lines.append(lead)
    lines.append("")

    # Unlocks section — recipe cards for crafting unlocks, plain text for others
    has_unlocks = False
    unlock_lines: list[str] = []

    # Crafting recipe unlocks (shown as RecipeCards)
    if research.crafting_unlocks:
        for recipe_id in research.crafting_unlocks:
            recipe = gd.recipes.get(recipe_id)
            if recipe:
                unlock_lines.append(f"{{{{RecipeCard Recipe|id={recipe_id}}}}}")
                unlock_lines.append("")

    # Non-recipe unlocks (shown as plain text items)
    other_unlocks: list[str] = []

    # Ore scanner unlocks
    if research.ore_scanner_unlocks:
        for oid in research.ore_scanner_unlocks:
            # Try to resolve a display name from items or terrain
            item = gd.items.get(oid)
            if item and item.name:
                other_unlocks.append(f"Ore Scanner: [[{item.name}]]")
            else:
                # Format the identifier nicely
                pretty = oid.replace("_base_", "").replace("oreveinmineable_", "").replace("_", " ").title()
                other_unlocks.append(f"Ore Scanner: {pretty}")

    # Assembly line robot unlocks
    if research.assembly_line_objects:
        for oid in research.assembly_line_objects:
            item = gd.items.get(oid)
            if item and item.name:
                other_unlocks.append(f"Assembly Line: [[{item.name}]]")
            else:
                pretty = oid.replace("_base_", "").replace("_", " ").title()
                other_unlocks.append(f"Assembly Line: {pretty}")

    # Inventory slot unlocks
    if research.additional_inventory_slots:
        other_unlocks.append(f"+{research.additional_inventory_slots} Inventory Slots")

    # Mining hardness unlocks
    if research.mining_hardness_level:
        other_unlocks.append(f"Mining Hardness Level {research.mining_hardness_level}")

    # Jetpack speed unlocks
    if research.jetpack_speed_increase:
        other_unlocks.append(f"Jetpack Speed +{int(research.jetpack_speed_increase)}%")

    if unlock_lines or other_unlocks:
        lines.append("== Unlocks ==")
        lines.append("")
        # Other unlocks first as bullet points
        for item_text in other_unlocks:
            lines.append(f"* {item_text}")
        if other_unlocks and unlock_lines:
            lines.append("")
        # Then recipe cards
        lines.extend(unlock_lines)
        # Ensure trailing blank line if section only had bullet points
        if other_unlocks and not unlock_lines:
            lines.append("")

    # Leads To section — what depends on this research?
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

    # Tech Tree section — one breadcrumb per direct prerequisite chain
    if research.dependencies:
        lines.append("== Tech Tree ==")
        lines.append("")
        for dep_id in research.dependencies:
            dep_res = gd.research.get(dep_id)
            if not dep_res:
                continue
            # Walk the ancestor chain for this single prerequisite
            dep_tree = gd.research_dependencies_tree(dep_id)
            ancestor_ids: list[str] = []
            for layer in reversed(dep_tree):
                if layer:
                    ancestor_ids.append(layer[0])
            ancestor_ids.append(dep_id)
            # Render as a breadcrumb with proper page titles
            crumb_parts = []
            for rid in ancestor_ids:
                res = gd.research.get(rid)
                if res:
                    page_title = registry.get_title("Research", res.name) if registry else res.name
                    if page_title != res.name:
                        crumb_parts.append(f"[[{page_title}|{res.name}]]")
                    else:
                        crumb_parts.append(f"[[{res.name}]]")
            crumb_parts.append(f"'''{name}'''")
            lines.append(" → ".join(crumb_parts))
            lines.append("")
        lines.append("<!-- Interactive tech tree embedding placeholder -->")
        lines.append("")

    # Tips placeholder — commented out so editors can uncomment and fill in
    lines.append("<!-- == Tips ==")
    lines.append("Feel free to uncomment this and add any tips for this research")
    lines.append("-->")
    lines.append("")

    # History section
    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    # See Also — real section if disambiguation siblings exist, placeholder otherwise
    lines.extend(_render_see_also(registry, "Research", research.name))

    # Navigation
    lines.append("{{Navbox Research}}")
    lines.append("")

    return "\n".join(lines)


def _generate_element_page(element: Element, gd: GameData, *, registry: PageTitleRegistry | None = None, page_title: str = "") -> str:
    """Generate complete wikitext for an element page."""
    lines = []
    name = element.name

    # Infobox
    lines.append(f"{{{{Infobox Element|id={element.identifier}|image={name} (Element).png}}}}")
    lines.append("")

    # Lead paragraph
    lead = _element_lead(element, gd)
    lines.append(lead)
    lines.append("")

    # Produced By section — single RecipeTable call (element is indexed in RecipeIndex)
    produced_by_ids = [
        recipe_id for recipe_id, recipe in gd.recipes.items()
        if any(eo.identifier == element.identifier for eo in recipe.elemental_outputs)
    ]
    if produced_by_ids:
        lines.append("== Produced By ==")
        lines.append("")
        lines.append(f"{{{{RecipeTable|id={element.identifier}|mode=producing}}}}")
        lines.append("")

    # Used In section — single RecipeTable call
    used_in_ids = [
        recipe_id for recipe_id, recipe in gd.recipes.items()
        if any(ei.identifier == element.identifier for ei in recipe.elemental_inputs)
    ]
    if used_in_ids:
        lines.append("== Used In ==")
        lines.append("")
        lines.append(f"{{{{RecipeTable|id={element.identifier}|mode=consuming}}}}")
        lines.append("")

    # Tips placeholder — commented out so editors can uncomment and fill in
    lines.append("<!-- == Tips ==")
    lines.append("Feel free to uncomment this and add any tips for using this element")
    lines.append("-->")
    lines.append("")

    # History section
    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    # See Also — real section if disambiguation siblings exist, placeholder otherwise
    lines.extend(_render_see_also(registry, "Element", element.name))

    # Navigation
    lines.append("{{Navbox Elements}}")
    lines.append("")

    return "\n".join(lines)


# ======================================================================
# Filtering: which entities get pages?
# ======================================================================

_BUILDING_SKIP_TYPES = frozenset([
    "TerrainBlock",  # terrain blocks get their own category
    "NaturalResource",
    "WorldDecorMineAble",  # mineable world objects (ore nodes, crystals)
    "ResourceNode",  # world-spawned resource nodes (Geothermal Vent, Resource Node: Alien Scrap, etc.)
])

# World decoration items that don't merit their own wiki pages.
# These are plants, trees, rocks, cave formations, sea life, and other
# world objects that players can harvest for biomass but aren't meaningful
# wiki topics on their own.
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
    "_gl_birch_", "_gl_fansy_plant",  # generic trees/plants
)

# Items whose names indicate they're world objects, not wiki-page-worthy
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
])

# Items handled by merged pages (seeds, critters, biome dirt)
_MERGED_PAGE_ITEMS = frozenset([
    # Critters — merged into single "Critter" page
    "Forest Critter", "Jungle Critter", "Rocky Desert Critter",
    "Sandy DesertCritter", "Shrublands Critter", "Tundra Critter",
    # Biome dirt — merged into "Dirt" page
    "Tropical Rainforest Dirt", "Tundra Dirt", "Rocky Desert Dirt",
    "Dirt",  # replaced by custom merged page
    # Commands and Emotes — merged into special pages (their toggleableModes
    # are the real entries; the item itself is just a hidden container)
    "Commands", "Emotes",
])


def _is_world_object(item: Item) -> bool:
    """Check if an item is a world decoration object (not page-worthy)."""
    if item.name in _WORLD_OBJECT_NAMES:
        return True
    if item.name in _MERGED_PAGE_ITEMS:
        return True
    # Check identifier patterns
    id_lower = item.identifier.lower()
    for pattern in _WORLD_OBJECT_ID_PATTERNS:
        if pattern in id_lower:
            return True
    return False


def _should_have_page_item(item: Item, gd: GameData) -> bool:
    """Determine if an item should have its own wiki page.

    Items that place buildings are excluded here — they get a unified
    building page instead (which includes crafting/ingredient info).
    World objects (plants, trees, rocks) are excluded entirely.
    Seeds, critters, and dirt variants are handled by merged pages.
    """
    # Skip items that are purely internal
    if not item.name:
        return False
    # Skip if name looks like an identifier (starts with _base_ etc.)
    if item.name.startswith("_"):
        return False
    # Skip world decoration objects and merged-page items
    if _is_world_object(item):
        return False
    # Skip items that place buildings — these are covered by building pages
    building = gd.building_for_item(item.identifier)
    if building:
        bname = gd.building_name(building.identifier)
        # Only skip if the building also passes its own page filter
        if bname and not bname.startswith("_") and building.type not in _BUILDING_SKIP_TYPES:
            return False
    # Skip creative-mode only items with no recipes
    producing = gd.recipes_producing(item.identifier)
    consuming = gd.recipes_consuming(item.identifier)
    if not producing and not consuming and not item.can_be_traded:
        # Check if it's a meaningful item by flags
        if not item.flags or all(f in ("", "NONE") for f in item.flags):
            return False
    return True


def _sanitize_wiki_title(name: str) -> str:
    """Replace characters illegal in MediaWiki titles with safe equivalents.

    Converts square brackets to round brackets so that building names like
    'WGD[do not use]' become valid page titles ('WGD (do not use)').
    """
    return name.replace('[', '(').replace(']', ')')


def _is_valid_wiki_title(name: str) -> bool:
    """Check if a name can be used as a MediaWiki page title."""
    if not name:
        return False
    # MediaWiki forbids these characters in titles: # < > | { }
    # Note: [ ] are handled by _sanitize_wiki_title before this check is called.
    import re
    if re.search(r'[#<>|{}]', name):
        return False
    return True


def _should_have_page_building(building: Building, gd: GameData) -> bool:
    """Determine if a building should have its own wiki page."""
    name = gd.building_name(building.identifier)
    if not name or name.startswith("_"):
        return False
    if not _is_valid_wiki_title(_sanitize_wiki_title(name)):
        return False
    if building.type in _BUILDING_SKIP_TYPES:
        return False
    # Skip decorative natural objects
    if "forest" in building.identifier or "decor" in building.identifier:
        # But keep player-placeable decor
        item = gd.item_for_building(building.identifier)
        if not item:
            return False
    # Skip modular Module buildings that have no placing item — these are
    # auto-placed connectors / pipe attachments, not player-crafted buildings.
    if building.is_modular and building.modular_type == "Module":
        if not gd.item_for_building(building.identifier):
            return False
    return True


def _should_have_page_research(research: Research) -> bool:
    """Determine if research should have its own wiki page."""
    return bool(research.name and not research.name.startswith("_"))


def _should_have_page_element(element: Element) -> bool:
    """Determine if an element should have its own wiki page."""
    return bool(element.name and not element.name.startswith("_"))


# ======================================================================
# Exploration Unlock pages
# ======================================================================

def _exploration_unlock_ancestor_chain(unlock_id: str, gd: GameData) -> list[str]:
    """Walk unlock_dependencies back to the root and return the full chain.

    Returns identifiers from root → unlock_id (inclusive), suitable for
    rendering as a breadcrumb trail.
    """
    chain: list[str] = []
    current_id = unlock_id
    visited: set[str] = set()
    while current_id and current_id not in visited:
        chain.append(current_id)
        visited.add(current_id)
        u = gd.exploration_unlocks.get(current_id)
        if not u or not u.unlock_dependencies:
            break
        dep = u.unlock_dependencies[0]
        current_id = dep.get("explorationUnlockTemplateIdentifier", "") if isinstance(dep, dict) else ""
    chain.reverse()
    return chain


def _generate_exploration_unlock_page(unlock, gd: GameData, *, registry: PageTitleRegistry | None = None, page_title: str = "") -> str:
    """Generate complete wikitext for an exploration unlock page."""
    lines = []
    name = unlock.title

    # Infobox
    lines.append(f"{{{{Infobox Exploration Unlock|id={unlock.identifier}|image={name} (Exploration).png}}}}")
    lines.append("")

    # Lead paragraph
    lines.append(
        f"'''{name}''' is an exploration unlock in [[Foundry]]. "
        f"It is discovered through exploration and grants the player "
        f"new abilities or upgrades."
    )
    lines.append("")

    # Description section
    if unlock.description:
        lines.append("== Description ==")
        lines.append("")
        lines.append(unlock.description)
        lines.append("")

    # Recipe unlocks
    if unlock.crafting_recipe_unlocks:
        lines.append("== Unlocks ==")
        lines.append("")
        for recipe_id in unlock.crafting_recipe_unlocks:
            if isinstance(recipe_id, dict):
                recipe_id = recipe_id.get("identifier", "")
            recipe = gd.recipes.get(recipe_id)
            if recipe:
                lines.append(f"{{{{RecipeCard Recipe|id={recipe_id}}}}}")
                lines.append("")

    # Tech Tree — one breadcrumb per direct prerequisite chain
    prereq_ids = [
        d.get("explorationUnlockTemplateIdentifier", "")
        for d in unlock.unlock_dependencies
        if isinstance(d, dict)
    ]
    valid_prereqs = [pid for pid in prereq_ids if pid in gd.exploration_unlocks]
    if valid_prereqs:
        lines.append("== Tech Tree ==")
        lines.append("")
        for prereq_id in valid_prereqs:
            ancestor_chain = _exploration_unlock_ancestor_chain(prereq_id, gd)
            crumb_parts = []
            for aid in ancestor_chain:
                au = gd.exploration_unlocks.get(aid)
                if au and au.title:
                    ptitle = registry.get_title("Exploration Unlock", au.title) if registry else au.title
                    if ptitle != au.title:
                        crumb_parts.append(f"[[{ptitle}|{au.title}]]")
                    else:
                        crumb_parts.append(f"[[{au.title}]]")
            crumb_parts.append(f"'''{name}'''")
            lines.append(" → ".join(crumb_parts))
            lines.append("")

    # Tips placeholder — commented out so editors can uncomment and fill in
    lines.append("<!-- == Tips ==")
    lines.append("")
    lines.append("-->")
    lines.append("")

    # History section
    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    # See Also — real section if disambiguation siblings exist, placeholder otherwise
    lines.extend(_render_see_also(registry, "Exploration Unlock", unlock.title))

    # Navigation
    lines.append("{{Navbox Exploration Unlocks}}")
    lines.append("")
    lines.append("[[Category:Exploration Unlocks]]")

    return "\n".join(lines)


# ======================================================================
# Space Station (Sky Platform) Upgrade pages
# ======================================================================

def _generate_sky_platform_page(upgrade, gd: GameData, *, registry: PageTitleRegistry | None = None, page_title: str = "") -> str:
    """Generate complete wikitext for a sky platform upgrade page."""
    lines = []
    name = upgrade.name

    # Infobox
    lines.append(f"{{{{Infobox Sky Platform Upgrade|id={upgrade.identifier}|image={name} (Space Station).png}}}}")
    lines.append("")

    # Lead paragraph
    lines.append(
        f"'''{name}''' is a [[Space Station]] upgrade in [[Foundry]]."
    )
    lines.append("")

    # Description section
    if upgrade.description:
        lines.append("== Description ==")
        lines.append("")
        lines.append(upgrade.description)
        lines.append("")

    # Tips placeholder — commented out so editors can uncomment and fill in
    lines.append("<!-- == Tips ==")
    lines.append("")
    lines.append("-->")
    lines.append("")

    # History section
    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    # See Also — real section if disambiguation siblings exist, placeholder otherwise
    lines.extend(_render_see_also(registry, "Sky Platform", upgrade.name))

    # Navigation
    lines.append("{{Navbox Space Station Upgrades}}")
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


def _generate_seed_page(biome: str, plants_id: str, trees_id: str, gd: GameData) -> str:
    """Generate a merged seed page for a biome (combining plant + tree seeds)."""
    lines = []

    # Look up item name for the image param before building the infobox line
    plants_item = gd.items.get(plants_id)
    seed_image = f"{plants_item.name}.png" if plants_item else f"{biome} Plant Seed.png"
    lines.append(f"{{{{Infobox Item|id={plants_id}|image={seed_image}}}}}")
    lines.append("")

    lines.append(
        f"'''{biome} Seed''' is a plantable item that comes in two variants: "
        f"one for plants and one for trees. Seeds can be obtained by destroying "
        f"existing {biome.lower()} vegetation or produced in a [[Greenhouse]] "
        f"after researching the appropriate technology."
    )
    lines.append("")

    # Check recipes
    # (plants_item already fetched above)
    trees_item = gd.items.get(trees_id)

    producing_plants = gd.recipes_producing(plants_id) if plants_item else []
    producing_trees = gd.recipes_producing(trees_id) if trees_item else []

    if producing_plants or producing_trees:
        lines.append("== Production ==")
        lines.append("")
        if producing_plants:
            lines.append(f"{{{{RecipeCard|id={plants_id}}}}}")
            lines.append("")
        if producing_trees and trees_id != plants_id:
            lines.append(f"{{{{RecipeCard|id={trees_id}}}}}")
            lines.append("")

    # Usage
    consuming_plants = gd.recipes_consuming(plants_id) if plants_item else []
    consuming_trees = gd.recipes_consuming(trees_id) if trees_item else []

    if consuming_plants or consuming_trees:
        lines.append("== Usage ==")
        lines.append("")
        lines.append(
            "Seeds are consumed when planted, placing vegetation in the world. "
            "Plants and trees grow over time and can be harvested for [[Biomass]]."
        )
        lines.append("")

    # Navigation
    lines.append("{{Navbox Items}}")
    lines.append("")
    lines.append("[[Category:Resources]]")
    lines.append("[[Category:Seeds]]")

    return "\n".join(lines)


def _generate_critter_page(gd: GameData) -> str:
    """Generate a merged Critter page covering all biome critters."""
    lines = []

    _critter_item = gd.items.get("_base_critter_forest")
    _critter_img = f"{_critter_item.name}.png" if _critter_item else "Forest Critter.png"
    lines.append(f"{{{{Infobox Item|id=_base_critter_forest|image={_critter_img}}}}}")
    lines.append("")

    lines.append(
        "'''Critters''' are small creatures found across the various biomes of "
        "Foundry. They are passive wildlife that inhabit the world and do not "
        "interact with the player's factory infrastructure."
    )
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

    # Navigation
    lines.append("{{Navbox Items}}")
    lines.append("")
    lines.append("[[Category:Wildlife]]")

    return "\n".join(lines)


def _generate_dirt_page(gd: GameData) -> str:
    """Generate the Dirt page including biome dirt variants."""
    lines = []

    _dirt_item = gd.items.get("_base_dirt")
    _dirt_img = f"{_dirt_item.name}.png" if _dirt_item else "Dirt.png"
    lines.append(f"{{{{Infobox Item|id=_base_dirt|image={_dirt_img}}}}}")
    lines.append("")

    lines.append(
        "'''Dirt''' is a natural resource obtained by digging terrain. "
        "It appears in several biome-specific textures (Tropical Rainforest Dirt, "
        "Tundra Dirt, Rocky Desert Dirt) but all variants produce the same Dirt item "
        "when excavated. Dirt has no crafting uses and is primarily encountered "
        "as a byproduct of terrain modification."
    )
    lines.append("")

    lines.append("== Variants ==")
    lines.append("")
    lines.append(
        "Different biomes feature visually distinct dirt textures, but they are "
        "functionally identical:"
    )
    lines.append("")
    lines.append("* Tropical Rainforest Dirt — dark, rich soil")
    lines.append("* Tundra Dirt — pale, frozen ground")
    lines.append("* Rocky Desert Dirt — dry, reddish earth")
    lines.append("")

    # Navigation
    lines.append("{{Navbox Items}}")
    lines.append("")
    lines.append("[[Category:Resources]]")

    return "\n".join(lines)


def _generate_commands_page(gd: GameData) -> str:
    """Generate the Commands page listing all player command wheel entries."""
    lines = []

    item = gd.items.get("_base_commands")
    modes = item._raw.get("toggleableModes", []) if item else []

    lines.append(
        "'''Commands''' are a set of player actions accessible through the "
        "radial command wheel in [[Foundry]]. Each command triggers a "
        "specific in-game function such as toggling the flashlight, "
        "demolishing buildings, or calling the construction drone."
    )
    lines.append("")

    lines.append("== Command List ==")
    lines.append("")
    lines.append('{| class="wikitable sortable"')
    lines.append("! Name !! Internal Identifier")
    for mode in modes:
        name = mode.get("name", "")
        identifier = mode.get("identifier", "")
        lines.append("|-")
        lines.append(f"| {name} || <code>{identifier}</code>")
    lines.append("|}")
    lines.append("")

    lines.append("<!-- == Tips ==")
    lines.append("")
    lines.append("-->")
    lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.extend(_render_see_also(None, "Commands", "Commands"))

    lines.append("[[Category:Gameplay]]")

    return "\n".join(lines)


def _generate_emotes_page(gd: GameData) -> str:
    """Generate the Emotes page listing all player emote actions."""
    lines = []

    item = gd.items.get("_base_emotes")
    modes = item._raw.get("toggleableModes", []) if item else []

    lines.append(
        "'''Emotes''' are a set of character animations that players can "
        "trigger in [[Foundry]], primarily for use in multiplayer sessions. "
        "They are accessed through the radial emote wheel."
    )
    lines.append("")

    lines.append("== Emote List ==")
    lines.append("")
    lines.append('{| class="wikitable sortable"')
    lines.append("! Name !! Internal Identifier")
    for mode in modes:
        name = mode.get("name", "")
        identifier = mode.get("identifier", "")
        lines.append("|-")
        lines.append(f"| {name} || <code>{identifier}</code>")
    lines.append("|}")
    lines.append("")

    lines.append("<!-- == Tips ==")
    lines.append("")
    lines.append("-->")
    lines.append("")

    lines.append("== History ==")
    lines.append("")
    lines.append("{{History table}}")
    lines.append("")

    lines.extend(_render_see_also(None, "Emotes", "Emotes"))

    lines.append("[[Category:Gameplay]]")

    return "\n".join(lines)


def _generate_achievements_page() -> str:
    """Generate the Achievements page.

    Section headings live on the page so editors can add tips/notes under each
    one without those edits being wiped on the next generate-pages run.
    Each heading calls its dedicated Module:Achievements function which
    returns only the wikitable.  p.remaining renders heading + table for any
    achievement types added in future game updates.
    """
    lines = [
        "== Item Creation ==",
        "",
        "{{#invoke:Achievements|item_creation}}",
        "",
        "== Building Placement ==",
        "",
        "{{#invoke:Achievements|building_built}}",
        "",
        "== Research ==",
        "",
        "{{#invoke:Achievements|research}}",
        "",
        "== Lifetime Earnings ==",
        "",
        "{{#invoke:Achievements|lifetime_earnings}}",
        "",
        "== Market Dominance ==",
        "",
        "{{#invoke:Achievements|market_dominance}}",
        "",
        "== Space Station ==",
        "",
        "{{#invoke:Achievements|space_station}}",
        "",
        "== Quests ==",
        "",
        "{{#invoke:Achievements|quests}}",
        "",
        "== Special ==",
        "",
        "{{#invoke:Achievements|fixed}}",
        "",
        "<!-- Any achievement types not covered above are rendered here automatically. -->",
        "{{#invoke:Achievements|remaining}}",
        "",
        "== History ==",
        "",
        "{{History table}}",
        "",
        "[[Category:Gameplay]]",
    ]
    return "\n".join(lines)


# ======================================================================
# Title manifest helpers
# ======================================================================

def _write_titles_manifest(directory: Path, titles: dict[str, str]) -> None:
    """Write a _titles.json manifest mapping filename stem -> page title.

    This lets the uploader recover the exact page title for any file whose
    name was sanitised by _safe_filename (e.g. colons replaced with underscores).
    Only entries where the stem differs from the title are strictly necessary,
    but we write all of them for simplicity and debuggability.
    """
    manifest_path = directory / "_titles.json"
    manifest_path.write_text(
        json.dumps(titles, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


# ======================================================================
# Main export
# ======================================================================

def generate_all_pages(
    gd: GameData,
    output_dir: Path,
    verbose: bool = True,
) -> dict[str, int]:
    """
    Generate wiki pages for all entities.

    Returns dict of page_type -> count generated.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {
        "items": 0, "buildings": 0, "research": 0, "elements": 0,
        "exploration_unlocks": 0, "sky_platform_upgrades": 0,
        "z_redirects": 0,
    }

    # Clear stale page files from previous runs (disambiguation may have
    # renamed pages, leaving old un-suffixed files that would get uploaded
    # and overwrite the correct pages).
    for subdir_name in ("items", "buildings", "research", "elements",
                        "exploration_unlocks", "sky_platform_upgrades"):
        subdir = output_dir / subdir_name
        if subdir.exists():
            for old_file in subdir.glob("*.wikitext"):
                try:
                    old_file.unlink()
                except OSError:
                    pass  # skip files we can't delete (e.g. mount restrictions)

    # Build disambiguation registry
    registry = PageTitleRegistry()
    registry.build(gd)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # --- Items ---
    items_dir = output_dir / "items"
    items_dir.mkdir(exist_ok=True)
    items_titles: dict[str, str] = {}
    for item_id, item in sorted(gd.items.items()):
        if not _should_have_page_item(item, gd):
            continue
        page_title = registry.get_title("Item", item.name)
        page = _generate_item_page(item, gd, registry=registry, page_title=page_title)
        stem = _safe_filename(page_title)
        (items_dir / (stem + ".wikitext")).write_text(page, encoding="utf-8")
        items_titles[stem] = page_title
        counts["items"] += 1

    # --- Merged item pages (critters, dirt, commands, emotes) ---
    # Critter page
    page = _generate_critter_page(gd)
    (items_dir / "Critter.wikitext").write_text(page, encoding="utf-8")
    items_titles["Critter"] = "Critter"
    counts["items"] += 1

    # Dirt page (replaces the default one if it exists)
    page = _generate_dirt_page(gd)
    (items_dir / "Dirt.wikitext").write_text(page, encoding="utf-8")
    items_titles["Dirt"] = "Dirt"
    # Don't increment — the regular Dirt item might have already been counted
    # (it passes the filter since it has no building and no flag issues)

    # Commands page
    page = _generate_commands_page(gd)
    (items_dir / "Commands.wikitext").write_text(page, encoding="utf-8")
    items_titles["Commands"] = "Commands"
    counts["items"] += 1

    # Emotes page
    page = _generate_emotes_page(gd)
    (items_dir / "Emotes.wikitext").write_text(page, encoding="utf-8")
    items_titles["Emotes"] = "Emotes"
    counts["items"] += 1

    # Achievements page (content rendered via Module:Achievements + Module:Data/Achievements)
    page = _generate_achievements_page()
    (items_dir / "Achievements.wikitext").write_text(page, encoding="utf-8")
    items_titles["Achievements"] = "Achievements"
    counts["items"] += 1

    _write_titles_manifest(items_dir, items_titles)
    log(f"  Items: {counts['items']} pages")

    # --- Buildings ---
    buildings_dir = output_dir / "buildings"
    buildings_dir.mkdir(exist_ok=True)
    # Track names we've already generated to avoid duplicates
    # (multiple building IDs can share the same display name, e.g. tiers)
    generated_building_names: set[str] = set()
    buildings_titles: dict[str, str] = {}
    # Maps raw building display name -> modular item page title, used later
    # to generate "Blast Furnace" -> "Blast Furnace Base" redirects.
    modular_building_renames: dict[str, str] = {}

    for building_id, building in sorted(gd.buildings.items()):
        if not _should_have_page_building(building, gd):
            continue
        raw_name = _sanitize_wiki_title(gd.building_name(building.identifier))

        # For modular buildings (Base or Module), use the placing item's name
        # as the page title so that "Blast Furnace Base" and "Heavy Caster Module"
        # each get their own correctly-titled page rather than colliding under
        # the shared building display name.
        if building.is_modular:
            placing_item = gd.item_for_building(building_id)
            if placing_item and placing_item.name and not placing_item.name.startswith("_"):
                name = _sanitize_wiki_title(placing_item.name)
                if name != raw_name:
                    # Record for redirect generation (raw_name -> item page title).
                    # Base buildings take priority; don't overwrite an existing entry.
                    if raw_name not in modular_building_renames or building.modular_type == "Base":
                        modular_building_renames[raw_name] = name
            else:
                name = raw_name
        else:
            name = raw_name

        if name in generated_building_names:
            continue
        generated_building_names.add(name)
        page_title = registry.get_title("Building", name)
        page = _generate_building_page(building, gd, registry=registry, page_title=page_title)
        stem = _safe_filename(page_title)
        (buildings_dir / (stem + ".wikitext")).write_text(page, encoding="utf-8")
        buildings_titles[stem] = page_title
        counts["buildings"] += 1
    _write_titles_manifest(buildings_dir, buildings_titles)
    log(f"  Buildings: {counts['buildings']} pages")

    # --- Research ---
    research_dir = output_dir / "research"
    research_dir.mkdir(exist_ok=True)
    research_titles: dict[str, str] = {}
    for res_id, research in sorted(gd.research.items()):
        if not _should_have_page_research(research):
            continue
        page_title = registry.get_title("Research", research.name)
        page = _generate_research_page(research, gd, registry=registry, page_title=page_title)
        stem = _safe_filename(page_title)
        (research_dir / (stem + ".wikitext")).write_text(page, encoding="utf-8")
        research_titles[stem] = page_title
        counts["research"] += 1
    _write_titles_manifest(research_dir, research_titles)
    log(f"  Research: {counts['research']} pages")

    # --- Elements ---
    elements_dir = output_dir / "elements"
    elements_dir.mkdir(exist_ok=True)
    elements_titles: dict[str, str] = {}
    for elem_id, element in sorted(gd.elements.items()):
        if not _should_have_page_element(element):
            continue
        page_title = registry.get_title("Element", element.name)
        page = _generate_element_page(element, gd, registry=registry, page_title=page_title)
        stem = _safe_filename(page_title)
        (elements_dir / (stem + ".wikitext")).write_text(page, encoding="utf-8")
        elements_titles[stem] = page_title
        counts["elements"] += 1
    _write_titles_manifest(elements_dir, elements_titles)
    log(f"  Elements: {counts['elements']} pages")

    # --- Exploration Unlocks ---
    unlocks_dir = output_dir / "exploration_unlocks"
    unlocks_dir.mkdir(exist_ok=True)
    unlocks_titles: dict[str, str] = {}
    for unlock_id, unlock in sorted(gd.exploration_unlocks.items()):
        if not unlock.title or unlock.title.startswith("_"):
            continue
        page_title = registry.get_title("Exploration Unlock", unlock.title)
        page = _generate_exploration_unlock_page(unlock, gd, registry=registry, page_title=page_title)
        stem = _safe_filename(page_title)
        (unlocks_dir / (stem + ".wikitext")).write_text(page, encoding="utf-8")
        unlocks_titles[stem] = page_title
        counts["exploration_unlocks"] += 1
    _write_titles_manifest(unlocks_dir, unlocks_titles)
    log(f"  Exploration Unlocks: {counts['exploration_unlocks']} pages")

    # --- Sky Platform Upgrades ---
    sky_dir = output_dir / "sky_platform_upgrades"
    sky_dir.mkdir(exist_ok=True)
    sky_titles: dict[str, str] = {}
    for upgrade_id, upgrade in sorted(gd.sky_platform_upgrades.items()):
        if not upgrade.name or upgrade.name.startswith("_"):
            continue
        page_title = registry.get_title("Sky Platform", upgrade.name)
        page = _generate_sky_platform_page(upgrade, gd, registry=registry, page_title=page_title)
        stem = _safe_filename(page_title)
        (sky_dir / (stem + ".wikitext")).write_text(page, encoding="utf-8")
        sky_titles[stem] = page_title
        counts["sky_platform_upgrades"] += 1
    _write_titles_manifest(sky_dir, sky_titles)
    log(f"  Sky Platform Upgrades: {counts['sky_platform_upgrades']} pages")

    # --- Redirects ---
    redirects_dir = output_dir / "z_redirects"
    redirects_dir.mkdir(exist_ok=True)
    # Clear stale redirect files
    for old_file in redirects_dir.glob("*.wikitext"):
        old_file.unlink()

    redirects = registry.get_all_redirects()
    redirects_titles: dict[str, str] = {}
    for redirect_title, target_title in redirects:
        content = f"#REDIRECT [[{target_title}]]"
        stem = _safe_filename(redirect_title)
        (redirects_dir / (stem + ".wikitext")).write_text(content, encoding="utf-8")
        redirects_titles[stem] = redirect_title
    # Redirects for building-placing items whose name differs from their building.
    # For modular Base buildings the page title IS the item name, so we instead
    # redirect the raw building name -> item name (e.g. "Blast Furnace" -> "Blast
    # Furnace Base").  For non-modular buildings the original logic applies:
    # item name -> building page title.
    for item_id, item in sorted(gd.items.items(), key=lambda x: x[1].name or ""):
        if not item.name or item.name.startswith("_"):
            continue
        building = gd.building_for_item(item_id)
        if not building:
            continue
        bname = gd.building_name(building.identifier)
        if not bname or bname.startswith("_") or building.type in _BUILDING_SKIP_TYPES:
            continue
        if item.name == bname:
            continue  # same name — no redirect needed

        if building.is_modular and building.modular_type == "Base":
            # Page lives at item.name ("Blast Furnace Base").
            # Redirect the raw building name ("Blast Furnace") -> item name.
            redirect_from = bname
            redirect_to = item.name
        else:
            # Non-modular: page lives at building name; redirect item name -> it.
            redirect_from = item.name
            redirect_to = registry.get_title("Building", bname)

        stem = _safe_filename(redirect_from)
        redirect_file = redirects_dir / (stem + ".wikitext")
        if redirect_file.exists():
            continue  # never overwrite a real content page
        content = f"#REDIRECT [[{redirect_to}]]"
        redirect_file.write_text(content, encoding="utf-8")
        redirects_titles[stem] = redirect_from

    # Redirects for modular buildings whose raw display name was repurposed as
    # a page title for a different building (e.g. "Heavy Caster" raw name is
    # shared by both the Base and the Module building; the Base wins the
    # "Heavy Caster Base" title and the Module gets "Heavy Caster Module", so
    # "Heavy Caster" itself should redirect to "Heavy Caster Base").
    for raw_name, item_page_title in modular_building_renames.items():
        stem = _safe_filename(raw_name)
        redirect_file = redirects_dir / (stem + ".wikitext")
        if redirect_file.exists():
            continue
        content = f"#REDIRECT [[{item_page_title}]]"
        redirect_file.write_text(content, encoding="utf-8")
        redirects_titles[stem] = raw_name

    _write_titles_manifest(redirects_dir, redirects_titles)
    counts["z_redirects"] = len(redirects_titles)
    log(f"  Redirects: {counts['z_redirects']} pages")

    total = sum(counts.values())
    log(f"  Total: {total} pages generated in {output_dir}/")

    return counts