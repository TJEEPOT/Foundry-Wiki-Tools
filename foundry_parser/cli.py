"""
Command-line interface for the Foundry parser.

Usage:
    python -m foundry_parser parse <game_dir> [--output <json_path>]
    python -m foundry_parser summary <game_dir>
    python -m foundry_parser lookup <game_dir> <type> <identifier>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .game_data import GameData


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

    args = parser.parse_args()

    if args.command == "parse":
        cmd_parse(args)
    elif args.command == "summary":
        cmd_summary(args)
    elif args.command == "lookup":
        cmd_lookup(args)


if __name__ == "__main__":
    main()
