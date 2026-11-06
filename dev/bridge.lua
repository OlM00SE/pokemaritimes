-- mGBA control bridge: line-based TCP command server for automated playtesting.
-- Load with: mGBA.exe --script bridge.lua rom.gba   (listens on 127.0.0.1:8765)
-- Every command gets exactly one reply line once it has finished executing.
--   ping                      -> ok pong
--   press <KEYS> <frames>     hold keys (e.g. A, UP, A+B) for N frames, then release
--   wait <frames>             advance N frames with no input
--   shot <path>               save a PNG screenshot
--   read8|read16|read32 <hexaddr>
--   readrange <hexaddr> <len> -> hex string
--   write8|write16|write32 <hexaddr> <value>
--   frame                     -> current frame counter
--   reset                     reset the console

local PORT = 8765
local SESSION = "standalone"
local KEYS = { A = 0, B = 1, SELECT = 2, START = 3, RIGHT = 4, LEFT = 5, UP = 6, DOWN = 7, R = 8, L = 9 }

local server, client
local queue = {}      -- pending commands
local active = nil    -- command currently running across frames
local buf = ""
local frameCount = 0

local function reply(s) if client then client:send(s .. "\n") end end

local function keymask(spec)
  local m = 0
  for k in string.gmatch(spec:upper(), "[^+]+") do
    if KEYS[k] == nil then return nil end
    m = m | (1 << KEYS[k])
  end
  return m
end

local function start(line)
  local cmd, a, b = line:match("^(%S+)%s*(%S*)%s*(.*)$")
  if cmd == "ping" then reply("ok pong " .. SESSION)
  elseif cmd == "frame" then reply("ok " .. frameCount)
  elseif cmd == "press" then
    local m = keymask(a)
    if not m then reply("err badkey " .. a) return end
    active = { kind = "press", mask = m, left = tonumber(b) or 1 }
  elseif cmd == "wait" then
    active = { kind = "wait", left = tonumber(a) or 1 }
  elseif cmd == "shot" then
    emu:screenshot(a); reply("ok " .. a)
  elseif cmd == "read8" then reply("ok " .. emu:read8(tonumber(a, 16)))
  elseif cmd == "read16" then reply("ok " .. emu:read16(tonumber(a, 16)))
  elseif cmd == "read32" then reply("ok " .. emu:read32(tonumber(a, 16)))
  elseif cmd == "readrange" then
    local s = emu:readRange(tonumber(a, 16), tonumber(b))
    reply("ok " .. (s:gsub(".", function(c) return string.format("%02x", c:byte()) end)))
  elseif cmd == "write8" then emu:write8(tonumber(a, 16), tonumber(b)); reply("ok")
  elseif cmd == "write16" then emu:write16(tonumber(a, 16), tonumber(b)); reply("ok")
  elseif cmd == "write32" then emu:write32(tonumber(a, 16), tonumber(b)); reply("ok")
  elseif cmd == "reset" then emu:reset(); reply("ok")
  else reply("err unknown " .. tostring(cmd)) end
end

callbacks:add("frame", function()
  frameCount = frameCount + 1
  if active then
    if active.kind == "press" then emu:setKeys(active.mask) end
    active.left = active.left - 1
    if active.left <= 0 then
      emu:setKeys(0)
      active = nil
      reply("ok")
    end
    return
  end
  if #queue > 0 then start(table.remove(queue, 1)) end
end)

local function onReceived()
  while client do
    local p, err = client:receive(4096)
    if p then
      buf = buf .. p
      for line in buf:gmatch("([^\n]*)\n") do
        line = line:gsub("\r", "")
        if #line > 0 then table.insert(queue, line) end
      end
      buf = buf:match("[^\n]*$")
    else
      if err ~= socket.ERRORS.AGAIN then client:close(); client = nil end
      return
    end
  end
end

server = socket.bind("127.0.0.1", PORT)
server:listen()
server:add("received", function()
  local s = server:accept()
  if s then
    if client then client:close() end
    client = s
    client:add("received", onReceived)
    client:add("error", function() client = nil end)
  end
end)
console:log("bridge listening on " .. PORT)
