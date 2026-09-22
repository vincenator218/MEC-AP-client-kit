-- list_live_checks.lua   (which flags does the game enforce with a flag-check entity?)
--
-- READ-ONLY. It writes and calls nothing.
--
-- Every ability tested live is enforced by one flag-check entity
-- (vtable +1C7B168) with bit 0x2000 set, whose [e+0x80] points at its flag's
-- table node (+0x10). This script lists EVERY such entity with the hash it
-- checks, so we can see the full set of live-gateable flags, including whether
-- any of them looks like a baseline move (climb, vault, wallrun ...).
--
-- USAGE: paste, Execute, send the whole output. No breakpoints needed.

local MODULE = "MirrorsEdgeCatalyst.exe"
local BASE   = getAddress(MODULE)
local ENT_VT = BASE + 0x1C7B168

local function u32(a) local v = readInteger(a); if v and v < 0 then v = v + 0x100000000 end; return v end

-- node+0x10 -> {hash, node}
local byPtr, n = {}, 0
local tbl = readQword(BASE + 0x257C9D8)
local nb, bk = u32(tbl + 0x28), readQword(tbl + 0x20)
for i = 0, nb - 1 do
  local node = readQword(bk + i * 8)
  local g = 0
  while node and node ~= 0 and g < 2000 do
    local p = readQword(node + 0x10)
    if p and p ~= 0 then byPtr[p] = { h = u32(node), node = node }; n = n + 1 end
    node = readQword(node + 0x28); g = g + 1
  end
end
print(string.format("indexed %d table nodes", n))

local pat = {}
for i = 0, 7 do pat[#pat + 1] = string.format("%02X", (ENT_VT >> (i * 8)) & 0xFF) end
local hits = AOBScan(table.concat(pat, " "), "+W", 1, "8")
local rows, total, unresolved = {}, 0, 0
if hits then
  total = hits.Count
  for i = 0, hits.Count - 1 do
    local e = tonumber(hits[i], 16)
    local fl = u32(e + 0x18) or 0
    local c = readQword(e + 0x80)
    local r = c and byPtr[c]
    if r then
      rows[#rows + 1] = { h = r.h, live = (fl & 0x2000) ~= 0, fl = fl,
                          ev = u32(e + 0x78), tv = u32(r.node + 0x18), data = readQword(e + 0x28) or 0 }
    else
      unresolved = unresolved + 1
    end
  end
  hits.destroy()
end
table.sort(rows, function(a, b) if a.h ~= b.h then return a.h < b.h end return (a.live and 1 or 0) > (b.live and 1 or 0) end)

print(string.format("%d entities with vtable +1C7B168; %d resolved to a flag, %d not (no cached [+80])", total, #rows, unresolved))
print("hash      kind     flags  entity+78  table  data")
for _, r in ipairs(rows) do
  print(string.format("%08X  %-7s  %04X   %-9d  %-5d  %X", r.h, r.live and "LIVE" or "persist", r.fl & 0xFFFF, r.ev or -1, r.tv or -1, r.data))
end
print("done -- send all of this")
