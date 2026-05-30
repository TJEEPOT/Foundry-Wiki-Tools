-- Module:RecipeTable
-- Renders recipe tables for items, elements, and buildings.
-- Usage:
--   {{#invoke:RecipeTable|main|id=IronIngot|mode=producing}}
--   {{#invoke:RecipeTable|building|id=Smelter}}

local p = {}

local data_cache = {}

local function load_data(module_name)
    if not data_cache[module_name] then
        data_cache[module_name] = mw.loadData(module_name)
    end
    return data_cache[module_name]
end

local function get_items()              return load_data('Module:Data/Items') end
local function get_elements()           return load_data('Module:Data/Elements') end
local function get_recipes()            return load_data('Module:Data/Recipes') end
local function get_recipe_index()       return load_data('Module:Data/RecipeIndex') end
local function get_building_recipes()   return load_data('Module:Data/BuildingRecipeIndex') end
local function get_buildings()          return load_data('Module:Data/Buildings') end
local function get_name_index()         return load_data('Module:Data/NameIndex') end
local function get_recipe_buildings()   return load_data('Module:Data/RecipeBuildingNames') end

-------------------------------------------------------------------------------
-- Helpers
-------------------------------------------------------------------------------

--- Resolve identifier to display name.
local function resolve_name(id)
    if not id or id == '' then return id end
    local items = get_items()
    if items[id] and items[id].name then return items[id].name end
    local elements = get_elements()
    if elements[id] and elements[id].name then return elements[id].name end
    local buildings = get_buildings()
    if buildings[id] and buildings[id].name then return buildings[id].name end
    return id
end

--- Formats a number with comma separators.
local function format_number(n)
    if not n then return '' end
    local formatted = tostring(n)
    local k
    while true do
        formatted, k = string.gsub(formatted, "^(-?%d+)(%d%d%d)", '%1,%2')
        if k == 0 then break end
    end
    return formatted
end

--- Creates an item link with quantity: "5x [[Iron Ingot]]"
local function format_item_qty(id, amount)
    local name = resolve_name(id)
    local qty = ''
    if amount and amount > 1 then
        qty = format_number(amount) .. 'x '
    elseif amount == 1 then
        qty = '1x '
    end
    return qty .. '[[' .. name .. ']]'
end

--- Formats a time duration in seconds.
local function format_time(seconds)
    if not seconds then return '?' end
    if seconds < 60 then
        return seconds .. 's'
    elseif seconds < 3600 then
        local m = math.floor(seconds / 60)
        local s = seconds % 60
        if s > 0 then
            return m .. 'm ' .. s .. 's'
        end
        return m .. 'm'
    else
        local h = math.floor(seconds / 3600)
        local m = math.floor((seconds % 3600) / 60)
        if m > 0 then
            return h .. 'h ' .. m .. 'm'
        end
        return h .. 'h'
    end
end

--- Renders the inputs column for a recipe.
local function format_inputs(recipe)
    local parts = {}
    if recipe.inputs then
        for _, inp in ipairs(recipe.inputs) do
            parts[#parts + 1] = format_item_qty(inp.identifier, inp.amount)
        end
    end
    if recipe.elemental_inputs then
        for _, inp in ipairs(recipe.elemental_inputs) do
            local name = resolve_name(inp.identifier)
            parts[#parts + 1] = format_number(inp.amount) .. 'L [[' .. name .. ']]'
        end
    end
    if #parts == 0 then return '—' end
    return table.concat(parts, '<br>')
end

--- Renders the outputs column for a recipe.
local function format_outputs(recipe)
    local parts = {}
    if recipe.outputs then
        for _, out in ipairs(recipe.outputs) do
            parts[#parts + 1] = format_item_qty(out.identifier, out.amount)
        end
    end
    if recipe.elemental_outputs then
        for _, out in ipairs(recipe.elemental_outputs) do
            local name = resolve_name(out.identifier)
            parts[#parts + 1] = format_number(out.amount) .. 'L [[' .. name .. ']]'
        end
    end
    if #parts == 0 then return '—' end
    return table.concat(parts, '<br>')
end

--- Resolves which building(s) can craft a recipe using the pre-computed
--- RecipeBuildingNames index (recipe_id -> list of building display names).
--- This avoids any iteration over mw.loadData() proxy tables.
local function find_buildings_for_recipe(recipe_id)
    local rb = get_recipe_buildings()
    local names = rb[recipe_id]
    if not names then return {} end

    local result = {}
    local i = 1
    while names[i] do
        result[#result + 1] = '[[' .. names[i] .. ' (Building)|' .. names[i] .. ']]'
        i = i + 1
    end
    table.sort(result)
    return result
end

--- Renders a full recipe table from a list of recipe identifiers.
local function render_recipe_table(recipe_ids, show_building)
    if not recipe_ids or #recipe_ids == 0 then
        return nil
    end

    local recipes = get_recipes()

    local tbl = mw.html.create('table')
        :addClass('recipe-table')
        :addClass('wikitable')
        :addClass('sortable')

    -- Header row
    local header = tbl:tag('tr')
    header:tag('th'):wikitext('Recipe')
    header:tag('th'):wikitext('Inputs')
    header:tag('th'):wikitext('Outputs')
    header:tag('th'):wikitext('Time')
    if show_building then
        header:tag('th'):wikitext('Building')
    end

    -- Data rows
    for _, rid in ipairs(recipe_ids) do
        local recipe = recipes[rid]
        if recipe then
            local tr = tbl:tag('tr')
            tr:tag('td'):wikitext(recipe.name or rid)
            tr:tag('td'):wikitext(format_inputs(recipe))
            tr:tag('td'):wikitext(format_outputs(recipe))
            tr:tag('td'):wikitext(format_time(recipe.time_seconds))
            if show_building then
                local bldgs = find_buildings_for_recipe(rid)
                tr:tag('td'):wikitext(#bldgs > 0 and table.concat(bldgs, ', ') or '—')
            end
        end
    end

    return tostring(tbl)
end

-------------------------------------------------------------------------------
-- p.main(frame) - Recipe table for an item or element
-------------------------------------------------------------------------------

function p.main(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">RecipeTable: no id specified</span>'
    end

    local mode = (args.mode or 'producing'):lower()
    local recipe_index = get_recipe_index()

    -- RecipeIndex structure: { outputs = { [id] = {rid, ...} }, inputs = { [id] = {rid, ...} } }
    local recipe_ids = {}

    if mode == 'producing' or mode == 'all' then
        local producing = recipe_index.outputs and recipe_index.outputs[id]
        if producing then
            for _, rid in ipairs(producing) do
                recipe_ids[#recipe_ids + 1] = rid
            end
        end
    end

    if mode == 'consuming' or mode == 'all' then
        local consuming = recipe_index.inputs and recipe_index.inputs[id]
        if consuming then
            for _, rid in ipairs(consuming) do
                recipe_ids[#recipe_ids + 1] = rid
            end
        end
    end

    if #recipe_ids == 0 then
        return ''
    end

    local result = render_recipe_table(recipe_ids, true)
    return result or ''
end

-------------------------------------------------------------------------------
-- p.building(frame) - All recipes craftable in a building
-------------------------------------------------------------------------------

function p.building(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">RecipeTable: no building id specified</span>'
    end

    local building_recipes = get_building_recipes()
    local recipe_ids = building_recipes[id]

    if not recipe_ids or #recipe_ids == 0 then
        return ''
    end

    local result = render_recipe_table(recipe_ids, false)
    return result or ''
end

-------------------------------------------------------------------------------
-- p.recipe(frame) - Single recipe by recipe ID
-------------------------------------------------------------------------------

function p.recipe(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">RecipeTable: no recipe id specified</span>'
    end

    local result = render_recipe_table({id}, true)
    return result or ''
end

return p
