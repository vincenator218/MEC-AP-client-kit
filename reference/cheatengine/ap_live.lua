-- ap_live.lua -- reference implementation of the live item/location interface
-- for Mirror's Edge Catalyst (PC), as a Cheat Engine Lua script.
--
-- This is a PROTOTYPE to show the exact memory operations a real client needs
-- (see docs/MEMORY.md). A real client should do the same thing from an
-- injected DLL and make the apply call on the game's own thread.
--
-- STATUS: assembled from pieces that were each tested in-game (flag lookup,
-- table writes, entity scan, the apply call), but this combined script has
-- NOT been run in-game as a whole yet. Run ap_check() first.
--
-- Functions:
--   ap_check()                   sanity-check the addresses against this game build
--   ap_get(flag)                 read a flag (name or hash)
--   ap_set(flag, v)              write a flag to the table only (no call)
--   ap_grant(flag, v)            write + apply now (ability items); v = 1 grant, 0 revoke
--   ap_unlock_side_mission(m)    SilverCompleted_<m> = 1 (shows at next load)
--   ap_watch({flag, ...})        print whenever one of these flags changes (location checks)
--   ap_unwatch()
--
-- Cheat Engine: attach to MirrorsEdgeCatalyst.exe, Table > Show Cheat Table Lua
-- Script (Ctrl+Alt+L), paste, Execute.

local MODULE     = "MirrorsEdgeCatalyst.exe"
local OFF_TABLE  = 0x257C9D8   -- [module+OFF_TABLE] -> flag hash table
local OFF_ENT_VT = 0x1C7B168   -- vtable of the flag-check entity class
local OFF_APPLY  = 0x3A75790   -- apply(entity, value, force)

local function base() return getAddress(MODULE) end

local function u32(a)
  local v = readInteger(a)
  if v and v < 0 then v = v + 0x100000000 end
  return v
end

function ap_hash(s)
  if type(s) == "number" then return s end
  local h = 5381
  for i = 1, #s do h = ((h * 33) ~ s:byte(i)) & 0xFFFFFFFF end
  return h
end

local function node(h)
  local t = readQword(base() + OFF_TABLE)
  if not t or t == 0 then return nil end
  local nb, bk = u32(t + 0x28), readQword(t + 0x20)
  local n = readQword(bk + (h % nb) * 8)
  local guard = 0
  while n and n ~= 0 and guard < 4096 do
    if u32(n) == h then return n end
    n = readQword(n + 0x28); guard = guard + 1
  end
end

function ap_check()
  local t = readQword(base() + OFF_TABLE)
  local nb = t and u32(t + 0x28)
  local ok = t and t ~= 0 and nb and nb > 64 and nb < 1000000
  print(string.format("table %X, buckets %s -> %s", t or 0, tostring(nb), ok and "plausible" or "WRONG"))
  local n = node(ap_hash("Unlocks_Coil"))
  print("known flag Unlocks_Coil " .. (n and "found" or "NOT FOUND -- addresses don't match this build"))
  local vt = readQword(base() + OFF_ENT_VT)
  print(string.format("entity vtable slot 0 -> %X", vt or 0))
  return ok and n ~= nil
end

function ap_get(flag)
  local n = node(ap_hash(flag))
  if not n then return nil end
  return readInteger(n + 0x18)
end

function ap_set(flag, v)
  local n = node(ap_hash(flag))
  if not n then print("flag not in table: " .. tostring(flag)) return false end
  writeInteger(n + 0x18, v)
  return true
end

-- Every flag-check entity for this flag: those whose [e+0x80] points at node+0x10.
local function entities(h)
  local n = node(h)
  if not n then return {} end
  local key = readQword(n + 0x10)
  local vt = base() + OFF_ENT_VT
  local pat = {}
  for i = 0, 7 do pat[#pat + 1] = string.format("%02X", (vt >> (i * 8)) & 0xFF) end
  local out = {}
  local hits = AOBScan(table.concat(pat, " "), "+W", 1, "8")
  if hits then
    for i = 0, hits.Count - 1 do
      local e = tonumber(hits[i], 16)
      if readQword(e + 0x80) == key then
        out[#out + 1] = { e = e, flags = u32(e + 0x18) or 0, data = readQword(e + 0x28) or 0 }
      end
    end
    hits.destroy()
  end
  return out
end

local function apply(e, v)
  if readQword(e) ~= base() + OFF_ENT_VT then return false end
  -- x64 fastcall: rcx = entity, edx = value, r8b = force = 0 (0 = fire the change event too)
  local ok = pcall(executeCodeEx, 0, 3000, base() + OFF_APPLY,
    { type = 0, value = e }, { type = 0, value = v }, { type = 0, value = 0 })
  return ok
end

-- Grant (v=1) or revoke (v=0) an ability item.
--  1. write the table (persists via autosave; applies at next respawn on its own)
--  2. if there is a per-spawn entity (flags & 0x2000): call apply on it  -> live now
--  3. otherwise, ONLY if the flag has at most 3 entities in total, call apply on
--     the persistent entities whose data pointer is unique for this flag
--     (proven on Unlocks_Focus: 2 entities). Flags with many entities are
--     checked by world objects that stream in and out; calling those crashed
--     the game once (Disruptor_Overload). For them, don't call anything: the
--     table write applies at the next respawn.
function ap_grant(flag, v)
  local h = ap_hash(flag)
  if not ap_set(h, v) then return end
  local list = entities(h)
  local live = {}
  for _, x in ipairs(list) do if (x.flags & 0x2000) ~= 0 then live[#live + 1] = x end end
  local targets = {}
  if #live >= 1 then
    targets = live
  elseif #list <= 3 then
    local count = {}
    for _, x in ipairs(list) do count[x.data] = (count[x.data] or 0) + 1 end
    for _, x in ipairs(list) do if count[x.data] == 1 then targets[#targets + 1] = x end end
  end
  for _, x in ipairs(targets) do apply(x.e, v) end
  print(string.format("%s = %d: %d entities, called %d (%s)", tostring(flag), v, #list, #targets,
    #live >= 1 and "live entity" or (#targets > 0 and "persistent, unique data" or "none: applies at next respawn")))
end

function ap_unlock_side_mission(name)
  if ap_set("SilverCompleted_" .. name, 1) then
    print("unlocked '" .. name .. "' -- appears in Missions > Side Missions after the next load (e.g. checkpoint restart)")
  end
end

-- Location detection: poll flags and report changes. A real client would load
-- data/locations.json and watch every hash in it.
AP_WATCH = AP_WATCH or nil
function ap_watch(flags, ms)
  ap_unwatch()
  local last = {}
  for _, f in ipairs(flags) do last[f] = ap_get(f) end
  AP_WATCH = createTimer(nil)
  AP_WATCH.Interval = ms or 1000
  AP_WATCH.OnTimer = function()
    for _, f in ipairs(flags) do
      local v = ap_get(f)
      if v ~= last[f] then
        print(string.format("CHANGED %s: %s -> %s", tostring(f), tostring(last[f]), tostring(v)))
        last[f] = v
      end
    end
  end
  print("watching " .. #flags .. " flags")
end

function ap_unwatch()
  if AP_WATCH then AP_WATCH.destroy(); AP_WATCH = nil end
end

ap_check()
print("ap_get / ap_set / ap_grant / ap_unlock_side_mission / ap_watch / ap_unwatch")
