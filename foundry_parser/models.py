"""
Data models for parsed Foundry game entities.

Each model extracts and normalises the wiki-relevant fields from raw YAML data,
discarding Unity-specific fields (asset paths, mesh data, prefab references, etc.)
that aren't useful for wiki content.

Design notes:
  - Models are plain dataclasses for easy serialisation and inspection.
  - Raw data is always preserved in a `_raw` field for debugging and for
    accessing fields that aren't yet explicitly modelled.
  - Identifier cross-references are stored as strings; the GameData class
    in game_data.py resolves them into object references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_numeric_str(value: Any) -> float | None:
    """Parse a value that may be stored as a string (common '_str' suffix fields)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_flags(value: Any) -> list[str]:
    """Parse a pipe-separated flags string into a list."""
    if not value or not isinstance(value, str):
        return []
    return [f.strip() for f in value.split("|") if f.strip()]


# ---------------------------------------------------------------------------
# Crafting I/O entries
# ---------------------------------------------------------------------------

@dataclass
class CraftingIO:
    """An input or output entry in a crafting recipe."""
    identifier: str
    amount: int
    percentage: float = 1.0

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> CraftingIO:
        return cls(
            identifier=data["identifier"],
            amount=int(data.get("amount", 0)),
            percentage=_parse_numeric_str(data.get("percentage_str", "1")) or 1.0,
        )


@dataclass
class ElementalIO:
    """An elemental (fluid) input or output entry."""
    identifier: str
    amount: float

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> ElementalIO:
        return cls(
            identifier=data["identifier"],
            amount=_parse_numeric_str(data.get("amount_str", "0")) or 0.0,
        )


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

@dataclass
class Item:
    """An item (material, component, tool, bot, etc.)."""
    identifier: str
    name: str
    icon: str
    stack_size: int
    weight_grams: int
    flags: list[str]
    category_id: str
    category_sort_order: int
    creative_mode_category: str
    can_be_traded: bool
    buy_price: int
    sell_price: int
    is_hidden: bool

    # Fuel properties
    fuel_value_kj: float | None
    fuel_residual_item: str
    fuel_residual_count: int

    # Sales properties
    sales_category: str
    sales_industry: str
    sales_currency_amount: int
    sales_platform_capacity: int
    sales_demand_per_day: int

    # Science pack properties
    science_pack_sort_order: int

    # Recycling
    recycling_data: list[dict[str, Any]]

    # Buildable object link
    buildable_object_id: str

    # Auto-producer recipes (for items that suggest their own recipe in machines)
    auto_producer_recipes: list[dict[str, str]]

    # Workstation effect properties
    workstation_effect: str
    workstation_data01: float
    workstation_data02: float

    # Exploration unlock flavor
    exploration_sort_order: int
    exploration_flavor_text: str

    # Warehouse
    warehouse_stack_size: int

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Item:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            stack_size=int(data.get("stackSize", 0)),
            weight_grams=int(data.get("_baseWeightInGrams", 0)),
            flags=_parse_flags(data.get("flags", "")),
            category_id=data.get("itemCategoryIdentifier", ""),
            category_sort_order=int(data.get("itemCategorySortOrder", 0)),
            creative_mode_category=data.get("creativeModeCategory_str", ""),
            can_be_traded=bool(data.get("canBeTradedOnStation", False)),
            buy_price=int(data.get("market_buyPrice", 0)),
            sell_price=int(data.get("market_sellPrice", 0)),
            is_hidden=bool(data.get("isHiddenItem", False)),
            fuel_value_kj=_parse_numeric_str(data.get("burnable_fuelValueKJ_str")),
            fuel_residual_item=data.get("burnable_residualItemTemplate_str", ""),
            fuel_residual_count=int(data.get("burnable_residualItemTemplate_count", 0)),
            sales_category=data.get("salesItem_salesItemCategoryIdentifier", ""),
            sales_industry=data.get("salesItem_industryIdentifier", ""),
            sales_currency_amount=int(data.get("salesItem_currencyAmount", 0)),
            sales_platform_capacity=int(data.get("salesItem_skyPlatformBaseCapacity", 0)),
            sales_demand_per_day=int(data.get("salesItem_salesPlatformBaseDemandPerDay", 25)),
            science_pack_sort_order=int(data.get("sciencePack_researchFrameSortingOrder", 0)),
            recycling_data=data.get("recyclingData", []),
            buildable_object_id=data.get("buildableObjectIdentifer", ""),
            auto_producer_recipes=data.get("autoProducerRecipes", []),
            workstation_effect=data.get("workstationItem_effect", ""),
            workstation_data01=float(data.get("workstationItem_data01", 0)),
            workstation_data02=float(data.get("workstationItem_data02", 0)),
            exploration_sort_order=int(data.get("explorationUnlockInput_sortOrderASC", 0)),
            exploration_flavor_text=data.get("explorationUnlockInput_flavorText", ""),
            warehouse_stack_size=int(data.get("warehouse_stackSize", 0)),
            _raw=data,
        )


# ---------------------------------------------------------------------------
# Building (BuildableObject)
# ---------------------------------------------------------------------------

@dataclass
class Building:
    """A buildable object (machine, structure, conveyor, etc.)."""
    identifier: str
    type: str  # AutoProducer, Conveyor, Storage, etc.
    name_override: str
    has_name_override: bool
    size: dict[str, int]  # {x, y, z}
    has_foundation: bool
    rotation_allowed: bool
    can_be_destroyed_by_dynamite: bool
    demolition_time_sec: float
    is_visible_on_map: bool

    # Power
    power_type: str  # PCM, etc.
    power_subtype: str  # POWER_CONSUMER, POWER_PRODUCER, etc.
    energy_consumption_kw: float | None

    # Producer properties
    producer_recipe_type: str
    producer_recipe_tags: list[str]
    producer_time_modifier: float | None
    auto_producer_tag: str
    auto_producer_time_modifier: float | None

    # Storage
    storage_slot_size: int

    # Conveyor
    conveyor_speed: int
    conveyor_is_slope: bool

    # Item buffer layout
    item_buffer_slots: list[dict[str, Any]]

    # Modular building
    is_modular: bool
    modular_type: str

    # Workstation
    workstation_robot_slots: int
    workstation_effect_tags: list[str]
    workstation_power_core_slots: int

    # Data system
    has_data_system: bool

    # Fluid box
    has_fluid_box: bool

    # Loader
    loader_level: int

    # Various specific building type data
    solar_output_max: float | None
    solar_output_min: float | None
    battery_capacity_kj: float | None
    transformer_rate: float | None

    # Conversion group (for upgrade paths)
    conversion_group: str

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Building:
        size_raw = data.get("size", {})
        return cls(
            identifier=data.get("identifier", ""),
            type=data.get("type", ""),
            name_override=data.get("nameOverride", ""),
            has_name_override=bool(data.get("hasNameOverride", False)),
            size={
                "x": int(size_raw.get("x", 0)),
                "y": int(size_raw.get("y", 0)),
                "z": int(size_raw.get("z", 0)),
            },
            has_foundation=bool(data.get("hasToBeOnFoundation", False)),
            rotation_allowed=bool(data.get("rotationAllowed", True)),
            can_be_destroyed_by_dynamite=bool(data.get("canBeDestroyedByDynamite", True)),
            demolition_time_sec=float(data.get("demolitionTimeSec", 1)),
            is_visible_on_map=bool(data.get("isVisibleOnMap", True)),
            power_type=data.get("powerComponentType", ""),
            power_subtype=data.get("powerSubType", ""),
            energy_consumption_kw=_parse_numeric_str(data.get("energyConsumptionKW_str")),
            producer_recipe_type=data.get("producerRecipeType", ""),
            producer_recipe_tags=data.get("producer_recipeType_tags", []),
            producer_time_modifier=_parse_numeric_str(data.get("producer_recipeTimeModifier_str")),
            auto_producer_tag=data.get("autoProducer_recipeType_tag", ""),
            auto_producer_time_modifier=_parse_numeric_str(
                data.get("autoProducer_recipeTimeModifier_str")
            ),
            storage_slot_size=int(data.get("storage_slotSize", 0)),
            conveyor_speed=int(data.get("conveyor_speed_slotsPerTick", 0)),
            conveyor_is_slope=bool(data.get("conveyor_isSlope", False)),
            item_buffer_slots=data.get("itemBufferSlotMap", []),
            is_modular=bool(data.get("isModularBuilding", False)),
            modular_type=data.get("modularBuildingType", ""),
            workstation_robot_slots=int(data.get("workstation_robotSlotCount", 0)),
            workstation_effect_tags=[
                # Tags come as "identifier|guid" — extract just the identifier
                t.split("|")[0] if isinstance(t, str) else t
                for t in data.get("workstationEffectTags", [])
            ],
            workstation_power_core_slots=int(data.get("workstation_powerCoreSlots", 0)),
            has_data_system=bool(data.get("hasDataSystemManager", False)),
            has_fluid_box=bool(data.get("hasFluidBoxManager", False)),
            loader_level=int(data.get("loaderLevel", 0)),
            solar_output_max=_parse_numeric_str(data.get("solarPanel_outputMax_str")),
            solar_output_min=_parse_numeric_str(data.get("solarPanel_outputMin_str")),
            battery_capacity_kj=_parse_numeric_str(data.get("battery_capacityKJ_str")),
            transformer_rate=_parse_numeric_str(data.get("transformer_transmissionRate_kjPerS_str")),
            conversion_group=data.get("conversionGroup_str", ""),
            _raw=data,
        )


# ---------------------------------------------------------------------------
# Crafting Recipe
# ---------------------------------------------------------------------------

@dataclass
class CraftingRecipe:
    """A crafting recipe defining inputs, outputs, time, and where it can be crafted."""
    identifier: str
    name: str
    icon: str
    category_id: str
    row_group_id: str
    sort_order: int
    time_ms: int
    tags: list[str]  # Which machine types can use this recipe
    is_hidden: bool

    inputs: list[CraftingIO]
    outputs: list[CraftingIO]
    elemental_inputs: list[ElementalIO]
    elemental_outputs: list[ElementalIO]

    related_item_id: str
    recipe_priority: int

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> CraftingRecipe:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            category_id=data.get("category_identifier", ""),
            row_group_id=data.get("rowGroup_identifier", ""),
            sort_order=int(data.get("sortingOrderWithinRowGroup", 0)),
            time_ms=int(data.get("timeMs", 0)),
            tags=data.get("tags", []),
            is_hidden=bool(data.get("isHiddenInCharacterCraftingFrame", False)),
            inputs=[CraftingIO.from_raw(d) for d in data.get("input_data", [])],
            outputs=[CraftingIO.from_raw(d) for d in data.get("output_data", [])],
            elemental_inputs=[
                ElementalIO.from_raw(d) for d in data.get("inputElemental_data", [])
            ],
            elemental_outputs=[
                ElementalIO.from_raw(d) for d in data.get("outputElemental_data", [])
            ],
            related_item_id=data.get("relatedItemTemplateIdentifier", ""),
            recipe_priority=int(data.get("recipePriority", 1000)),
            _raw=data,
        )

    @property
    def time_seconds(self) -> float:
        return self.time_ms / 1000.0


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

@dataclass
class ResearchCost:
    """A science pack cost for a research node."""
    identifier: str
    amount: int

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> ResearchCost:
        return cls(
            identifier=data["identifier"],
            amount=int(data.get("amount", 0)),
        )


@dataclass
class Research:
    """A research/technology node."""
    identifier: str
    name: str
    icon: str
    description: str
    seconds_per_science_item: int

    costs: list[ResearchCost]
    dependencies: list[str]  # Research identifiers that must be completed first
    crafting_unlocks: list[str]  # Recipe identifiers unlocked
    blast_furnace_modes: list[str]
    assembly_line_objects: list[str]
    ore_scanner_unlocks: list[str]
    sky_platform_visibility: list[str]
    shipping_pad_visibility: list[str]
    galactic_market_visibility: list[str]

    # Special unlocks
    additional_inventory_slots: int
    mining_hardness_level: int
    jetpack_speed_increase: float | None

    required_company_rank: str

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Research:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            description=data.get("description", ""),
            seconds_per_science_item=int(data.get("secondsPerScienceItem", 0)),
            costs=[ResearchCost.from_raw(d) for d in data.get("input_data", [])],
            dependencies=data.get("list_researchDependencies_str", []),
            crafting_unlocks=data.get("list_craftingUnlocks_str", []),
            blast_furnace_modes=data.get("list_blastFurnaceModes_str", []),
            assembly_line_objects=data.get("list_alots_str", []),
            ore_scanner_unlocks=data.get("list_oreScannerUnlocks_str", []),
            sky_platform_visibility=data.get("list_skyPlatformItemVisibility_str", []),
            shipping_pad_visibility=data.get("list_shippingPadItemVisibility_str", []),
            galactic_market_visibility=data.get("list_galacticMarketItemVisibility_str", []),
            additional_inventory_slots=int(data.get("inventorySize_additionalInventorySlots", 0)),
            mining_hardness_level=int(data.get("miningHardness_unlockedLevel", 0)),
            jetpack_speed_increase=_parse_numeric_str(
                data.get("jetpackSpeed_speedIncreasmentPercent_str")
            ),
            required_company_rank=data.get("requiredCompanyRankIdentifier", ""),
            _raw=data,
        )


# ---------------------------------------------------------------------------
# Supporting / Lookup Templates
# ---------------------------------------------------------------------------

@dataclass
class ItemCategory:
    """An item category (Components, Raw Materials, etc.)."""
    identifier: str
    name: str
    icon: str
    sort_order: int
    station_capacity_per_level: int

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> ItemCategory:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            sort_order=int(data.get("sortingOrder", 0)),
            station_capacity_per_level=int(data.get("stationCapacityPerLevel", 0)),
            _raw=data,
        )


@dataclass
class RecipeCategory:
    """A crafting recipe category (Structures, Components, etc.)."""
    identifier: str
    name: str
    icon: str
    default_row_group: str
    sort_order: int

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> RecipeCategory:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            default_row_group=data.get("identifier_defaultRowGroup", ""),
            sort_order=int(data.get("sortOrderASC", 0)),
            _raw=data,
        )


@dataclass
class RecipeRowGroup:
    """A row group within a recipe category."""
    identifier: str
    title: str
    sort_order: int
    category_id: str

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> RecipeRowGroup:
        return cls(
            identifier=data.get("identifier", ""),
            title=data.get("title", ""),
            sort_order=int(data.get("sortingOrder", 0)),
            category_id=data.get("identifier_category", ""),
            _raw=data,
        )


@dataclass
class CraftingTag:
    """A crafting tag that defines what machines can craft what recipes."""
    identifier: str
    name: str

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> CraftingTag:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            _raw=data,
        )


@dataclass
class Element:
    """A fluid/gas element (water, air, molten metal, etc.)."""
    identifier: str
    name: str
    icon: str
    flags: list[str]
    pipe_content_type: int
    fuel_value_kj_per_l: float | None

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Element:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            flags=_parse_flags(data.get("flags", "")),
            pipe_content_type=int(data.get("pipeContentType", 0)),
            fuel_value_kj_per_l=_parse_numeric_str(data.get("fuel_fuelValueKJPerL_str")),
            _raw=data,
        )


@dataclass
class TerrainBlock:
    """A terrain block type (ores, stone, bedrock, etc.)."""
    identifier: str
    name: str
    destructible: bool
    yield_item: str
    mining_time_sec: float
    required_mining_hardness: int
    ore_yield_id: str
    average_yield: int

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> TerrainBlock:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            destructible=bool(data.get("destructible", False)),
            yield_item=data.get("yieldItemOnDig", ""),
            mining_time_sec=float(data.get("miningTimeInSec", 0)),
            required_mining_hardness=int(data.get("requiredMiningHardnessLevel", 0)),
            ore_yield_id=data.get("ore_yield_id", ""),
            average_yield=int(data.get("averageYield", 0)),
            _raw=data,
        )


@dataclass
class ExplorationUnlock:
    """An exploration unlock (character upgrades from alien artifacts)."""
    identifier: str
    title: str
    description: str
    category_id: str
    icon: str
    unlock_flags: str
    seconds_to_unlock: int
    sort_order: int

    requirements: list[dict[str, Any]]  # item + amount pairs
    unlock_dependencies: list[str]
    research_dependencies: list[str]
    crafting_recipe_unlocks: list[str]

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> ExplorationUnlock:
        return cls(
            identifier=data.get("identifier", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            category_id=data.get("categoryIdentifier", ""),
            icon=data.get("icon_identifier", ""),
            unlock_flags=data.get("unlockFlags", ""),
            seconds_to_unlock=int(data.get("secondsToUnlock", 0)),
            sort_order=int(data.get("sortOrderASC", 0)),
            requirements=data.get("requirements", []),
            unlock_dependencies=data.get("unlockDepedencies", []),
            research_dependencies=[
                d.get("researchTemplateIdentifier", "")
                for d in data.get("researchDepedencies", [])
                if isinstance(d, dict)
            ],
            crafting_recipe_unlocks=data.get("craftingRecipeUnlocks_identifier", []),
            _raw=data,
        )


@dataclass
class SkyPlatformUpgrade:
    """A sky platform (space station) upgrade."""
    identifier: str
    name: str
    description: str
    category_id: str
    icon: str
    flags: list[str]
    is_endless: bool
    sort_order: int

    power_requirement_mw: float
    power_increase_mw: float
    construction_drone_increase: int
    construction_speed_multiplier: float | None

    requirements: list[str]  # prerequisite upgrade identifiers
    research_requirements: list[str]
    costs: list[dict[str, Any]]  # item + amount pairs

    sector_unlocks: int
    trade_license_unlocks: int
    hangar_space_increase: int

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> SkyPlatformUpgrade:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category_id=data.get("category_identifier", ""),
            icon=data.get("icon_identifier", ""),
            flags=_parse_flags(data.get("flags", "")),
            is_endless=bool(data.get("isEndless", False)),
            sort_order=int(data.get("sortOrderASC", 0)),
            power_requirement_mw=float(data.get("powerRequirement_mw", 0)),
            power_increase_mw=float(data.get("powerIncrease_mw", 0)),
            construction_drone_increase=int(data.get("constructionDroneIncrease", 0)),
            construction_speed_multiplier=_parse_numeric_str(
                data.get("constructionSpeedMultiplier_str")
            ),
            requirements=data.get("requirements_array", []),
            research_requirements=data.get("research_requirements_array", []),
            costs=data.get("cost_array", []),
            sector_unlocks=int(data.get("sectorUnlocks", 0)),
            trade_license_unlocks=int(data.get("tradeLicenseUnlocks", 0)),
            hangar_space_increase=int(data.get("hangarSpaceIncrease", 0)),
            _raw=data,
        )


@dataclass
class Quest:
    """A quest / milestone."""
    identifier: str
    is_milestone: bool
    title: str
    conditions: list[dict[str, Any]]
    quest_dependencies: list[str]
    research_dependencies: list[str]

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Quest:
        return cls(
            identifier=data.get("identifier", ""),
            is_milestone=bool(data.get("isMilestoneQuest", False)),
            title=data.get("title", ""),
            conditions=data.get("conditions", []),
            quest_dependencies=data.get("dependencies_quests_identifier", []),
            research_dependencies=data.get("dependencies_research_identifier", []),
            _raw=data,
        )


@dataclass
class BlastFurnaceMode:
    """A blast furnace operating mode."""
    identifier: str
    name: str
    icon: str
    inputs: list[CraftingIO]
    elemental_outputs: list[ElementalIO]
    waste_gas: ElementalIO | None

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> BlastFurnaceMode:
        waste_raw = data.get("waste_gas_data", {})
        waste = None
        if waste_raw and waste_raw.get("identifier"):
            waste = ElementalIO(
                identifier=waste_raw["identifier"],
                amount=_parse_numeric_str(waste_raw.get("amount_str", "0")) or 0.0,
            )
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            icon=data.get("icon_identifier", ""),
            inputs=[CraftingIO.from_raw(d) for d in data.get("input_data", [])],
            elemental_outputs=[
                ElementalIO.from_raw(d) for d in data.get("output_data_elemental", [])
            ],
            waste_gas=waste,
            _raw=data,
        )


@dataclass
class Industry:
    """An industry type for the sales/trade system."""
    identifier: str
    name: str

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Industry:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            _raw=data,
        )


@dataclass
class CompanyRank:
    """A company rank level."""
    identifier: str
    name: str

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> CompanyRank:
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            _raw=data,
        )


@dataclass
class OreVein:
    """An ore vein template for deep mining."""
    identifier: str
    outer_layer_block: str
    mineable_block: str
    core_block: str
    spawn_chance: int
    mining_fluid_id: str
    mining_fluid_rate: float | None

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> OreVein:
        return cls(
            identifier=data.get("identifier", ""),
            outer_layer_block=data.get("outerLayerBlockType_identifier", ""),
            mineable_block=data.get("mineableBlockType_identifier", ""),
            core_block=data.get("coreBlockType_identifier", ""),
            spawn_chance=int(data.get("spawnChancePerOreChunk", 0)),
            mining_fluid_id=data.get("miningFluid_identifier", ""),
            mining_fluid_rate=_parse_numeric_str(
                data.get("requiredMiningFluid_literPerMinutePerMiner_str")
            ),
            _raw=data,
        )


@dataclass
class BuildableObjectConversionGroup:
    """Defines upgrade/conversion paths between building tiers."""
    identifier: str
    entries: list[str]

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> BuildableObjectConversionGroup:
        entries = data.get("entries", [])
        # entries may be list of dicts with 'identifier' or list of strings
        if entries and isinstance(entries[0], dict):
            entries = [e.get("identifier", "") for e in entries]
        return cls(
            identifier=data.get("identifier", ""),
            entries=entries,
            _raw=data,
        )


@dataclass
class InfoDatabaseEntry:
    """An in-game encyclopedia / help entry."""
    identifier: str
    category_id: str
    sidebar_text: str
    sort_order: int
    page_type: str
    is_unlocked_by_default: bool
    paragraphs: list[dict[str, Any]]

    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> InfoDatabaseEntry:
        return cls(
            identifier=data.get("identifier", ""),
            category_id=data.get("category_identifier", ""),
            sidebar_text=data.get("sidebarButtonText", ""),
            sort_order=int(data.get("sortOrderDESC", 0)),
            page_type=data.get("infoPageType", ""),
            is_unlocked_by_default=bool(data.get("isUnlockedByDefault", False)),
            paragraphs=data.get("paragraphs", []),
            _raw=data,
        )
