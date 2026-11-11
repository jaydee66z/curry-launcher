--[[
    MM2 CANDY FARM — v0.2 (Tormenta_2336 + Curry Launcher optimizations)
    ==================================================================
    v0.2 CHANGES (verified live in MM2 via roblox-mcp):
    - FIXED: coins are tagged "CoinVisual" (CollectionService); the parent
      Coin_Server is a Model, not a BasePart — v0.1's `c:IsA("BasePart")`
      filter rejected every single coin. Now we iterate the tag directly.
    - FIXED: HEAD_OFFSET is measured dynamically from the live rig instead
      of hardcoded 1.5 (R15 real offset is ~1.86; R6 is ~1.5).
    - FIXED: Gate 1 used the literal "waiting for your turn" which does
      not exist in current MM2. We now check MainGUI.Game.Waiting.Visible
      directly — O(1) instead of walking 3,600+ TextLabels per frame.
    - DROPPED: Gate 3 (tool-present). Current MM2 does not give innocents
      a tool, so the gate falsely blocked. The two surviving gates
      (not-spectator + coins-exist) are sufficient.
    - PERF: CoinContainer reference is cached per round and invalidated
      on CoinsStarted remote fire, instead of walking workspace per frame.
    - PERF: visited is keyed on CoinID (an attribute) and set the instant
      the server fires CoinCollected.OnClientEvent — exact, no 0.8s hack.
    - PERF: applyNoclip runs once on round start; a DescendantAdded
      listener catches new accessories and sets CanCollide=false on them.

    FLOW:
      - setupNoclip / character handler: hook DescendantAdded per character
      - cacheCoinContainer: find Workspace.<Map>.CoinContainer once
      - CoinCollected.OnClientEvent -> visited[coinID] = true
      - CoinsStarted.OnClientEvent  -> invalidate cache, clear visited
      - Heartbeat:
          1. kill switch
          2. character valid + alive
          3. Waiting.Visible or no CoinContainer -> stopFarm once, return
          4. first entry -> detect role, apply noclip, setup hover
          5. compute threats; if too close, flee
          6. getBestCoin via CollectionService:GetTagged("CoinVisual")
          7. target = CoinVisual.Position - headOffset on Y
          8. snap if within COIN_REACH else step toward it at SPEED
]]

running = false
task.wait(0.5)

local Players            = game:GetService("Players")
local RNS                = game:GetService("RunService")
local CollectionService  = game:GetService("CollectionService")
local ReplicatedStorage  = game:GetService("ReplicatedStorage")
local lp                 = Players.LocalPlayer
running                  = true

-- ───────────────────────────────────────────────
-- CONFIG
-- ───────────────────────────────────────────────
local SPEED        = 26
local COIN_REACH   = 1.2
local MURDER_SAFE  = 35
local SHERIFF_SAFE = 20
-- HEAD_OFFSET is derived dynamically from the live rig (see refreshHeadOffset).

-- ───────────────────────────────────────────────
-- STATE
-- ───────────────────────────────────────────────
local visited     = {}          -- coinID -> true (cleared on CoinsStarted)
local myRole      = "innocent"
local wasFarming  = false
local headOffset  = 1.5         -- fallback for R6; refreshed on each character
local coinContainer = nil       -- cached Model reference
local waitingLabel  = nil       -- cached GUI reference

-- Remotes fire fast; keep a ref so we never WaitForChild on hot path.
local Remotes       = ReplicatedStorage:WaitForChild("Remotes")
local Gameplay      = Remotes:WaitForChild("Gameplay")
local CoinCollected = Gameplay:WaitForChild("CoinCollected")
local CoinsStarted  = Gameplay:WaitForChild("CoinsStarted")

-- ───────────────────────────────────────────────
-- CACHING HELPERS
-- ───────────────────────────────────────────────
local function cacheCoinContainer()
    coinContainer = nil
    for _, v in ipairs(workspace:GetChildren()) do
        local cc = v:FindFirstChild("CoinContainer")
        if cc then
            coinContainer = cc
            return
        end
    end
end

local function cacheWaitingLabel()
    local gui = lp:FindFirstChild("PlayerGui")
    local mainGui = gui and gui:FindFirstChild("MainGUI")
    local gameFrame = mainGui and mainGui:FindFirstChild("Game")
    waitingLabel = gameFrame and gameFrame:FindFirstChild("Waiting") or nil
end

local function refreshHeadOffset(char)
    local hrp = char:FindFirstChild("HumanoidRootPart")
    local head = char:FindFirstChild("Head")
    if hrp and head then
        local delta = head.Position.Y - hrp.Position.Y
        if delta > 0 and delta < 5 then
            headOffset = delta
        end
    end
end

-- ───────────────────────────────────────────────
-- Remote listeners
-- ───────────────────────────────────────────────
CoinCollected.OnClientEvent:Connect(function(coinID)
    -- Marks the specific coin collected the instant the server confirms.
    if coinID ~= nil then visited[coinID] = true end
end)

CoinsStarted.OnClientEvent:Connect(function()
    visited = {}
    cacheCoinContainer()
end)

-- ───────────────────────────────────────────────
-- Character / noclip handler
-- ───────────────────────────────────────────────
local noclipConn
local function applyNoclipOnce(char)
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") then p.CanCollide = false end
    end
end

local function restoreCollision(char)
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") then p.CanCollide = true end
    end
end

local function onCharacter(char)
    char:WaitForChild("HumanoidRootPart", 5)
    refreshHeadOffset(char)
    cacheWaitingLabel()
    if noclipConn then noclipConn:Disconnect() end
    noclipConn = char.DescendantAdded:Connect(function(d)
        if d:IsA("BasePart") then
            task.defer(function() if d.Parent then d.CanCollide = false end end)
        end
    end)
end

if lp.Character then onCharacter(lp.Character) end
lp.CharacterAdded:Connect(onCharacter)

cacheCoinContainer()
cacheWaitingLabel()

-- ───────────────────────────────────────────────
-- Gates (now O(1) each)
-- ───────────────────────────────────────────────
local function shouldFarm()
    -- Gate 1: not spectating (Waiting ImageLabel hidden means game active)
    if waitingLabel == nil then cacheWaitingLabel() end
    if waitingLabel and waitingLabel.Visible then return false end

    -- Gate 2: active CoinContainer with children
    if coinContainer == nil or coinContainer.Parent == nil then
        cacheCoinContainer()
    end
    if coinContainer == nil or #coinContainer:GetChildren() == 0 then
        return false
    end

    return true
end

-- ───────────────────────────────────────────────
-- Role detection (kept for danger evaluation)
-- ───────────────────────────────────────────────
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
-- Danger (threats) / safe check
-- ───────────────────────────────────────────────
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
-- Coin selection (direct tagged query)
-- ───────────────────────────────────────────────
local function getBestCoin(myPos)
    local danger = getDanger()
    local bS, bSD = nil, math.huge
    local bA, bAD = nil, math.huge
    for _, coin in ipairs(CollectionService:GetTagged("CoinVisual")) do
        local coinID = coin:GetAttribute("CoinID")
        if coin:IsA("BasePart")
            and coin.Parent
            and not coin:GetAttribute("Collected")
            and not coin:GetAttribute("RoundEnd")
            and not (coinID and visited[coinID])
        then
            local pos = coin.Position
            local tp  = Vector3.new(pos.X, pos.Y - headOffset, pos.Z)
            local d   = (tp - myPos).Magnitude
            if isSafe(pos, danger) then
                if d < bSD then bS, bSD = coin, d end
            end
            if d < bAD then bA, bAD = coin, d end
        end
    end
    return bS or bA
end

-- ───────────────────────────────────────────────
-- Hover / stopFarm
-- ───────────────────────────────────────────────
local function setupHover(hrp)
    local bv = hrp:FindFirstChild("FarmBV") or Instance.new("BodyVelocity", hrp)
    bv.Name     = "FarmBV"
    bv.MaxForce = Vector3.new(0, 1e6, 0)
    bv.P        = 1e5
    bv.Velocity = Vector3.zero
    return bv
end

local function stopFarm(char, hrp, hum)
    if not char or not hrp or not hum then return end
    hum.PlatformStand = false
    local bv = hrp:FindFirstChild("FarmBV")
    if bv then bv:Destroy() end
    restoreCollision(char)
end

-- ───────────────────────────────────────────────
-- HEARTBEAT
-- ───────────────────────────────────────────────
local farmConn
farmConn = RNS.Heartbeat:Connect(function(dt)
    if not running then
        farmConn:Disconnect()
        if noclipConn then noclipConn:Disconnect() end
        return
    end

    local char = lp.Character
    local hum  = char and char:FindFirstChildOfClass("Humanoid")
    local hrp  = char and char:FindFirstChild("HumanoidRootPart")
    if not hum or not hrp or hum.Health <= 0 then return end

    if not shouldFarm() then
        if wasFarming then
            stopFarm(char, hrp, hum)
            wasFarming = false
            -- Do NOT wipe visited here; CoinsStarted resets it on round start.
        end
        return
    end

    if not wasFarming then
        wasFarming = true
        myRole     = getMyRole()
        refreshHeadOffset(char)
        applyNoclipOnce(char)
    end

    hum.PlatformStand = true

    local bv     = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
    local myPos  = hrp.Position
    local danger = getDanger()

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

    local target = Vector3.new(coin.Position.X, coin.Position.Y - headOffset, coin.Position.Z)
    local diff   = target - myPos
    local dist   = diff.Magnitude

    if dist < COIN_REACH then
        hrp.CFrame  = CFrame.new(target)
        bv.Velocity = Vector3.zero
        -- Server will fire CoinCollected and we'll mark visited via the
        -- remote listener. We also pre-mark to avoid same-frame reselection.
        local coinID = coin:GetAttribute("CoinID")
        if coinID then visited[coinID] = true end
        return
    end

    local step = math.min(dist, SPEED * dt)
    hrp.CFrame  = CFrame.new(myPos + diff.Unit * step)
    bv.Velocity = Vector3.zero
end)
