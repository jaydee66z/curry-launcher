--[[
    MM2 CANDY FARM — v0.6 (Curry Launcher)
    ======================================
    v0.6 CRITICAL FIX:
    - Live analysis showed every coin in MM2 shares the SAME CoinID
      attribute (literal "Candy"). Our v0.2-v0.5 used CoinID as the
      visited key, so the FIRST successful pickup set visited["Candy"]
      = true and blocked EVERY subsequent coin. The bot picked one
      candy and froze for 35+ seconds.
    - v0.6 keys visited/deferredUntil on the coin INSTANCE itself
      (weak-keyed table — orphaned coins drop on GC). We no longer
      need the CoinID to know which coin was picked: MM2 sets the
      per-coin attribute Collected=true on the server side, so
      getBestCoin's existing Collected filter handles it.
    - CoinCollected remote listener now only increments the per-round
      candy counter (no dedup needed).

    v0.5 CHANGES vs v0.4:
    - PICKUP FIX #2: the v0.4 anti-sink clamp broke coins BELOW the
      character (Y target stayed at myPos.Y, head never reached coin).
      v0.5 always targets coin.Y - headOffset; STAND_ON_FLOOR is off
      by default. Turn it back on only if the server kicks for sinking
      into the floor.
    - DEBUG EXPOSURE: internal state is mirrored to `_G.farmDebug` for
      live introspection via get-data-by-code. Fields: myRole,
      wasFarming, candiesThisRound, parkedCoinID, tripCoinID,
      lastBestCoinID, lastBestDist, visitedCount, deferredCount,
      lastDecisionAt.
    - LOG: rate-limited prints on state transitions (round start,
      wasFarming toggle, combat mode entered) for console-based
      debugging.

    v0.4 CHANGES vs v0.3:
    - CRITICAL PICKUP FIX: STAND_ON_FLOOR semantics corrected.
      v0.3 pinned target.Y = myPos.Y which, for any coin ABOVE the
      character (most coins on platforms/tables/stairs), left the head
      BELOW the coin — the .Touched never fired. v0.4 interprets the
      flag as "anti-sink": never DESCEND below current Y, but always
      RISE if needed to bring the head to coin.Y via headOffset.
      Explicit formula: target.Y = max(coin.Y - headOffset, myPos.Y).
    - PICKUP DETECTION FIX: we now measure HEAD → coin distance (3D),
      not HRP target distance. The server fires CoinCollected the
      moment the Head's hitbox overlaps the CoinVisual's hitbox.
    - CANDY COUNTER: a per-round counter increments on each
      CoinCollected event. Reset on CoinsStarted.
    - ROLE-BASED COMBAT:
        * COMBAT_AT_CANDIES (default 50) — threshold candies this round
          before combat mode engages.
        * Sheriff: when threshold met + murderer visible, fires
          Gun.Shoot:FireServer(gunOrigin, targetCFrame) targeting the
          murderer's HRP, respecting TIME_BETWEEN_SHOTS reload.
        * Murderer: when threshold met, walks to the nearest alive
          player and fires Knife.Events.KnifeStabbed:FireServer() when
          within STAB_RANGE, respecting TIME_BETWEEN_STABS.
    Kill switch: `running = false`.
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
local CONFIG = {
    -- Features
    FARM_COINS              = true,
    STAND_ON_FLOOR          = false, -- v0.5: off by default; breaks coins below char when on
    ABORT_IF_MURDERER_NEAR  = true,
    CONTEST                 = true,
    LEAVE_FOR_OTHER_BOTS    = false,
    DEBUG_LOG               = true,  -- rate-limited prints
    DEBUG_EXPOSE            = true,  -- mirror state to _G.farmDebug

    -- Combat (new in v0.4)
    COMBAT_AT_CANDIES       = 50,    -- candies this round before combat kicks in
    SHERIFF_SHOOT_RANGE     = 60,    -- stop farming to shoot when murderer within
    TIME_BETWEEN_SHOTS      = 3.4,   -- gun reload
    STAB_RANGE              = 12,    -- murderer stab range
    TIME_BETWEEN_STABS      = 1.5,

    -- Tuning
    SPEED                   = 26,
    TIME_ON_COIN            = 0.15,
    RETRY_AFTER             = 1.5,
    STOP_SHORT              = 0,
    HEIGHT_WEIGHT           = 1,
    CLUSTER_WEIGHT          = 0,
    CLUSTER_RADIUS          = 15,
    AVOID_MURDERER_RADIUS   = 35,
    START_DELAY             = 2,
    MAP_MARGIN              = 20,

    -- Contest
    CONTEST_RADIUS          = 15,
    TIME_MARGIN             = 0.7,
    TIE_MARGIN              = 1.15,

    -- Danger
    MURDER_SAFE             = 35,
    SHERIFF_SAFE            = 20,

    -- Physics
    COIN_REACH_XZ           = 3.0,   -- head-to-coin max XZ (loose, server is auth)
    COIN_REACH_Y            = 3.0,   -- head-to-coin max Y
}

-- ───────────────────────────────────────────────
-- STATE
-- ───────────────────────────────────────────────
-- v0.6: keyed by coin INSTANCE (weak table so GC'd coins drop out).
local visited        = setmetatable({}, {__mode = "k"})
local deferredUntil  = setmetatable({}, {__mode = "k"})
local parkedUntil    = 0
local parkedCoin     = nil
local tripTarget     = nil
local roundStartAt   = 0
local candiesThisRound = 0

local myRole         = "innocent"
local wasFarming     = false
local headOffset     = 1.5
local charParts      = {}
local coinContainer  = nil
local waitingLabel   = nil

local nextShotAt     = 0
local nextStabAt     = 0

local Remotes       = ReplicatedStorage:WaitForChild("Remotes")
local Gameplay      = Remotes:WaitForChild("Gameplay")
local CoinCollected = Gameplay:WaitForChild("CoinCollected")
local CoinsStarted  = Gameplay:WaitForChild("CoinsStarted")

-- Debug bus
_G.farmDebug = _G.farmDebug or {}
local DBG = _G.farmDebug
local lastLogAt = 0
local function dlog(msg)
    if not CONFIG.DEBUG_LOG then return end
    if os.clock() - lastLogAt < 0.25 then return end
    lastLogAt = os.clock()
    print("[farm] " .. msg)
end
local function dsync(key, value)
    if CONFIG.DEBUG_EXPOSE then DBG[key] = value end
end

-- ───────────────────────────────────────────────
-- Weapon helpers (role-based combat)
-- ───────────────────────────────────────────────
local function findHeldTool(nameMatchers)
    local char = lp.Character
    if not char then return nil end
    for _, t in ipairs(char:GetChildren()) do
        if t:IsA("Tool") then
            local n = t.Name:lower()
            for _, m in ipairs(nameMatchers) do
                if n:find(m) then return t end
            end
        end
    end
    return nil
end

local function tryShoot(targetHRP)
    if os.clock() < nextShotAt then return end
    local gun = findHeldTool({"gun", "revolver"})
    if not gun then return end
    local shoot = gun:FindFirstChild("Shoot")
    if not shoot or not shoot:IsA("RemoteEvent") then return end
    local hrp = lp.Character and lp.Character:FindFirstChild("HumanoidRootPart")
    if not hrp then return end
    local att = hrp:FindFirstChild("GunRaycastAttachment")
    local origin = att and att.WorldCFrame or (hrp.CFrame * CFrame.new(0, 0, -1))
    local targetCF = CFrame.new(targetHRP.Position)
    shoot:FireServer(origin, targetCF)
    nextShotAt = os.clock() + CONFIG.TIME_BETWEEN_SHOTS
end

local function tryStab()
    if os.clock() < nextStabAt then return end
    local knife = findHeldTool({"knife"})
    if not knife then return end
    local events = knife:FindFirstChild("Events")
    local evt = events and events:FindFirstChild("KnifeStabbed")
    if not evt or not evt:IsA("RemoteEvent") then return end
    evt:FireServer()
    nextStabAt = os.clock() + CONFIG.TIME_BETWEEN_STABS
end

-- ───────────────────────────────────────────────
-- Caches
-- ───────────────────────────────────────────────
local function cacheCoinContainer()
    coinContainer = nil
    for _, v in ipairs(workspace:GetChildren()) do
        local cc = v:FindFirstChild("CoinContainer")
        if cc then coinContainer = cc; return end
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
        if delta > 0 and delta < 5 then headOffset = delta end
    end
end

local function rebuildCharPartsCache(char)
    table.clear(charParts)
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") then table.insert(charParts, p) end
    end
end

-- ───────────────────────────────────────────────
-- Remote listeners
-- ───────────────────────────────────────────────
-- v0.6: CoinID is a type tag ("Candy"), not a unique id, so we only
-- count the pickup here. Per-coin dedup is handled by MM2's own
-- per-coin Collected attribute in getBestCoin.
CoinCollected.OnClientEvent:Connect(function(coinID, a2, a3, a4)
    candiesThisRound = candiesThisRound + 1
    dsync("candiesThisRound", candiesThisRound)
    dlog(("pickup: type=%s total=%d"):format(tostring(coinID), candiesThisRound))
end)

CoinsStarted.OnClientEvent:Connect(function()
    visited = setmetatable({}, {__mode = "k"})
    deferredUntil = setmetatable({}, {__mode = "k"})
    tripTarget = nil
    parkedCoin = nil
    parkedUntil = 0
    roundStartAt = os.clock()
    candiesThisRound = 0
    dlog("CoinsStarted: new round")
    dsync("candiesThisRound", 0)
end)

-- ───────────────────────────────────────────────
-- Character / noclip
-- ───────────────────────────────────────────────
local noclipConn
local function restoreCollision()
    for _, p in ipairs(charParts) do
        if p and p.Parent then p.CanCollide = true end
    end
end

local function onCharacter(char)
    char:WaitForChild("HumanoidRootPart", 5)
    refreshHeadOffset(char)
    rebuildCharPartsCache(char)
    cacheWaitingLabel()
    if noclipConn then noclipConn:Disconnect() end
    noclipConn = char.DescendantAdded:Connect(function(d)
        if d:IsA("BasePart") then
            table.insert(charParts, d)
            task.defer(function() if d.Parent then d.CanCollide = false end end)
        end
    end)
end

if lp.Character then onCharacter(lp.Character) end
lp.CharacterAdded:Connect(onCharacter)

cacheCoinContainer()
cacheWaitingLabel()

-- ───────────────────────────────────────────────
-- Gates
-- ───────────────────────────────────────────────
local function shouldFarm()
    if not CONFIG.FARM_COINS then return false end
    if waitingLabel == nil then cacheWaitingLabel() end
    if waitingLabel and waitingLabel.Visible then return false end
    if coinContainer == nil or coinContainer.Parent == nil then
        cacheCoinContainer()
    end
    if coinContainer == nil or #coinContainer:GetChildren() == 0 then
        return false
    end
    if roundStartAt > 0 and (os.clock() - roundStartAt) < CONFIG.START_DELAY then
        return false
    end
    return true
end

-- ───────────────────────────────────────────────
-- Role / danger
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

local function getWorldThreats()
    local threats, players = {}, {}
    local murderer
    for _, p in ipairs(Players:GetPlayers()) do
        if p ~= lp and p.Character then
            local hrp = p.Character:FindFirstChild("HumanoidRootPart")
            local hum = p.Character:FindFirstChildOfClass("Humanoid")
            if hrp and hum and hum.Health > 0 then
                table.insert(players, {p = p, hrp = hrp, hum = hum, speed = math.max(1, hum.WalkSpeed)})
                for _, t in ipairs(p.Character:GetChildren()) do
                    if t:IsA("Tool") then
                        local n = t.Name:lower()
                        if n:find("knife") then
                            murderer = {p = p, hrp = hrp, hum = hum}
                            table.insert(threats, { pos = hrp.Position, dist = CONFIG.MURDER_SAFE, kind = "murderer" })
                        elseif (n:find("gun") or n:find("sheriff") or n:find("revolver"))
                            and myRole == "innocent" then
                            table.insert(threats, { pos = hrp.Position, dist = CONFIG.SHERIFF_SAFE, kind = "sheriff" })
                        end
                    end
                end
            end
        end
    end
    return threats, murderer, players
end

local function isSafe(pos, threats)
    for _, d in ipairs(threats) do
        if (pos - d.pos).Magnitude < d.dist then return false end
    end
    return true
end

-- ───────────────────────────────────────────────
-- Map bbox
-- ───────────────────────────────────────────────
local function insideMap(pos)
    if CONFIG.MAP_MARGIN <= 0 or coinContainer == nil then return true end
    local parent = coinContainer.Parent
    if parent and parent:IsA("Model") then
        local ok, cf, size = pcall(parent.GetBoundingBox, parent)
        if ok then
            local corner = cf.Position
            local half = size / 2 + Vector3.new(1, 1, 1) * CONFIG.MAP_MARGIN
            local d = pos - corner
            if math.abs(d.X) <= half.X and math.abs(d.Y) <= half.Y and math.abs(d.Z) <= half.Z then
                return true
            end
            return false
        end
    end
    return true
end

-- ───────────────────────────────────────────────
-- Contest / coin scoring
-- ───────────────────────────────────────────────
local function arrivalTime(from, to, speed) return (from - to).Magnitude / speed end

local function winsContest(coinPos, myPos, mySpeed, players)
    if not CONFIG.CONTEST then return true end
    local ourTime = arrivalTime(myPos, coinPos, mySpeed)
    for _, pl in ipairs(players) do
        local theirTime = arrivalTime(pl.hrp.Position, coinPos, pl.speed)
        if theirTime < ourTime * CONFIG.TIME_MARGIN then return false end
        if theirTime < ourTime * CONFIG.TIE_MARGIN and pl.p.UserId < lp.UserId then
            return false
        end
    end
    return true
end

local function weightedDist(from, to)
    local dx, dz = to.X - from.X, to.Z - from.Z
    local dy = to.Y - from.Y
    return math.sqrt(dx*dx + dz*dz + (dy * CONFIG.HEIGHT_WEIGHT)^2)
end

local function clusterBonus(coinPos, allCoins)
    if CONFIG.CLUSTER_WEIGHT <= 0 then return 0 end
    local count = 0
    for _, c in ipairs(allCoins) do
        if c:IsA("BasePart") and c.Parent and (c.Position - coinPos).Magnitude < CONFIG.CLUSTER_RADIUS then
            count = count + 1
        end
    end
    return count * CONFIG.CLUSTER_WEIGHT
end

local function getBestCoin(myPos, mySpeed)
    local threats, murderer, players = getWorldThreats()
    local murdererPos = murderer and murderer.hrp.Position or nil
    local allCoins = CollectionService:GetTagged("CoinVisual")
    local bS, bSD = nil, math.huge
    local bA, bAD = nil, math.huge
    local now = os.clock()
    for _, coin in ipairs(allCoins) do
        local deferTs = deferredUntil[coin]
        if coin:IsA("BasePart")
            and coin.Parent
            and not coin:GetAttribute("Collected")
            and not coin:GetAttribute("RoundEnd")
            and not visited[coin]
            and (not deferTs or now >= deferTs)
        then
            local pos = coin.Position
            if insideMap(pos) then
                local inMurdererZone = murdererPos and (murdererPos - pos).Magnitude < CONFIG.AVOID_MURDERER_RADIUS
                local weWin = winsContest(pos, myPos, mySpeed, players)
                local score = weightedDist(myPos, pos) - clusterBonus(pos, allCoins)
                if isSafe(pos, threats) and not inMurdererZone and weWin then
                    if score < bSD then bS, bSD = coin, score end
                end
                if score < bAD then bA, bAD = coin, score end
            end
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
    restoreCollision()
    parkedCoin = nil
    parkedUntil = 0
    tripTarget = nil
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
    local head = char and char:FindFirstChild("Head")
    if not hum or not hrp or hum.Health <= 0 then return end

    if not shouldFarm() then
        if wasFarming then
            stopFarm(char, hrp, hum)
            wasFarming = false
        end
        return
    end

    if not wasFarming then
        wasFarming = true
        myRole     = getMyRole()
        refreshHeadOffset(char)
        rebuildCharPartsCache(char)
        dlog(("ENGAGE: role=%s head=%.2f parts=%d"):format(myRole, headOffset, #charParts))
        dsync("myRole", myRole)
        dsync("wasFarming", true)
        dsync("headOffset", headOffset)
    end

    hum.PlatformStand = true

    -- Per-frame noclip over cache (cheap).
    for _, p in ipairs(charParts) do
        if p.Parent then p.CanCollide = false end
    end

    local bv       = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
    local myPos    = hrp.Position
    local mySpeed  = math.max(1, hum.WalkSpeed)
    local threats, murderer, _ = getWorldThreats()

    -- ─── COMBAT MODE (candies threshold reached) ───
    if candiesThisRound >= CONFIG.COMBAT_AT_CANDIES then
        -- Sheriff: shoot the murderer when in range, straight line of sight ignored
        if myRole == "sheriff" and murderer then
            local mhrp = murderer.hrp
            local toM = (mhrp.Position - myPos)
            local dist = toM.Magnitude
            if dist <= CONFIG.SHERIFF_SHOOT_RANGE then
                -- Face and fire
                hrp.CFrame = CFrame.new(myPos, Vector3.new(mhrp.Position.X, myPos.Y, mhrp.Position.Z))
                tryShoot(mhrp)
                bv.Velocity = Vector3.zero
                return
            end
        end
        -- Murderer: chase nearest player and stab
        if myRole == "murderer" then
            local best, bestD = nil, math.huge
            for _, pl in ipairs(Players:GetPlayers()) do
                if pl ~= lp and pl.Character then
                    local phrp = pl.Character:FindFirstChild("HumanoidRootPart")
                    local phum = pl.Character:FindFirstChildOfClass("Humanoid")
                    if phrp and phum and phum.Health > 0 then
                        local d = (phrp.Position - myPos).Magnitude
                        if d < bestD then best, bestD = phrp, d end
                    end
                end
            end
            if best then
                if bestD <= CONFIG.STAB_RANGE then
                    hrp.CFrame = CFrame.new(best.Position)
                    tryStab()
                    bv.Velocity = Vector3.zero
                    return
                else
                    local diff = best.Position - myPos
                    local step = math.min(diff.Magnitude, CONFIG.SPEED * dt)
                    hrp.CFrame = CFrame.new(myPos + diff.Unit * step)
                    bv.Velocity = Vector3.zero
                    return
                end
            end
        end
    end

    -- Immediate personal danger
    for _, d in ipairs(threats) do
        if (myPos - d.pos).Magnitude < d.dist * 0.6 then
            local away = myPos - d.pos
            if away.Magnitude > 0 then
                hrp.CFrame = CFrame.new(myPos + away.Unit * CONFIG.SPEED * dt)
            end
            bv.Velocity = Vector3.zero
            parkedCoin, parkedUntil, tripTarget = nil, 0, nil
            return
        end
    end

    -- Parked (waiting for server-side Collected flag)
    if parkedCoin and os.clock() < parkedUntil then
        if (not parkedCoin.Parent) or parkedCoin:GetAttribute("Collected") then
            -- The server confirmed and either marked collected or destroyed it.
            visited[parkedCoin] = true
            parkedCoin, parkedUntil = nil, 0
        else
            bv.Velocity = Vector3.zero
            return
        end
    elseif parkedCoin then
        -- Park window elapsed without confirmation -> defer this specific coin
        -- instance and move on to the next.
        if parkedCoin.Parent and not parkedCoin:GetAttribute("Collected") then
            deferredUntil[parkedCoin] = os.clock() + CONFIG.RETRY_AFTER
        else
            visited[parkedCoin] = true
        end
        parkedCoin, parkedUntil = nil, 0
    end

    -- Pick a coin
    local coin = getBestCoin(myPos, mySpeed)
    if not coin then
        bv.Velocity = Vector3.zero
        tripTarget = nil
        dsync("tripCoinID", "none")
        dlog("no coin available")
        return
    end

    -- Abort trip if murderer entered target's zone
    if CONFIG.ABORT_IF_MURDERER_NEAR and tripTarget == coin and murderer then
        if (murderer.hrp.Position - coin.Position).Magnitude < CONFIG.AVOID_MURDERER_RADIUS then
            deferredUntil[coin] = os.clock() + CONFIG.RETRY_AFTER
            tripTarget = nil
            bv.Velocity = Vector3.zero
            return
        end
    end

    if tripTarget ~= coin then
        tripTarget = coin
        dsync("tripCoinID", coin:GetAttribute("CoinID"))
    end

    -- v0.5 PICKUP: always target coin.Y - headOffset so the head
    -- physically overlaps the CoinVisual's hitbox regardless of
    -- whether the coin is above or below the character. The old
    -- STAND_ON_FLOOR clamp broke pickup for any coin below the char.
    local targetY = coin.Position.Y - headOffset
    if CONFIG.STAND_ON_FLOOR then
        if targetY < myPos.Y - 1.5 then
            deferredUntil[coin] = os.clock() + CONFIG.RETRY_AFTER
            tripTarget = nil
            bv.Velocity = Vector3.zero
            return
        end
    end
    local target = Vector3.new(coin.Position.X, targetY, coin.Position.Z)

    if CONFIG.STOP_SHORT > 0 then
        local dir = target - myPos
        if dir.Magnitude > CONFIG.STOP_SHORT then
            target = target - dir.Unit * CONFIG.STOP_SHORT
        end
    end

    -- Measure HEAD distance to coin for pickup detection (not HRP target).
    local headPos = head and head.Position or (myPos + Vector3.new(0, headOffset, 0))
    local toCoin  = coin.Position - headPos
    local dXZ     = math.sqrt(toCoin.X^2 + toCoin.Z^2)
    local dY      = math.abs(toCoin.Y)
    if dXZ < CONFIG.COIN_REACH_XZ and dY < CONFIG.COIN_REACH_Y then
        hrp.CFrame  = CFrame.new(target)
        bv.Velocity = Vector3.zero
        parkedCoin  = coin
        parkedUntil = os.clock() + CONFIG.TIME_ON_COIN
        dsync("parkedCoinID", coin:GetAttribute("CoinID"))
        return
    end

    local diff = target - myPos
    local step = math.min(diff.Magnitude, CONFIG.SPEED * dt)
    hrp.CFrame  = CFrame.new(myPos + diff.Unit * step)
    bv.Velocity = Vector3.zero
    dsync("lastDecisionAt", os.clock())
end)
