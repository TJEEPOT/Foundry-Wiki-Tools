-- Module:RecipeCard
-- Renders detailed recipe cards with per-building crafting rates.
-- Design B: recipe summary card (inputs → outputs) + per-building rate cards
-- with abbr tooltips for input/output rates.
--
-- Usage:
--   {{#invoke:RecipeCard|main|id=IronIngot|mode=producing}}
--   {{#invoke:RecipeCard|building|id=Smelter}}
--   {{#invoke:RecipeCard|recipe|id=_base_conveyor_i}}

local p = {}

local data_cache = {}

local function load_data(module_name)
    if not data_cache[module_name] then
        data_cache[module_name] = mw.loadData(module_name)
    end
    return data_cache[module_name]
end

local function get_items()            return load_data('Module:Data/Items') end
local function get_elements()         return load_data('Module:Data/Elements') end
local function get_recipes()          return load_data('Module:Data/Recipes') end
local function get_recipe_index()     return load_data('Module:Data/RecipeIndex') end
local function get_building_recipes() return load_data('Module:Data/BuildingRecipeIndex') end
local function get_buildings()        return load_data('Module:Data/Buildings') end
local function get_crafting_data()    return load_data('Module:Data/RecipeCraftingData') end

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

--- Formats a time duration in seconds to a human-readable string.
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

--- Round a number to avoid floating point display artefacts.
--- Shows integers when possible, otherwise up to 2 decimal places.
local function round_rate(n)
    if n == math.floor(n) then
        return format_number(math.floor(n))
    end
    -- Round to 2 decimal places
    local rounded = math.floor(n * 100 + 0.5) / 100
    if rounded == math.floor(rounded) then
        return format_number(math.floor(rounded))
    end
    return string.format('%.2f', rounded)
end

--- Creates an item link: "[[Iron Ingot]]"
local function item_link(id)
    local name = resolve_name(id)
    return '[[' .. name .. ']]'
end

--- Creates a building link: "[[Smelter (Small) (Building)|Smelter (Small)]]"
local function building_link(name)
    return '[[' .. name .. ' (Building)|' .. name .. ']]'
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

--- Collects all inputs for a recipe into a flat list of {name, amount, unit}.
--- Items have unit = '' and elements have unit = 'L'.
local function collect_io_items(recipe, direction)
    local items_key = direction == 'input' and 'inputs' or 'outputs'
    local elements_key = direction == 'input' and 'elemental_inputs' or 'elemental_outputs'
    local result = {}

    local item_list = recipe[items_key]
    if item_list then
        for _, entry in ipairs(item_list) do
            result[#result + 1] = {
                name = resolve_name(entry.identifier),
                id = entry.identifier,
                amount = entry.amount,
                unit = ''
            }
        end
    end

    local elem_list = recipe[elements_key]
    if elem_list then
        for _, entry in ipairs(elem_list) do
            result[#result + 1] = {
                name = resolve_name(entry.identifier),
                id = entry.identifier,
                amount = entry.amount,
                unit = 'L'
            }
        end
    end

    return result
end

-------------------------------------------------------------------------------
-- Recipe card rendering
-------------------------------------------------------------------------------

--- Renders a single recipe card (Design B layout).
local function render_recipe_card(recipe_id)
    local recipes = get_recipes()
    local recipe = recipes[recipe_id]
    if not recipe then return nil end

    local crafting_data = get_crafting_data()
    local cd = crafting_data[recipe_id]

    local base_time = recipe.time_seconds
    local inputs = collect_io_items(recipe, 'input')
    local outputs = collect_io_items(recipe, 'output')

    -- TemplateStyles
    local styles = mw.getCurrentFrame():extensionTag(
        'templatestyles', '', { src = 'Template:TemplateStyles/RecipeCard.css' }
    )

    -- Outer wrapper
    local card = mw.html.create('div')
        :addClass('recipe-card')

    -- === Recipe summary section ===
    local summary = card:tag('div'):addClass('recipe-card-summary')

    -- Recipe name header
    summary:tag('div')
        :addClass('recipe-card-header')
        :wikitext(recipe.name or recipe_id)

    -- Inputs → Outputs flow
    local flow = summary:tag('div'):addClass('recipe-card-flow')

    -- Inputs column
    local inp_col = flow:tag('div'):addClass('recipe-card-io')
    inp_col:tag('div'):addClass('recipe-card-io-label'):wikitext('Inputs')
    for _, inp in ipairs(inputs) do
        local qty_str
        if inp.unit == 'L' then
            qty_str = format_number(inp.amount) .. 'L ' .. '[[' .. inp.name .. ']]'
        else
            qty_str = format_item_qty(inp.id, inp.amount)
        end
        inp_col:tag('div'):addClass('recipe-card-io-item'):wikitext(qty_str)
    end

    -- Arrow
    flow:tag('div')
        :addClass('recipe-card-arrow')
        :wikitext('→')

    -- Outputs column
    local out_col = flow:tag('div'):addClass('recipe-card-io')
    out_col:tag('div'):addClass('recipe-card-io-label'):wikitext('Outputs')
    for _, out in ipairs(outputs) do
        local qty_str
        if out.unit == 'L' then
            qty_str = format_number(out.amount) .. 'L ' .. '[[' .. out.name .. ']]'
        else
            qty_str = format_item_qty(out.id, out.amount)
        end
        out_col:tag('div'):addClass('recipe-card-io-item'):wikitext(qty_str)
    end

    -- Base time footer
    summary:tag('div')
        :addClass('recipe-card-basetime')
        :wikitext('Base craft time: ' .. format_time(base_time))

    -- === Building rate cards ===
    if cd and cd.n and cd.n > 0 then
        local rates_section = card:tag('div'):addClass('recipe-card-rates')

        for i = 1, cd.n do
            local bname = cd['n' .. i]
            local btime = cd['t' .. i]
            if not bname or not btime then break end

            local rate_card = rates_section:tag('div'):addClass('recipe-rate-card')

            -- Building name (linked for machines, plain for Hand)
            local name_div = rate_card:tag('div'):addClass('recipe-rate-name')
            if bname == 'Hand' then
                name_div:wikitext(bname)
            else
                name_div:wikitext(building_link(bname))
            end

            -- Craft time
            rate_card:tag('div')
                :addClass('recipe-rate-time')
                :wikitext(format_time(btime))
            rate_card:tag('div')
                :addClass('recipe-rate-time-label')
                :wikitext('per craft')

            -- Input rates with abbr tooltips
            if #inputs > 0 then
                local in_rate_div = rate_card:tag('div'):addClass('recipe-rate-row')
                in_rate_div:tag('span')
                    :addClass('recipe-rate-direction')
                    :wikitext('In:')
                local in_vals = {}
                for _, inp in ipairs(inputs) do
                    local rate = (inp.amount / btime) * 60
                    local rate_str = round_rate(rate)
                    in_vals[#in_vals + 1] = tostring(
                        mw.html.create('abbr')
                            :attr('title', inp.name)
                            :wikitext(rate_str .. '/m')
                    )
                end
                in_rate_div:tag('span')
                    :addClass('recipe-rate-values')
                    :wikitext(table.concat(in_vals, ', '))
            end

            -- Output rates with abbr tooltips
            if #outputs > 0 then
                local out_rate_div = rate_card:tag('div'):addClass('recipe-rate-row')
                out_rate_div:tag('span')
                    :addClass('recipe-rate-direction')
                    :wikitext('Out:')
                local out_vals = {}
                for _, out in ipairs(outputs) do
                    local rate = (out.amount / btime) * 60
                    local rate_str = round_rate(rate)
                    out_vals[#out_vals + 1] = tostring(
                        mw.html.create('abbr')
                            :attr('title', out.name)
                            :wikitext(rate_str .. '/m')
                    )
                end
                out_rate_div:tag('span')
                    :addClass('recipe-rate-values')
                    :wikitext(table.concat(out_vals, ', '))
            end
        end
    end

    return styles .. tostring(card)
end

-------------------------------------------------------------------------------
-- p.recipe(frame) - Single recipe card by recipe ID
-------------------------------------------------------------------------------

function p.recipe(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">RecipeCard: no recipe id specified</span>'
    end

    local result = render_recipe_card(id)
    return result or ''
end

-------------------------------------------------------------------------------
-- p.main(frame) - Recipe cards for an item or element (producing/consuming)
-------------------------------------------------------------------------------

function p.main(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">RecipeCard: no id specified</span>'
    end

    local mode = (args.mode or 'producing'):lower()
    local recipe_index = get_recipe_index()

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

    local parts = {}
    for _, rid in ipairs(recipe_ids) do
        local card = render_recipe_card(rid)
        if card then
            parts[#parts + 1] = card
        end
    end

    return table.concat(parts, '\n')
end

-------------------------------------------------------------------------------
-- p.building(frame) - All recipe cards for a building
-------------------------------------------------------------------------------

function p.building(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">RecipeCard: no building id specified</span>'
    end

    local building_recipes = get_building_recipes()
    local recipe_ids = building_recipes[id]

    if not recipe_ids or #recipe_ids == 0 then
        return ''
    end

    local parts = {}
    local i = 1
    while recipe_ids[i] do
        local card = render_recipe_card(recipe_ids[i])
        if card then
            parts[#parts + 1] = card
        end
        i = i + 1
    end

    return table.concat(parts, '\n')
end

return p
