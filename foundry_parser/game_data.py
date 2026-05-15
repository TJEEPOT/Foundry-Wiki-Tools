"""
GameData - central registry that loads every template category and provides
cross-referenced lookups.

Usage:
    from foundry_parser.game_data import GameData

    gd = GameData.from_game_dir(Path("F:/SteamLibrary/.../FOUNDRY"))
    print(gd.items["_base_stone"].name)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .loader import load_template_dir_batch
from .models import (
    BlastFurnaceMode,
    Building,
    BuildableObjectConversionGroup,
    CompanyRank,
    CraftingRecipe,
    CraftingTag,
    Element,
    ExplorationUnlock,
    Industry,
    InfoDatabaseEntry,
    Item,
    ItemCategory,
    OreVein,
    Quest,
    RecipeCategory,
    RecipeRowGroup,
    Research,
    SkyPlatformUpgrade,
    TerrainBlock,
)


@dataclass
class GameData:
    """Complete parsed game data with cross-reference indices."""

    # Core entities
    items: dict[str, Item] = field(default_factory=dict)
    buildings: dict[str, Building] = field(default_factory=dict)
    recipes: dict[str, CraftingRecipe] = field(default_factory=dict)
    research: dict[str, Research] = field(default_factory=dict)

    # Supporting lookups
    item_categories: dict[str, ItemCategory] = field(default_factory=dict)
    recipe_categories: dict[str, RecipeCategory] = field(default_factory=dict)
    recipe_row_groups: dict[str, RecipeRowGroup] = field(default_factory=dict)
    crafting_tags: dict[str, CraftingTag] = field(default_factory=dict)
    elements: dict[str, Element] = field(default_factory=dict)
    terrain_blocks: dict[str, TerrainBlock] = field(default_factory=dict)
    exploration_unlocks: dict[str, ExplorationUnlock] = field(default_factory=dict)
    sky_platform_upgrades: dict[str, SkyPlatformUpgrade] = field(default_factory=dict)
    quests: dict[str, Quest] = field(default_factory=dict)
    blast_furnace_modes: dict[str, BlastFurnaceMode] = field(default_factory=dict)
    industries: dict[str, Industry] = field(default_factory=dict)
    company_ranks: dict[str, CompanyRank] = field(default_factory=dict)
    ore_veins: dict[str, OreVein] = field(default_factory=dict)
    conversion_groups: dict[str, BuildableObjectConversionGroup] = field(
        default_factory=dict
    )
    info_database: dict[str, InfoDatabaseEntry] = field(default_factory=dict)

    # Raw data for categories without dedicated models
    raw_categories: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    # Cross-reference indices (built after loading)
    _recipe_outputs_index: dict[str, list[str]] = field(default_factory=dict)
    _recipe_inputs_index: dict[str, list[str]] = field(default_factory=dict)
    _research_unlocks_index: dict[str, list[str]] = field(default_factory=dict)
    _item_to_building_index: dict[str, str] = field(default_factory=dict)
    _building_to_item_index: dict[str, str] = field(default_factory=dict)
    _building_recipes_index: dict[str, list[str]] = field(default_factory=dict)

    _CATEGORY_MAP: dict[str, tuple[str, type]] = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._CATEGORY_MAP = {
            "ItemTemplate": ("items", Item),
            "BuildableObjectTemplate": ("buildings", Building),
            "CraftingRecipe": ("recipes", CraftingRecipe),
            "ResearchTemplate": ("research", Research),
            "ItemCategoryTemplate": ("item_categories", ItemCategory),
            "CraftingRecipeCategory": ("recipe_categories", RecipeCategory),
            "CraftingRecipeRowGroup": ("recipe_row_groups", RecipeRowGroup),
            "CraftingTag": ("crafting_tags", CraftingTag),
            "ElementTemplate": ("elements", Element),
            "TerrainBlockType": ("terrain_blocks", TerrainBlock),
            "ExplorationUnlockTemplate": ("exploration_unlocks", ExplorationUnlock),
            "SkyPlatformUpgradeTemplate": (
                "sky_platform_upgrades",
                SkyPlatformUpgrade,
            ),
            "QuestTemplate": ("quests", Quest),
            "BlastFurnaceModeTemplate": ("blast_furnace_modes", BlastFurnaceMode),
            "IndustryTemplate": ("industries", Industry),
            "CompanyRankTemplate": ("company_ranks", CompanyRank),
            "OreVeinTemplate": ("ore_veins", OreVein),
            "BuildableObjectConversionGroup": (
                "conversion_groups",
                BuildableObjectConversionGroup,
            ),
            "InfoDatabaseTemplate": ("info_database", InfoDatabaseEntry),
        }

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def from_game_dir(cls, game_dir: Path) -> GameData:
        """Load all templates from a Foundry installation directory."""
        templates_root = game_dir / "foundry_Data" / "StreamingAssets" / "Templates"
        return cls.from_templates_dir(templates_root)

    @classmethod
    def from_templates_dir(cls, templates_root: Path) -> GameData:
        """Load all templates from the Templates directory."""
        gd = cls()

        if not templates_root.is_dir():
            raise FileNotFoundError(
                f"Templates directory not found: {templates_root}"
            )

        for category_dir in sorted(templates_root.iterdir()):
            if not category_dir.is_dir():
                continue

            category_name = category_dir.name
            raw_data = load_template_dir_batch(category_dir)

            if not raw_data:
                continue

            if category_name in gd._CATEGORY_MAP:
                attr_name, model_cls = gd._CATEGORY_MAP[category_name]
                target = getattr(gd, attr_name)
                for identifier, data in raw_data.items():
                    try:
                        target[identifier] = model_cls.from_raw(data)
                    except Exception as e:
                        print(
                            f"Warning: Failed to parse "
                            f"{category_name}/{identifier}: {e}"
                        )
            else:
                gd.raw_categories[category_name] = raw_data

        gd._build_indices()
        return gd

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_indices(self) -> None:
        """Build all cross-reference indices after loading."""
        self._build_recipe_indices()
        self._build_research_index()
        self._build_item_building_index()
        self._build_building_recipes_index()

    def _build_recipe_indices(self) -> None:
        self._recipe_outputs_index.clear()
        self._recipe_inputs_index.clear()
        for recipe_id, recipe in self.recipes.items():
            for output in recipe.outputs:
                self._recipe_outputs_index.setdefault(
                    output.identifier, []
                ).append(recipe_id)
            for inp in recipe.inputs:
                self._recipe_inputs_index.setdefault(
                    inp.identifier, []
                ).append(recipe_id)

    def _build_research_index(self) -> None:
        self._research_unlocks_index.clear()
        for research_id, res in self.research.items():
            for unlock in res.crafting_unlocks:
                self._research_unlocks_index.setdefault(
                    unlock, []
                ).append(research_id)

    def _build_item_building_index(self) -> None:
        self._item_to_building_index.clear()
        self._building_to_item_index.clear()
        for item_id, item in self.items.items():
            if item.buildable_object_id:
                self._item_to_building_index[item_id] = item.buildable_object_id
                self._building_to_item_index[item.buildable_object_id] = item_id

    def _build_building_recipes_index(self) -> None:
        self._building_recipes_index.clear()
        tag_to_recipes: dict[str, list[str]] = {}
        for recipe_id, recipe in self.recipes.items():
            for tag in recipe.tags:
                tag_to_recipes.setdefault(tag, []).append(recipe_id)
        for building_id, building in self.buildings.items():
            recipe_ids: list[str] = []
            for tag in building.producer_recipe_tags:
                recipe_ids.extend(tag_to_recipes.get(tag, []))
            if building.auto_producer_tag:
                recipe_ids.extend(
                    tag_to_recipes.get(building.auto_producer_tag, [])
                )
            if recipe_ids:
                self._building_recipes_index[building_id] = sorted(
                    set(recipe_ids)
                )

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def recipes_producing(self, item_id: str) -> list[CraftingRecipe]:
        """Get all recipes that produce a given item."""
        return [
            self.recipes[rid]
            for rid in self._recipe_outputs_index.get(item_id, [])
            if rid in self.recipes
        ]

    def recipes_consuming(self, item_id: str) -> list[CraftingRecipe]:
        """Get all recipes that consume a given item as input."""
        return [
            self.recipes[rid]
            for rid in self._recipe_inputs_index.get(item_id, [])
            if rid in self.recipes
        ]

    def research_unlocking(self, recipe_or_item_id: str) -> list[Research]:
        """Get research nodes that unlock a given recipe/item."""
        return [
            self.research[rid]
            for rid in self._research_unlocks_index.get(
                recipe_or_item_id, []
            )
            if rid in self.research
        ]

    def building_for_item(self, item_id: str) -> Building | None:
        """Get the building associated with an item."""
        building_id = self._item_to_building_index.get(item_id)
        return self.buildings.get(building_id) if building_id else None

    def item_for_building(self, building_id: str) -> Item | None:
        """Get the item associated with a building."""
        item_id = self._building_to_item_index.get(building_id)
        return self.items.get(item_id) if item_id else None

    def recipes_for_building(self, building_id: str) -> list[CraftingRecipe]:
        """Get all recipes a building can craft."""
        return [
            self.recipes[rid]
            for rid in self._building_recipes_index.get(building_id, [])
            if rid in self.recipes
        ]

    def research_dependencies_tree(self, research_id: str) -> list[list[str]]:
        """Get the full dependency chain for a research node (BFS layers)."""
        if research_id not in self.research:
            return []
        layers: list[list[str]] = []
        current_layer = [research_id]
        visited: set[str] = {research_id}
        while current_layer:
            next_layer: list[str] = []
            for rid in current_layer:
                res = self.research.get(rid)
                if not res:
                    continue
                for dep in res.dependencies:
                    if dep not in visited:
                        visited.add(dep)
                        next_layer.append(dep)
            if next_layer:
                layers.append(next_layer)
            current_layer = next_layer
        return layers

    def item_name(self, item_id: str) -> str:
        """Get display name for an item, falling back to identifier."""
        item = self.items.get(item_id)
        return item.name if item else item_id

    def building_name(self, building_id: str) -> str:
        """Get display name for a building."""
        building = self.buildings.get(building_id)
        if building and building.has_name_override and building.name_override:
            return building.name_override
        item = self.item_for_building(building_id)
        if item:
            return item.name
        return building_id

    def element_name(self, element_id: str) -> str:
        """Get display name for an element."""
        element = self.elements.get(element_id)
        return element.name if element else element_id

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, int]:
        """Return counts for each loaded category."""
        counts = {
            "items": len(self.items),
            "buildings": len(self.buildings),
            "recipes": len(self.recipes),
            "research": len(self.research),
            "item_categories": len(self.item_categories),
            "recipe_categories": len(self.recipe_categories),
            "recipe_row_groups": len(self.recipe_row_groups),
            "crafting_tags": len(self.crafting_tags),
            "elements": len(self.elements),
            "terrain_blocks": len(self.terrain_blocks),
            "exploration_unlocks": len(self.exploration_unlocks),
            "sky_platform_upgrades": len(self.sky_platform_upgrades),
            "quests": len(self.quests),
            "blast_furnace_modes": len(self.blast_furnace_modes),
            "industries": len(self.industries),
            "company_ranks": len(self.company_ranks),
            "ore_veins": len(self.ore_veins),
            "conversion_groups": len(self.conversion_groups),
            "info_database": len(self.info_database),
        }
        for cat_name, cat_data in self.raw_categories.items():
            counts[f"raw:{cat_name}"] = len(cat_data)
        return counts

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(self, output_path: Path, indent: int = 2) -> None:
        """Export all parsed data to a JSON file for inspection."""

        def _serialise(obj: Any) -> Any:
            if hasattr(obj, "__dataclass_fields__"):
                d = {}
                for fname in obj.__dataclass_fields__:
                    if fname.startswith("_"):
                        continue
                    d[fname] = _serialise(getattr(obj, fname))
                return d
            if isinstance(obj, dict):
                return {k: _serialise(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialise(v) for v in obj]
            return obj

        data = {
            "items": _serialise(self.items),
            "buildings": _serialise(self.buildings),
            "recipes": _serialise(self.recipes),
            "research": _serialise(self.research),
            "item_categories": _serialise(self.item_categories),
            "recipe_categories": _serialise(self.recipe_categories),
            "crafting_tags": _serialise(self.crafting_tags),
            "elements": _serialise(self.elements),
            "terrain_blocks": _serialise(self.terrain_blocks),
            "exploration_unlocks": _serialise(self.exploration_unlocks),
            "sky_platform_upgrades": _serialise(self.sky_platform_upgrades),
            "blast_furnace_modes": _serialise(self.blast_furnace_modes),
            "ore_veins": _serialise(self.ore_veins),
            "info_database": _serialise(self.info_database),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
