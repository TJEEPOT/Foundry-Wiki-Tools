-- Module:ItemLink
-- Renders an inline item link with optional icon and quantity count.
-- Usage: {{#invoke:ItemLink|main|id=IronIngot|count=5}}

local p = {}

local data_cache = {}

local function load_data(module_name)
    if not data_cache[module_name] then
        data_cache[module_name] = mw.loadData(module_name)
    end
    return data_cache[module_name]
end

local function get_items()     return load_data('Module:Data/Items') end
local function get_buildings() return load_data('Module:Data/Buildings') end
local function get_elements()  return load_data('Module:Data/Elements') end
local function get_research()  return load_data('Module:Data/Research') end

--- Resolve an identifier to a display name, trying multiple data modules.
local function resolve_name(id)
    if not id or id == '' then return nil end
    local items = get_items()
    if items[id] and items[id].name then return items[id].name end
    local buildings = get_buildings()
    if buildings[id] and buildings[id].name then return buildings[id].name end
    local elements = get_elements()
    if elements[id] and elements[id].name then return elements[id].name end
    local research = get_research()
    if research[id] and research[id].name then return research[id].name end
    -- Fallback: humanize the identifier
    return id:gsub('([A-Z])', ' %1'):gsub('^ ', ''):gsub('_', ' ')
end

--- Formats a number with comma separators.
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

-------------------------------------------------------------------------------
-- Main entry point
-------------------------------------------------------------------------------

function p.main(frame)
    local args = frame.args
    local id = args.id or args[1]
    if not id or id == '' then
        return '<span class="error">ItemLink: no id specified</span>'
    end

    local count = args.count or args[2]
    local noicon = args.noicon

    local name = resolve_name(id)
    if not name then
        return '<span class="error">ItemLink: unknown id "' .. id .. '"</span>'
    end

    -- Build the link HTML
    local span = mw.html.create('span'):addClass('item-link')

    -- Icon (unless suppressed)
    if not noicon or noicon == '' then
        -- Icon file convention: File:{Name}_icon.png
        local icon_file = name:gsub(' ', '_') .. '_icon.png'
        local icon_img = '[[File:' .. icon_file .. '|16px|link=' .. name .. '|class=item-icon]]'
        span:wikitext(icon_img)
    end

    -- Wikilink to item page
    span:wikitext('[[' .. name .. ']]')

    -- Count badge
    if count and count ~= '' then
        local num = tonumber(count)
        local display = num and format_number(num) or count
        span:tag('span')
            :addClass('item-count')
            :wikitext('×' .. display)
    end

    return tostring(span)
end

-------------------------------------------------------------------------------
-- Shortcut entry point for templates: {{ItemLink|id|count}}
-------------------------------------------------------------------------------

function p.link(frame)
    return p.main(frame)
end

return p
