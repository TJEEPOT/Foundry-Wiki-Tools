-- Module:Achievements
-- Renders achievement tables from Module:Data/Achievements.
--
-- Each known achievement type has its own exported function that returns
-- just the wikitable (no heading), so the Achievements page can place
-- section headings and editor notes around them:
--
--   == Item Creation ==
--   {{#invoke:Achievements|item_creation}}
--
-- p.remaining() renders heading + table for any types NOT covered by the
-- individual functions above, so new achievement types added in future
-- game updates are still shown automatically.

local p = {}

local data = mw.loadData('Module:Data/Achievements')

-- -----------------------------------------------------------------------
-- Configuration
-- -----------------------------------------------------------------------

local TYPE_LABELS = {
    MULTI_ITEMCREATION  = 'Item Creation',
    MULTI_BUILDINGBUILT = 'Building Placement',
    MULTI_RESEARCH      = 'Research',
    LIFETIME_EARNINGS   = 'Lifetime Earnings',
    MARKET_DOMINANCE    = 'Market Dominance',
    SPACE_STATION       = 'Space Station',
    QUESTS              = 'Quests',
    FIXED               = 'Special',
}

-- Types that have their own dedicated invoke function.
-- p.remaining() skips these and only renders anything outside this set.
local HANDLED_TYPES = {
    MULTI_ITEMCREATION  = true,
    MULTI_BUILDINGBUILT = true,
    MULTI_RESEARCH      = true,
    LIFETIME_EARNINGS   = true,
    MARKET_DOMINANCE    = true,
    SPACE_STATION       = true,
    QUESTS              = true,
    FIXED               = true,
}

-- -----------------------------------------------------------------------
-- Helpers
-- -----------------------------------------------------------------------

--- Format an integer with comma thousands separators (e.g. 1,000,000).
local function fmt_number(n)
    if not n then return '' end
    local s = tostring(math.floor(n))
    return s:reverse():gsub('(%d%d%d)', '%1,'):reverse():gsub('^,', '')
end

--- Build a wikilink, optionally with a display label.
local function link(target, label)
    if not target or target == '' then return '' end
    if label and label ~= target then
        return '[[' .. target .. '|' .. label .. ']]'
    end
    return '[[' .. target .. ']]'
end

--- Render the extra column header(s) for a given achievement type.
local function type_headers(atype)
    if atype == 'MULTI_ITEMCREATION' then
        return '! Item(s)\n! Required'
    elseif atype == 'MULTI_BUILDINGBUILT' then
        return '! Building(s)\n! Required'
    elseif atype == 'MULTI_RESEARCH' then
        return '! Research'
    elseif atype == 'LIFETIME_EARNINGS' then
        return '! Earnings Required'
    elseif atype == 'MARKET_DOMINANCE' then
        return '! Planets Required'
    elseif atype == 'SPACE_STATION' then
        return '! Space Station Upgrade'
    elseif atype == 'QUESTS' then
        return '! Quest(s)'
    else
        return nil
    end
end

--- Render the extra data cell(s) for a single achievement row.
local function type_cells(a, atype)
    local parts = {}

    if atype == 'MULTI_ITEMCREATION' then
        if a.multiItemCreationNames then
            local links = {}
            for i, name in ipairs(a.multiItemCreationNames) do
                links[i] = link(name)
            end
            table.insert(parts, '| ' .. table.concat(links, '<br>'))
        else
            table.insert(parts, '|')
        end
        table.insert(parts, '| ' .. fmt_number(a.multiItemCreationsNeeded))

    elseif atype == 'MULTI_BUILDINGBUILT' then
        if a.multiBuildingNames then
            local links = {}
            for i, name in ipairs(a.multiBuildingNames) do
                links[i] = link(name)
            end
            table.insert(parts, '| ' .. table.concat(links, '<br>'))
        else
            table.insert(parts, '|')
        end
        table.insert(parts, '| ' .. fmt_number(a.multiBuildingsNeeded))

    elseif atype == 'MULTI_RESEARCH' then
        if a.multiResearch then
            local res_parts = {}
            for _, r in ipairs(a.multiResearch) do
                local l = link(r.name)
                if r.needed and r.needed > 1 then
                    l = l .. ' \xc3\x97' .. r.needed  -- ×
                end
                table.insert(res_parts, l)
            end
            table.insert(parts, '| ' .. table.concat(res_parts, '<br>'))
        else
            table.insert(parts, '|')
        end

    elseif atype == 'LIFETIME_EARNINGS' then
        table.insert(parts, '| ' .. fmt_number(a.lifetimeEarningsNeeded))

    elseif atype == 'MARKET_DOMINANCE' then
        table.insert(parts, '| ' .. (a.planetsWithMarketDominanceNeeded and tostring(a.planetsWithMarketDominanceNeeded) or ''))

    elseif atype == 'SPACE_STATION' then
        if a.spaceStationUpgradeName then
            table.insert(parts, '| ' .. link(a.spaceStationUpgradeName))
        else
            table.insert(parts, '| ' .. (a.spaceStationUpgradeIdentifier or ''))
        end

    elseif atype == 'QUESTS' then
        if a.questNames then
            local links = {}
            for i, name in ipairs(a.questNames) do
                links[i] = link(name)
            end
            table.insert(parts, '| ' .. table.concat(links, '<br>'))
        else
            table.insert(parts, '|')
        end
    end

    return table.concat(parts, '\n')
end

-- -----------------------------------------------------------------------
-- Core renderer — returns just the wikitable, no heading
-- -----------------------------------------------------------------------

local function render_table(atype, achievements)
    local lines = {}

    table.insert(lines, '{| class="wikitable sortable" style="width:100%"')
    table.insert(lines, '|-')

    local header = '! Achievement\n! Description'
    local extra_hdr = type_headers(atype)
    if extra_hdr then
        header = header .. '\n' .. extra_hdr
    end
    table.insert(lines, header)

    for _, a in ipairs(achievements) do
        table.insert(lines, '|-')
        table.insert(lines, "| '''" .. (a.displayName or '') .. "'''")
        table.insert(lines, '| ' .. (a.description or ''))

        local extra = type_cells(a, atype)
        if extra ~= '' then
            table.insert(lines, extra)
        end
    end

    table.insert(lines, '|}')
    table.insert(lines, '')

    return table.concat(lines, '\n')
end

-- -----------------------------------------------------------------------
-- Shared helpers for individual type functions
-- -----------------------------------------------------------------------

local function get_sorted(atype)
    local list = {}
    for _, a in pairs(data) do
        if (a.achievementType or 'FIXED') == atype then
            table.insert(list, a)
        end
    end
    table.sort(list, function(x, y)
        if x.sortOrder ~= y.sortOrder then
            return x.sortOrder < y.sortOrder
        end
        return (x.displayName or '') < (y.displayName or '')
    end)
    return list
end

-- -----------------------------------------------------------------------
-- Per-type exported functions (table only — heading lives on the page)
-- -----------------------------------------------------------------------

function p.item_creation(frame)
    return render_table('MULTI_ITEMCREATION', get_sorted('MULTI_ITEMCREATION'))
end

function p.building_built(frame)
    return render_table('MULTI_BUILDINGBUILT', get_sorted('MULTI_BUILDINGBUILT'))
end

function p.research(frame)
    return render_table('MULTI_RESEARCH', get_sorted('MULTI_RESEARCH'))
end

function p.lifetime_earnings(frame)
    return render_table('LIFETIME_EARNINGS', get_sorted('LIFETIME_EARNINGS'))
end

function p.market_dominance(frame)
    return render_table('MARKET_DOMINANCE', get_sorted('MARKET_DOMINANCE'))
end

function p.space_station(frame)
    return render_table('SPACE_STATION', get_sorted('SPACE_STATION'))
end

function p.quests(frame)
    return render_table('QUESTS', get_sorted('QUESTS'))
end

function p.fixed(frame)
    return render_table('FIXED', get_sorted('FIXED'))
end

-- -----------------------------------------------------------------------
-- p.remaining — renders heading + table for any type NOT in HANDLED_TYPES.
-- Call this at the bottom of the Achievements page so new achievement
-- types added in future game updates are never silently dropped.
-- -----------------------------------------------------------------------

function p.remaining(frame)
    local groups = {}
    for _, a in pairs(data) do
        local atype = a.achievementType or 'FIXED'
        if not HANDLED_TYPES[atype] then
            if not groups[atype] then groups[atype] = {} end
            table.insert(groups[atype], a)
        end
    end

    local output = {}
    for atype, achs in pairs(groups) do
        table.sort(achs, function(x, y)
            if x.sortOrder ~= y.sortOrder then
                return x.sortOrder < y.sortOrder
            end
            return (x.displayName or '') < (y.displayName or '')
        end)
        local label = TYPE_LABELS[atype] or atype
        table.insert(output, '== ' .. label .. ' ==\n')
        table.insert(output, render_table(atype, achs))
    end

    return table.concat(output, '\n')
end

return p
