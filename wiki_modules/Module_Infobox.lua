-- Module:Infobox
-- Renders HTML infoboxes for Foundry wiki entities.
-- Loads data from auto-generated Lua data modules and produces styled tables.

local p = {}

-------------------------------------------------------------------------------
-- Data module lazy-loading
-------------------------------------------------------------------------------

local data_cache = {}

local function load_data(module_name)
    if not data_cache[module_name] then
        data_cache[module_name] = mw.loadData(module_name)
    end
    return data_cache[module_name]
end

local function get_items()         return load_data('Module:Data/Items') end
local function get_buildings()     return load_data('Module:Data/Buildings') end
local function get_research()      return load_data('Module:Data/Research') end
local function get_elements()      return load_data('Module:Data/Elements') end
local function get_exploration()   return load_data('Module:Data/ExplorationUnlocks') end
local function get_sky_platform()  return load_data('Module:Data/SkyPlatformUpgrades') end
local function get_item_building() return load_data('Module:Data/ItemBuildingIndex') end
local function get_name_index()    return load_data('Module:Data/NameIndex') end
local function get_categories()    return load_data('Module:Data/ItemCategories') end
local function get_upgrade_paths() return load_data('Module:Data/UpgradePaths') end

-------------------------------------------------------------------------------
-- Helper functions
-------------------------------------------------------------------------------

--- Creates a wikilink [[name]]
local function make_link(name)
    if not name then return nil end
    return '[[' .. name .. ']]'
end

--- Looks up an item by identifier and returns a wikilink to its display name.
--- Falls back to the raw identifier if not found.
local function item_link(id)
    if not id then return nil end
    local items = get_items()
    local item = items[id]
    if item and item.name then
        return '[[' .. item.name .. ']]'
    end
    -- Fallback: try buildings, research, elements for generic name resolution
    local buildings = get_buildings()
    if buildings[id] and buildings[id].name then
        return '[[' .. buildings[id].name .. ']]'
    end
    local research = get_research()
    if research[id] and research[id].name then
        return '[[' .. research[id].name .. ']]'
    end
    local elements = get_elements()
    if elements[id] and elements[id].name then
        return '[[' .. elements[id].name .. ']]'
    end
    return id
end

--- Resolves any entity identifier to its display name (without link markup).
local function resolve_name(id)
    if not id then return nil end
    local items = get_items()
    if items[id] and items[id].name then return items[id].name end
    local buildings = get_buildings()
    if buildings[id] and buildings[id].name then return buildings[id].name end
    local research = get_research()
    if research[id] and research[id].name then return research[id].name end
    local elements = get_elements()
    if elements[id] and elements[id].name then return elements[id].name end
    local exploration = get_exploration()
    if exploration[id] and exploration[id].title then return exploration[id].title end
    local sky = get_sky_platform()
    if sky[id] and sky[id].name then return sky[id].name end
    return id
end

--- Formats a number with comma separators (e.g. 1234567 -> "1,234,567")
local function format_number(n)
    if not n then return nil end
    local formatted = tostring(n)
    local k
    while true do
        formatted, k = string.gsub(formatted, "^(-?%d+)(%d%d%d)", '%1,%2')
        if k == 0 then break end
    end
    return formatted
end

--- Adds a standard data row to the infobox table if value is truthy.
local function render_row(tbl, label, value)
    if not value or value == '' then return end
    local tr = tbl:tag('tr')
    tr:tag('th'):wikitext(label)
    tr:tag('td'):wikitext(tostring(value))
end

--- Adds a section header row spanning both columns.
local function render_section(tbl, title)
    local tr = tbl:tag('tr')
    tr:tag('td')
        :attr('colspan', '2')
        :addClass('infobox-section')
        :wikitext(title)
end

--- Computes the dependency-depth tier for a research entry (0-indexed).
--- Returns 0 if no prerequisites, or 1 + max(dependency tiers) otherwise.
--- This matches the navbox tier logic: add 1 when displaying to get "Tier 1", "Tier 2", etc.
--- Pass the full research data module so dependencies can be looked up recursively.
local function compute_tier(res_id, research_data, visited)
    if not res_id then return 0 end
    visited = visited or {}
    if visited[res_id] then return 0 end  -- cycle guard
    visited[res_id] = true

    local res = research_data[res_id]
    if not res or not res.dependencies or not res.dependencies[1] then
        return 0
    end

    local max_dep = 0
    for _, dep_id in ipairs(res.dependencies) do
        local dep_tier = compute_tier(dep_id, research_data, visited)
        if dep_tier > max_dep then
            max_dep = dep_tier
        end
    end
    return max_dep + 1
end

--- Maps pipe_content_type to a human-readable state name.
local function element_state(pipe_content_type)
    if pipe_content_type == 1 then
        return 'Gas'
    elseif pipe_content_type == 2 then
        return 'Liquid'
    end
    return nil
end

--- Normalise an image parameter to include the wiki Item_ prefix.
-- Pages pass  |image=Assembler I.png  but files are stored as
-- File:Item_Assembler I.png, so we prepend Item_ when absent.
local function normalise_image(img)
    if not img or img == '' then return img end
    if img:sub(1, 5) == 'Item_' then return img end
    return 'Item_' .. img
end

--- Creates the base infobox table with TemplateStyles applied.
local function create_infobox(frame, caption)
    local styles = frame:extensionTag({
        name = 'templatestyles',
        args = { src = 'Template:Infobox/styles.css' }
    })
    local tbl = mw.html.create('table')
        :addClass('foundry-infobox')
        :addClass('wikitable')
    tbl:tag('caption'):wikitext(caption)
    return styles, tbl
end

--- Adds a description row (italic, spanning both columns).
local function render_description(tbl, description)
    if not description or description == '' then return end
    local tr = tbl:tag('tr')
    tr:tag('td')
        :attr('colspan', '2')
        :addClass('infobox-description')
        :wikitext(description)
end

--- Formats a list of cost entries ({identifier, amount}) as wikitext lines.
local function format_costs(costs)
    if not costs or not costs[1] then return nil end
    local lines = {}
    for _, cost in ipairs(costs) do
        local id = cost.identifier
        local amount = cost.amount
        local link = item_link(id)
        lines[#lines + 1] = format_number(amount) .. 'x ' .. link
    end
    return table.concat(lines, '<br>')
end

--- Converts a creative_mode_category identifier to a display name.
--- e.g. "_base_cmct_robots_and_bots" -> "Robots and Bots"
local function format_cmc_name(cmc_id)
    if not cmc_id or cmc_id == '' then return nil end
    -- Strip prefix
    local name = cmc_id:gsub('^_base_cmct_', '')
    -- Underscores to spaces, title-case each word
    name = name:gsub('_', ' '):gsub('(%a)([%w]*)', function(a, b)
        return a:upper() .. b
    end)
    -- Fix "And" -> "and" for natural English
    name = name:gsub(' And ', ' and ')
    return name
end

--- Returns an error message wrapped in an HTML span.
local function error_msg(msg)
    return '<span class="error">' .. msg .. '</span>'
end

-------------------------------------------------------------------------------
-- p.item(frame)
-------------------------------------------------------------------------------

function p.item(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no id specified')
    end

    local items = get_items()
    local data = items[id]
    if not data then
        return error_msg('Module:Infobox error: item "' .. id .. '" not found')
    end

    local name = data.name or id
    local styles, tbl = create_infobox(frame, name)

    -- Image (manual param from template call)
    local image = frame.args.image
    if image and image ~= '' then
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :addClass('infobox-image')
            :wikitext('[[File:' .. normalise_image(image) .. '|250x250px]]')
    end

    -- Description
    render_description(tbl, data.description)

    -- Trade Category (from category_id -> ItemCategories lookup)
    local trade_category_name = nil
    if data.category_id then
        local cats = get_categories()
        local cat = cats[data.category_id]
        if cat then
            trade_category_name = cat.name
            render_row(tbl, 'Trade Category', make_link(trade_category_name))
        end
    end

    -- Creative Category (from creative_mode_category identifier)
    local creative_category_name = format_cmc_name(data.creative_mode_category)
    if creative_category_name then
        render_row(tbl, 'Creative Category', creative_category_name)
    end

    -- Building (linked buildable object — always link to "Name (Building)" form,
    -- which either is the real page or a redirect to the clean title)
    if data.buildable_object_id and data.buildable_object_id ~= '' then
        local building_name = resolve_name(data.buildable_object_id)
        local link_target = building_name .. ' (Building)'
        render_row(tbl, 'Building', '[[' .. link_target .. '|' .. building_name .. ']]')
    end

    -- Stack Size
    render_row(tbl, 'Stack Size', format_number(data.stack_size))

    -- Weight
    if data.weight_kg then
        render_row(tbl, 'Weight', format_number(data.weight_kg) .. ' kg')
    elseif data.weight_g then
        render_row(tbl, 'Weight', format_number(data.weight_g) .. ' g')
    end

    -- Flags (excluding BUILDABLE_OBJECT)
    if data.flags then
        local display_flags = {}
        for _, flag in ipairs(data.flags) do
            if flag ~= 'BUILDABLE_OBJECT' then
                -- Convert FLAG_NAME to Title Case: "SALES_ITEM" -> "Sales Item"
                local pretty = flag:lower():gsub('_', ' '):gsub('(%a)([%w]*)', function(a, b)
                    return a:upper() .. b
                end)
                display_flags[#display_flags + 1] = pretty
            end
        end
        if #display_flags > 0 then
            render_row(tbl, 'Flags', table.concat(display_flags, '<br>'))
        end
    end

    -- Trade section
    if data.can_be_traded then
        render_section(tbl, 'Trade')
        render_row(tbl, 'Buy Price', data.buy_price and (format_number(data.buy_price) .. ' [[Firmarlite Bar (Item)|Firmarlite Bar]]'))
        render_row(tbl, 'Sell Price', data.sell_price and (format_number(data.sell_price) .. ' [[Firmarlite Bar (Item)|Firmarlite Bar]]'))
    end

    -- Categories
    local wiki_cats = '[[Category:Items]]'
    if trade_category_name then
        wiki_cats = wiki_cats .. '[[Category:' .. trade_category_name .. ']]'
    end
    if creative_category_name then
        wiki_cats = wiki_cats .. '[[Category:' .. creative_category_name .. ']]'
    end

    return styles .. tostring(tbl) .. wiki_cats
end

-------------------------------------------------------------------------------
-- p.building(frame)
-------------------------------------------------------------------------------

function p.building(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no id specified')
    end

    local buildings = get_buildings()
    local data = buildings[id]
    if not data then
        return error_msg('Module:Infobox error: building "' .. id .. '" not found')
    end

    -- Resolve display name
    local name = data.name_override or data.name or id

    local styles, tbl = create_infobox(frame, name)

    -- Image (manual param from template call)
    local image = frame.args.image
    if image and image ~= '' then
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :addClass('infobox-image')
            :wikitext('[[File:' .. normalise_image(image) .. '|250x250px]]')
    end

    -- Description
    render_description(tbl, data.description)

    -- Type
    render_row(tbl, 'Type', data.type)

    -- Size
    if data.size_x and data.size_y and data.size_z then
        -- size_y is vertical height; render as X × Z × Y (width × depth × height)
        local size_str = data.size_x .. 'x' .. data.size_z .. 'x' .. data.size_y
        render_row(tbl, 'Size', size_str)
    end

    -- Power consumption (consumers)
    if data.energy_consumption_kw and data.energy_consumption_kw > 0 then
        local voltage
        if data.grid_type == 'LowVoltage' then
            voltage = 'Low Voltage'
        elseif data.grid_type == 'HighVoltage' then
            voltage = 'High Voltage'
        end
        local power_str = format_number(data.energy_consumption_kw) .. ' kW'
        if voltage then
            power_str = power_str .. ' (' .. voltage .. ')'
        end
        render_row(tbl, 'Power', power_str)
    end

    -- Power generation (producers)
    if data.power_generation_kw and data.power_generation_kw > 0 then
        local voltage
        if data.grid_type == 'LowVoltage' then
            voltage = 'Low Voltage'
        elseif data.grid_type == 'HighVoltage' then
            voltage = 'High Voltage'
        end
        local gen_str
        if data.power_generation_min_kw and data.power_generation_min_kw > 0 then
            -- Solar: show range
            gen_str = format_number(data.power_generation_min_kw) .. ' – '
                   .. format_number(data.power_generation_kw) .. ' kW'
        else
            gen_str = format_number(data.power_generation_kw) .. ' kW'
        end
        if voltage then
            gen_str = gen_str .. ' (' .. voltage .. ')'
        end
        render_row(tbl, 'Max Generation', gen_str)
    end

    -- Transformer rate
    if data.transformer_rate_kw and data.transformer_rate_kw > 0 then
        local voltage
        if data.grid_type == 'LowVoltage' then
            voltage = 'Low Voltage'
        elseif data.grid_type == 'HighVoltage' then
            voltage = 'High Voltage'
        end
        local rate_str = format_number(data.transformer_rate_kw) .. ' kW'
        if voltage then
            rate_str = rate_str .. ' (' .. voltage .. ')'
        end
        render_row(tbl, 'Transfer Rate', rate_str)
    end

    -- Energy capacity (batteries)
    if data.capacity_mj and data.capacity_mj > 0 then
        render_row(tbl, 'Capacity', format_number(data.capacity_mj) .. ' MJ')
    end

    -- Module Slots (workstation robot slots, only if > 0)
    if data.workstation_robot_slots and data.workstation_robot_slots > 0 then
        render_row(tbl, 'Module Slots', data.workstation_robot_slots)
    end

    -- Conveyor Slots
    if data.conveyor_slots_in or data.conveyor_slots_out then
        local parts = {}
        if data.conveyor_slots_in and data.conveyor_slots_in > 0 then
            parts[#parts + 1] = 'In: ' .. data.conveyor_slots_in
        end
        if data.conveyor_slots_out and data.conveyor_slots_out > 0 then
            parts[#parts + 1] = 'Out: ' .. data.conveyor_slots_out
        end
        if #parts > 0 then
            render_row(tbl, 'Conveyor Slots', table.concat(parts, ', '))
        end
    end

    -- Pipe Slots
    if data.pipe_slots_in or data.pipe_slots_out then
        local parts = {}
        if data.pipe_slots_in and data.pipe_slots_in > 0 then
            parts[#parts + 1] = 'In: ' .. data.pipe_slots_in
        end
        if data.pipe_slots_out and data.pipe_slots_out > 0 then
            parts[#parts + 1] = 'Out: ' .. data.pipe_slots_out
        end
        if #parts > 0 then
            render_row(tbl, 'Pipe Slots', table.concat(parts, ', '))
        end
    end

    -- Walkway connection (only shown when true, since most buildings don't have it)
    if data.has_walkways then
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :addClass('infobox-walkway')
            :wikitext('Connects to [[Walkway|walkway]]')
    end

    -- Recipe Tags
    if data.producer_recipe_tags and data.producer_recipe_tags[1] then
        render_row(tbl, 'Recipe Tags', table.concat(data.producer_recipe_tags, ', '))
    end

    -- Upgrade Path
    local upgrade_paths = get_upgrade_paths()
    local path = upgrade_paths[id]
    if path and path.n and path.n >= 2 then
        local parts = {}
        for i = 1, path.n do
            local bname = path['n' .. i]
            if not bname then break end
            if bname == name then
                -- Bold the current building, no link
                parts[#parts + 1] = "'''" .. bname .. "'''"
            else
                parts[#parts + 1] = '[[' .. bname .. ' (Building)|' .. bname .. ']]'
            end
        end
        render_row(tbl, 'Upgrade Path', table.concat(parts, ' → '))
    end

    -- Categories
    local wiki_cats = '[[Category:Buildings]]'
    if data.type then
        wiki_cats = wiki_cats .. '[[Category:' .. data.type .. ' buildings]]'
    end

    return styles .. tostring(tbl) .. wiki_cats
end

-------------------------------------------------------------------------------
-- p.research(frame)
-------------------------------------------------------------------------------

function p.research(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no id specified')
    end

    local research = get_research()
    local data = research[id]
    if not data then
        return error_msg('Module:Infobox error: research "' .. id .. '" not found')
    end

    local name = data.name or id
    local styles, tbl = create_infobox(frame, name)

    -- Image (manual param from template call)
    local image = frame.args.image
    if image and image ~= '' then
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :addClass('infobox-image')
            :wikitext('[[File:' .. normalise_image(image) .. '|250x250px]]')
    end

    -- Description
    render_description(tbl, data.description)

    -- Tier (dependency-depth, 1-indexed to match navbox display)
    local tier = compute_tier(id, research) + 1
    render_row(tbl, 'Tier', tostring(tier))

    -- Cost (science packs with quantities, one per line)
    if data.costs and data.costs[1] then
        local cost_lines = {}
        local min_amount = nil
        for _, cost in ipairs(data.costs) do
            local link = item_link(cost.identifier)
            cost_lines[#cost_lines + 1] = format_number(cost.amount) .. '× ' .. link
            if not min_amount or cost.amount < min_amount then
                min_amount = cost.amount
            end
        end
        render_row(tbl, 'Cost', table.concat(cost_lines, '<br>'))

        -- Total Time: seconds_per_science_item × min_amount, formatted as Xh Xm Xs
        if data.seconds_per_science_item and min_amount then
            local total_sec = data.seconds_per_science_item * min_amount
            local parts = {}
            if total_sec >= 3600 then
                local h = math.floor(total_sec / 3600)
                total_sec = total_sec - h * 3600
                parts[#parts + 1] = h .. 'h'
            end
            if total_sec >= 60 then
                local m = math.floor(total_sec / 60)
                total_sec = total_sec - m * 60
                parts[#parts + 1] = m .. 'm'
            end
            if total_sec > 0 then
                parts[#parts + 1] = total_sec .. 's'
            end
            render_row(tbl, 'Total Time', table.concat(parts, ' ') .. ' with a single [[Research Server (Building)|Research Server]]')
        end
    end

    -- Prerequisites (moved from page body to infobox)
    if data.dependencies and data.dependencies[1] then
        local lines = {}
        for _, dep_id in ipairs(data.dependencies) do
            local dep = research[dep_id]
            local dep_name = dep and dep.name or dep_id
            lines[#lines + 1] = '[[' .. dep_name .. ' (Research)|' .. dep_name .. ']]'
        end
        render_row(tbl, 'Prerequisites', table.concat(lines, '<br>'))
    end

    -- Categories
    local wiki_cats = '[[Category:Research]]'
    wiki_cats = wiki_cats .. '[[Category:Tier ' .. tier .. ' research]]'

    return styles .. tostring(tbl) .. wiki_cats
end

-------------------------------------------------------------------------------
-- p.element(frame)
-------------------------------------------------------------------------------

function p.element(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no id specified')
    end

    local elements = get_elements()
    local data = elements[id]
    if not data then
        return error_msg('Module:Infobox error: element "' .. id .. '" not found')
    end

    local name = data.name or id
    local styles, tbl = create_infobox(frame, name)

    -- Image (manual param from template call)
    local image = frame.args.image
    if image and image ~= '' then
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :addClass('infobox-image')
            :wikitext('[[File:' .. normalise_image(image) .. '|250x250px]]')
    end

    -- Description
    render_description(tbl, data.description)

    -- State (derived from pipe_content_type)
    local state = element_state(data.pipe_content_type)
    render_row(tbl, 'State', state)

    -- Pipe Color — small swatch box + hex value
    if data.color and data.color ~= '' then
        local swatch = '<span style="display:inline-block;width:1em;height:1em;'
            .. 'background-color:' .. data.color .. ';border:1px solid #888;'
            .. 'vertical-align:middle;margin-right:0.4em;border-radius:2px;"></span>'
            .. data.color
        render_row(tbl, 'Pipe Color', swatch)
    end

    -- Categories
    local wiki_cats = '[[Category:Elements]]'

    return styles .. tostring(tbl) .. wiki_cats
end

-------------------------------------------------------------------------------
-- p.exploration_unlock(frame)
-------------------------------------------------------------------------------

function p.exploration_unlock(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no id specified')
    end

    local exploration = get_exploration()
    local data = exploration[id]
    if not data then
        return error_msg('Module:Infobox error: exploration unlock "' .. id .. '" not found')
    end

    local name = data.title or id
    local styles, tbl = create_infobox(frame, name)

    -- Image (manual param from template call)
    local image = frame.args.image
    if image and image ~= '' then
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :addClass('infobox-image')
            :wikitext('[[File:' .. normalise_image(image) .. '|250x250px]]')
    end

    -- Category (derived from category_id; strip _base_ prefix and title-case)
    if data.category_id and data.category_id ~= '' then
        local cat = data.category_id:gsub('^_base_', ''):gsub('_', ' ')
        cat = cat:gsub('(%a)([%w]*)', function(a, b) return a:upper() .. b end)
        render_row(tbl, 'Category', cat)
    end

    -- Unlock Time
    if data.seconds_to_unlock then
        render_row(tbl, 'Unlock Time', data.seconds_to_unlock .. 's')
    end

    -- Requirements section (items needed)
    if data.requirements and data.requirements[1] then
        render_section(tbl, 'Requirements')
        local lines = {}
        for _, req in ipairs(data.requirements) do
            local req_id = req.itemTemplateIdentifier
            local amount = req.amount
            local link = item_link(req_id)
            lines[#lines + 1] = format_number(amount) .. 'x ' .. link
        end
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :wikitext(table.concat(lines, '<br>'))
    end

    -- Prerequisites section — link to *(Exploration Unlock) page variant
    if data.unlock_dependencies and data.unlock_dependencies[1] then
        render_section(tbl, 'Prerequisites')
        local lines = {}
        for _, dep in ipairs(data.unlock_dependencies) do
            local dep_id = dep.explorationUnlockTemplateIdentifier
            local dep_data = exploration[dep_id]
            local dep_name = dep_data and dep_data.title or dep_id
            lines[#lines + 1] = '[[' .. dep_name .. ' (Exploration Unlock)|' .. dep_name .. ']]'
        end
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :wikitext(table.concat(lines, '<br>'))
    end

    -- Research Required
    if data.research_dependencies and data.research_dependencies[1] then
        local research = get_research()
        local lines = {}
        for _, res_id in ipairs(data.research_dependencies) do
            local res = research[res_id]
            local res_name = res and res.name or res_id
            lines[#lines + 1] = make_link(res_name)
        end
        render_row(tbl, 'Research Required', table.concat(lines, '<br>'))
    end

    -- Categories
    local wiki_cats = '[[Category:Exploration Unlocks]]'

    return styles .. tostring(tbl) .. wiki_cats
end

-------------------------------------------------------------------------------
-- p.sky_platform(frame)
-------------------------------------------------------------------------------

function p.sky_platform(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no id specified')
    end

    local sky = get_sky_platform()
    local data = sky[id]
    if not data then
        return error_msg('Module:Infobox error: sky platform upgrade "' .. id .. '" not found')
    end

    local name = data.name or id
    local image = frame.args.image or ''
    local styles, tbl = create_infobox(frame, name, image)

    -- Category
    if data.category_id and data.category_id ~= '' then
        local cat = data.category_id:gsub('^_base_', ''):gsub('_', ' ')
        cat = cat:gsub('(%a)([%w]*)', function(a, b) return a:upper() .. b end)
        cat = cat:gsub('Rd ', 'R&D ')
        render_row(tbl, 'Category', cat)
    end

    -- Power Required
    if data.power_requirement_mw and data.power_requirement_mw > 0 then
        render_row(tbl, 'Power Required', format_number(data.power_requirement_mw) .. ' MW')
    end

    -- Costs section
    if data.costs and data.costs[1] then
        render_section(tbl, 'Costs')
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :wikitext(format_costs(data.costs))
    end

    -- Prerequisites section (other sky platform upgrades)
    if data.requirements and data.requirements[1] then
        render_section(tbl, 'Prerequisites')
        local lines = {}
        for _, req_id in ipairs(data.requirements) do
            local req_data = sky[req_id]
            local req_name = req_data and req_data.name or req_id
            lines[#lines + 1] = make_link(req_name)
        end
        local tr = tbl:tag('tr')
        tr:tag('td')
            :attr('colspan', '2')
            :wikitext(table.concat(lines, '<br>'))
    end

    -- Research Required
    if data.research_requirements and data.research_requirements[1] then
        local research = get_research()
        local lines = {}
        for _, res_id in ipairs(data.research_requirements) do
            local res = research[res_id]
            local res_name = res and res.name or res_id
            lines[#lines + 1] = make_link(res_name)
        end
        render_row(tbl, 'Research Required', table.concat(lines, '<br>'))
    end

    -- Effects section
    local effects = {}
    if data.power_increase_mw and data.power_increase_mw > 0 then
        effects[#effects + 1] = { 'Power Increase', format_number(data.power_increase_mw) .. ' MW' }
    end
    if data.construction_speed_multiplier and data.construction_speed_multiplier > 0 then
        effects[#effects + 1] = { 'Build Speed', data.construction_speed_multiplier .. 'x' }
    end
    if data.sector_unlocks and data.sector_unlocks > 0 then
        effects[#effects + 1] = { 'Sectors', '+' .. format_number(data.sector_unlocks) }
    end
    if data.trade_license_unlocks and data.trade_license_unlocks > 0 then
        effects[#effects + 1] = { 'Trade Licenses', '+' .. format_number(data.trade_license_unlocks) }
    end
    if data.hangar_space_increase and data.hangar_space_increase > 0 then
        effects[#effects + 1] = { 'Hangar Space', '+' .. format_number(data.hangar_space_increase) }
    end

    if #effects > 0 then
        render_section(tbl, 'Effects')
        for _, eff in ipairs(effects) do
            render_row(tbl, eff[1], eff[2])
        end
    end

    -- Categories
    local wiki_cats = '[[Category:Sky Platform Upgrades]]'
    if data.is_endless then
        wiki_cats = wiki_cats .. '[[Category:Endless Upgrades]]'
    end

    return styles .. tostring(tbl) .. wiki_cats
end

-------------------------------------------------------------------------------
-- p.research_card(frame)
-- Compact research summary card for embedding in item/building pages.
-------------------------------------------------------------------------------

function p.research_card(frame)
    local id = frame.args.id or frame.args[1]
    if not id or id == '' then
        return error_msg('Module:Infobox error: no research id specified')
    end

    local research = get_research()
    local data = research[id]
    if not data then
        return error_msg('Module:Infobox error: research "' .. id .. '" not found')
    end

    local name = data.name or id

    -- Build a compact card using a styled div
    local styles = frame:extensionTag({
        name = 'templatestyles',
        args = { src = 'Template:Infobox/styles.css' }
    })

    local card = mw.html.create('div')
        :addClass('research-card')

    -- Title row: linked research name
    card:tag('div')
        :addClass('research-card-title')
        :wikitext('[[' .. name .. ' (Research)|' .. name .. ']]')

    -- Description
    if data.description and data.description ~= '' then
        card:tag('div')
            :addClass('research-card-desc')
            :wikitext(data.description)
    end

    -- Details container
    local details = card:tag('div')
        :addClass('research-card-details')

    -- Science costs
    if data.costs and data.costs[1] then
        local cost_parts = {}
        for _, cost in ipairs(data.costs) do
            local cost_name = resolve_name(cost.identifier)
            cost_parts[#cost_parts + 1] = format_number(cost.amount) .. 'x [[' .. cost_name .. ']]'
        end
        details:tag('div')
            :addClass('research-card-row')
            :tag('span'):addClass('research-card-label'):wikitext('Cost: '):done()
            :tag('span'):wikitext(table.concat(cost_parts, ', '))
    end

    -- Research time
    if data.seconds_per_science_item and data.seconds_per_science_item > 0 then
        details:tag('div')
            :addClass('research-card-row')
            :tag('span'):addClass('research-card-label'):wikitext('Time per item: '):done()
            :tag('span'):wikitext(data.seconds_per_science_item .. 's')
    end

    -- Prerequisites
    if data.dependencies and data.dependencies[1] then
        local dep_parts = {}
        for _, dep_id in ipairs(data.dependencies) do
            local dep = research[dep_id]
            local dep_name = dep and dep.name or dep_id
            dep_parts[#dep_parts + 1] = '[[' .. dep_name .. ' (Research)|' .. dep_name .. ']]'
        end
        details:tag('div')
            :addClass('research-card-row')
            :tag('span'):addClass('research-card-label'):wikitext('Requires: '):done()
            :tag('span'):wikitext(table.concat(dep_parts, ', '))
    end

    -- Unlocks (crafting recipes)
    if data.crafting_unlocks and data.crafting_unlocks[1] then
        local unlock_parts = {}
        for _, recipe_id in ipairs(data.crafting_unlocks) do
            local recipes = load_data('Module:Data/Recipes')
            local recipe = recipes[recipe_id]
            if recipe and recipe.outputs then
                for _, out in ipairs(recipe.outputs) do
                    local out_name = resolve_name(out.identifier)
                    unlock_parts[#unlock_parts + 1] = '[[' .. out_name .. ']]'
                end
            elseif recipe then
                unlock_parts[#unlock_parts + 1] = recipe.name or recipe_id
            end
        end
        if #unlock_parts > 0 then
            details:tag('div')
                :addClass('research-card-row')
                :tag('span'):addClass('research-card-label'):wikitext('Unlocks: '):done()
                :tag('span'):wikitext(table.concat(unlock_parts, ', '))
        end
    end

    return styles .. tostring(card)
end

return p
