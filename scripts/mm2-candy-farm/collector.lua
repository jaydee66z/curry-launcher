--[[
    MM2 CANDY FARM — Tormenta_2336
    v0.1 — Curry Launcher MM2 scripts baseline
    ================================
    GENERAL LOGIC:
    The script runs a single Heartbeat every frame (~60fps).
    Instead of an event-driven state machine, it uses shouldFarm() with three gates.
    If any gate fails -> Heartbeat does nothing and clears physics if it was farming.
    If all three pass -> enables noclip, hovers, and flies coin by coin.

    THREE GATES of shouldFarm():
      GATE 1: "Waiting for your turn" label visible in PlayerGui -> spectator, never move
      GATE 2: workspace.<Map>.CoinContainer has children -> an active round has coins
      GATE 3: The player holds a Tool (character or backpack) -> role has been assigned

    When all three pass, the main loop:
      - Disables Humanoid physics (PlatformStand = true)
      - Noclip (CanCollide = false on every BasePart, re-applied every frame)
      - Anti-gravity via a BodyVelocity (FarmBV) with MaxForce on Y only
      - Danger evasion (knife carriers, and gun carriers when we are innocent)
      - Best-coin selection: nearest safe, fallback nearest any
      - Target Y = coin.Y - HEAD_OFFSET so the head touches the coin (collides), triggering pickup
]]

running = false
task.wait(0.5)

local Players = game:GetService("Players")
local RNS     = game:GetService("RunService")
local lp      = Players.LocalPlayer
running       = true

-- ───────────────────────────────────────────────
-- CONFIG — tune these to change behavior
-- ───────────────────────────────────────────────
local SPEED        = 26    -- studs/second of movement toward the coin
local COIN_REACH   = 1.2   -- studs: within this distance the coin is snapped and marked collected
local HEAD_OFFSET  = 1.5   -- HRP is placed 1.5 studs BELOW the coin so the head (1.5 studs above HRP) touches it
local MURDER_SAFE  = 35    -- evade murderer at < 35 studs
local SHERIFF_SAFE = 20    -- evade sheriff (only if we are innocent) at < 20 studs

-- ───────────────────────────────────────────────
-- STATE
-- ───────────────────────────────────────────────
local visited    = {}         -- coin -> tick() when marked collected; expires at 0.8s
local myRole     = "innocent" -- updated by getMyRole() when farming starts
local wasFarming = false      -- so stopFarm() runs exactly once on farm->idle transition

-- ───────────────────────────────────────────────
-- shouldFarm() — the three gates (see header)
-- ───────────────────────────────────────────────
local function shouldFarm()
    -- GATE 1: Spectator / "Waiting for your turn"
    for _, v in ipairs(lp.PlayerGui:GetDescendants()) do
        if v:IsA("TextLabel") and v.Text:lower():find("waiting for your turn") then
            return false
        end
    end

    -- GATE 2: Coins present in the map
    local hasCoins = false
    for _, v in ipairs(workspace:GetChildren()) do
        local cc = v:FindFirstChild("CoinContainer")
        if cc and #cc:GetChildren() > 0 then
            hasCoins = true
            break
        end
    end
    if not hasCoins then return false end

    -- GATE 3: A Tool exists (role assigned = round active)
    local char = lp.Character
    if char then
        for _, t in ipairs(char:GetChildren()) do
            if t:IsA("Tool") then return true end
        end
    end
    for _, t in ipairs(lp.Backpack:GetChildren()) do
        if t:IsA("Tool") then return true end
    end

    return false
end

-- ───────────────────────────────────────────────
-- getMyRole() — detect current role
-- ───────────────────────────────────────────────
-- knife -> murderer, gun/sheriff/revolver -> sheriff, otherwise innocent.
local function getMyRole()
    local function scan(container)
        for _, t in ipairs(container:GetChildren()) do
            if t:IsA("Tool") then
                local n = t.Name:lower()
                if n:find("knife") then return "murderer" end
                if n:find("gun") or n:find("sheriff") or n:find("revolver") then
                    return "sheriff"
                end
            end
        end
    end
    if lp.Character then
        local r = scan(lp.Character)
        if r then return r end
    end
    return scan(lp.Backpack) or "innocent"
end

-- ───────────────────────────────────────────────
-- getDanger() — active threats
-- ───────────────────────────────────────────────
-- Returns a list of {pos = Vector3, dist = number} for each hostile tool carrier.
local function getDanger()
    local out = {}
    for _, p in ipairs(Players:GetPlayers()) do
        if p ~= lp and p.Character then
            local hrp = p.Character:FindFirstChild("HumanoidRootPart")
            local hum = p.Character:FindFirstChild("Humanoid")
            if hrp and hum and hum.Health > 0 then
                for _, t in ipairs(p.Character:GetChildren()) do
                    if t:IsA("Tool") then
                        local n = t.Name:lower()
                        if n:find("knife") then
                            table.insert(out, { pos = hrp.Position, dist = MURDER_SAFE })
                        elseif (n:find("gun") or n:find("sheriff") or n:find("revolver"))
                            and myRole == "innocent" then
                            table.insert(out, { pos = hrp.Position, dist = SHERIFF_SAFE })
                        end
                    end
                end
            end
        end
    end
    return out
end

local function isSafe(pos, danger)
    for _, d in ipairs(danger) do
        if (pos - d.pos).Magnitude < d.dist then return false end
    end
    return true
end

-- ───────────────────────────────────────────────
-- getCoins() — unvisited Coin_Server parts
-- ───────────────────────────────────────────────
local function getCoins()
    for _, v in ipairs(workspace:GetChildren()) do
        local cc = v:FindFirstChild("CoinContainer")
        if cc then
            local t = {}
            for _, c in ipairs(cc:GetChildren()) do
                if c.Name == "Coin_Server" and c:IsA("BasePart")
                    and c.Parent and not visited[c] then
                    t[#t + 1] = c
                end
            end
            return t
        end
    end
    return {}
end

-- ───────────────────────────────────────────────
-- getBestCoin(myPos) — pick a target
-- ───────────────────────────────────────────────
-- Two-pass: prefer nearest safe; fallback to nearest overall.
local function getBestCoin(myPos)
    local coins  = getCoins()
    local danger = getDanger()

    local bS, bSD = nil, math.huge -- best safe + dist
    local bA, bAD = nil, math.huge -- best any  + dist

    for _, c in ipairs(coins) do
        local tp = Vector3.new(c.Position.X, c.Position.Y - HEAD_OFFSET, c.Position.Z)
        local d  = (tp - myPos).Magnitude
        if isSafe(c.Position, danger) then
            if d < bSD then bS, bSD = c, d end
        end
        if d < bAD then bA, bAD = c, d end
    end

    return bS or bA
end

-- ───────────────────────────────────────────────
-- setupHover / applyNoclip / stopFarm
-- ───────────────────────────────────────────────
local function setupHover(hrp)
    local bv = hrp:FindFirstChild("FarmBV")
        or Instance.new("BodyVelocity", hrp)
    bv.Name     = "FarmBV"
    bv.MaxForce = Vector3.new(0, 1e6, 0)
    bv.P        = 1e5
    bv.Velocity = Vector3.zero
    return bv
end

local function applyNoclip(char)
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") then p.CanCollide = false end
    end
end

local function stopFarm(char, hrp, hum)
    if not char or not hrp or not hum then return end
    hum.PlatformStand = false
    local bv = hrp:FindFirstChild("FarmBV")
    if bv then bv:Destroy() end
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") then p.CanCollide = true end
    end
end

-- ───────────────────────────────────────────────
-- Visited expiry loop (keeps the table bounded)
-- ───────────────────────────────────────────────
task.spawn(function()
    while running do
        local now = tick()
        for coin, t in pairs(visited) do
            if now - t > 0.8 then visited[coin] = nil end
        end
        task.wait(0.8)
    end
end)

-- ───────────────────────────────────────────────
-- HEARTBEAT — main loop (runs every frame)
-- ───────────────────────────────────────────────
local farmConn
farmConn = RNS.Heartbeat:Connect(function(dt)
    if not running then
        farmConn:Disconnect()
        return
    end

    local char = lp.Character
    local hum  = char and char:FindFirstChild("Humanoid")
    local hrp  = char and char:FindFirstChild("HumanoidRootPart")
    if not hum or not hrp or hum.Health <= 0 then return end

    if not shouldFarm() then
        if wasFarming then
            stopFarm(char, hrp, hum)
            wasFarming = false
            visited    = {}
        end
        return
    end

    if not wasFarming then
        wasFarming = true
        myRole     = getMyRole()
    end

    hum.PlatformStand = true
    applyNoclip(char)

    local bv     = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
    local myPos  = hrp.Position
    local danger = getDanger()

    -- Immediate danger evasion: if any threat is inside 60% of its safe radius, flee.
    for _, d in ipairs(danger) do
        if (myPos - d.pos).Magnitude < d.dist * 0.6 then
            local away = myPos - d.pos
            if away.Magnitude > 0 then
                hrp.CFrame = CFrame.new(myPos + away.Unit * SPEED * dt)
            end
            bv.Velocity = Vector3.zero
            return
        end
    end

    local coin = getBestCoin(myPos)
    if not coin then
        bv.Velocity = Vector3.zero
        return
    end

    local target = Vector3.new(
        coin.Position.X,
        coin.Position.Y - HEAD_OFFSET,
        coin.Position.Z
    )
    local diff = target - myPos
    local dist = diff.Magnitude

    if dist < COIN_REACH then
        hrp.CFrame    = CFrame.new(target)
        bv.Velocity   = Vector3.zero
        visited[coin] = tick()
        return
    end

    local step = math.min(dist, SPEED * dt)
    hrp.CFrame  = CFrame.new(myPos + diff.Unit * step)
    bv.Velocity = Vector3.zero
end)
