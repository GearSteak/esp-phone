--!name Digivice
--!icon page

-- Digivice companion for Snail OS (XTEINK X3/X4).
-- 1) On Digivice: Apps → Tools → Snail Link → Start bridge
-- 2) Same Wi‑Fi as Digivice
-- 3) Set HOST below to the URL shown on Digivice (edit this file on the SD card)
--
-- snail.fetch is documented as HTTPS. If HTTP fails with a TLS/scheme error,
-- see docs/SNAIL_DIGIVICE.md (certs / tunnel).

local HOST = "http://192.168.1.50:8787"

local rows = {}
local cursor = 1
local status = "Confirm = refresh"
local detail = nil
local err = ""

local function recall()
  local raw = snail.load()
  if raw and #raw > 8 then
    HOST = raw
  end
  local cached = snail.cache("inbox")
  if cached and #cached > 0 then
    rows = {}
    for line in string.gmatch(cached .. "\n", "(.-)\n") do
      if line ~= "" then
        rows[#rows + 1] = line
      end
    end
  end
end

local function persist_rows()
  local buf = table.concat(rows, "\n")
  if #buf > 0 then
    snail.cache("inbox", buf)
  end
end

local function load_inbox()
  status = "Fetching…"
  err = ""
  local url = HOST .. "/snail/v1/inbox?limit=20"
  local fresh = {}
  local head, n = snail.fetch(url, "total,items[],line,title,body",
    function(line, title, body, i)
      local s = line
      if not s or s == "" then
        s = (title or "?") .. ": " .. (body or "")
      end
      if #s > 72 then s = string.sub(s, 1, 72) end
      fresh[#fresh + 1] = s
      return #fresh < 20
    end)
  if not head then
    -- Fallback: raw body (still may fail if HTTP blocked)
    local body, why = snail.fetch(url)
    if not body then
      err = tostring(why or n or "fetch failed")
      status = "Offline · showing cache"
      return
    end
    -- Very small JSON scrape for "line":"..."
    for line in string.gmatch(body, '"line"%s*:%s*"([^"]*)"') do
      fresh[#fresh + 1] = line
      if #fresh >= 20 then break end
    end
    if #fresh == 0 then
      err = "bad JSON"
      status = "Parse failed"
      return
    end
  end
  if #fresh == 0 then
    status = "Inbox empty"
    rows = { "(no Digivice notifs yet)" }
  else
    rows = fresh
    status = tostring(head and head.total or #rows) .. " from Digivice"
    persist_rows()
  end
  if cursor > #rows then cursor = #rows end
  if cursor < 1 then cursor = 1 end
end

function start()
  recall()
  snail.hint("OK refresh   UP/DOWN  BACK menu")
  snail.after(load_inbox)
end

function key(k)
  if detail then
    if k == "ok" or k == "left" then
      detail = nil
    end
    return
  end
  if k == "up" then
    cursor = cursor - 1
    if cursor < 1 then cursor = 1 end
  elseif k == "down" then
    cursor = cursor + 1
    if cursor > #rows then cursor = #rows end
  elseif k == "ok" then
    if #rows == 0 then
      snail.after(load_inbox)
    else
      detail = rows[cursor]
    end
  elseif k == "right" then
    snail.after(load_inbox)
  elseif k == "top" then
    snail.after(load_inbox)
  end
end

function draw()
  snail.center(false)
  snail.title("Digivice")
  snail.small(HOST)
  snail.gap()
  if detail then
    snail.text(detail)
    snail.gap()
    snail.hint("OK back")
    return
  end
  snail.small(status)
  if err ~= "" then
    snail.small(err)
  end
  snail.rule()
  if #rows == 0 then
    snail.text("No messages yet.")
    snail.small("Start bridge on Digivice.")
  else
    local start_i = cursor - 2
    if start_i < 1 then start_i = 1 end
    local last = start_i + 5
    if last > #rows then last = #rows end
    for i = start_i, last do
      snail.row(rows[i], i == cursor, "page")
    end
  end
  snail.hint("OK open · RIGHT refresh")
end
