-- setflag.lua  -- read/write one flag in the live table . No game-function calls.
-- getflag(hash)       prints the current value
-- setflag(hash, v)    prints old -> new and writes v
-- checksave()         prints the four flags touched in the research tests (edit for your own flags)

local function node(h)
  local B = getAddress("MirrorsEdgeCatalyst.exe")
  local t = readQword(B + 0x257C9D8)
  local nb = readInteger(t + 0x28)
  local n = readQword(readQword(t + 0x20) + (h % nb) * 8)
  while n and n ~= 0 do
    if (readInteger(n) & 0xFFFFFFFF) == h then return n end
    n = readQword(n + 0x28)
  end
end

function getflag(h)
  local n = node(h)
  if not n then print(string.format("%08X: not found", h)) return end
  print(string.format("%08X = %d", h, readInteger(n + 0x18)))
  return readInteger(n + 0x18)
end

function setflag(h, v)
  local n = node(h)
  if not n then print(string.format("%08X: not found", h)) return end
  print(string.format("%08X: %d -> %d", h, readInteger(n + 0x18), v))
  writeInteger(n + 0x18, v)
end

function checksave()
  for _, f in ipairs({ {0xB75C826E, "Disruptor_Overload", 0}, {0x2C9CC1D5, "Focus", 0},
                       {0xE77600AB, "MagRopeSwing", 1}, {0xF139B4B3, "DoubleWallrun", 1} }) do
    local n = node(f[1])
    local v = n and readInteger(n + 0x18)
    print(string.format("%-20s %08X = %s  (expected %d) %s", f[2], f[1], tostring(v), f[3],
      v == f[3] and "OK" or "<-- CHECK"))
  end
end

print("getflag(h) / setflag(h, v) / checksave()")
