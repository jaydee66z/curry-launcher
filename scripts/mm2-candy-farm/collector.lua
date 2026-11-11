--[[
    MM2 CANDY FARM — v0.3 (Curry Launcher)
    ======================================
    v0.3 CHANGES vs v0.2:
    - NOCLIP RELIABILITY: character parts cached in a table and
      CanCollide=false re-applied every frame over the cache (cheap). MM2
      can flip CanCollide back on humanoid state transitions; this keeps
      us phased through walls between coins.
    - STAND_ON_FLOOR mode: HRP sits at normal height (feet on floor) on
      arrival; we confirm pickup by proximity on the horizontal plane
      instead of sinking the body into the ground. Reduces kick detection.
    - TIME_ON_COIN / RETRY_AFTER: we park on a coin briefly so the
      server-side touch fires and CoinCollected confirms; if it doesn't
      confirm, the coin is deferred for RETRY_AFTER seconds.
    - STOP_SHORT: optional XZ offset when arriving at a coin (0 = land on
      it), anti-overshoot on fast rigs.
    - CLUSTER + HEIGHT WEIGHTS: coin scoring now weights Y-distance and
      awards bonus when the coin has neighbours within 15 studs.
    - AVOID_MURDERER_RADIUS: coins within this many studs of the murderer
      are skipped (not just we-flee-from-them).
    - CONTEST: when enabled we compute each live player's arrival time
      based on their walkspeed and current position; if any player would
      touch the coin significantly faster than us (TIME_MARGIN), we skip.
      Ties broken by lower UserId.
    - ABORT_IF_MURDERER_NEAR: an active trip is aborted and the coin
      deferred if a murderer enters the avoid radius mid-trip.
    - START_DELAY: wait N seconds after round start before engaging, to
      avoid teleporting into a server race.
    - MAP_MARGIN: coins beyond this distance from the map's bounding box
      are rejected (map-specific clean-up).

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
-- CONFIG — every knob from the reference bot's Features/Tuning/Contest
-- panels, minus the Gun / Murderer / Event / Webhook modules which live
-- in their own scripts.
-- ───────────────────────────────────────────────
local CONFIG = {
    -- Features
    FARM_COINS              = true,  -- master switch (turn off = idle in round, no pickup)
    STAND_ON_FLOOR          = true,  -- normal height at coin vs cabeza-on-coin (anti-kick)
    ABORT_IF_MURDERER_NEAR  = true,  -- cancel trip when murderer enters radius
    CONTEST                 = true,  -- skip coins another player will clearly get first
    LEAVE_FOR_OTHER_BOTS    = false, -- leave nearest coins to friendly bots

    -- Tuning
    SPEED                   = 26,
    TIME_ON_COIN            = 0.15,   -- sec parked on coin to let server confirm
    RETRY_AFTER             = 1.5,    -- sec to ignore an unconfirmed coin
    STOP_SHORT              = 0,      -- studs to stop short of coin (0 = right on it)
    HEIGHT_WEIGHT           = 1,      -- extra weight on Y delta (1 = plain euclid)
    CLUSTER_WEIGHT          = 0,      -- bonus for coins with neighbours (0 = off)
    CLUSTER_RADIUS          = 15,     -- studs considered neighbouring
    AVOID_MURDERER_RADIUS   = 35,     -- skip coins this close to a knife
    START_DELAY             = 2,      -- sec to wait after round start
    MAP_MARGIN              = 20,     -- studs beyond map bbox still "inside"

    -- Contest
    CONTEST_RADIUS          = 15,     -- distance-mode fallback
    TIME_MARGIN             = 0.7,    -- skip if other arrives under this * ourTime
    TIE_MARGIN              = 1.15,   -- near-tie -> lower UserId wins

    -- Danger
    MURDER_SAFE             = 35,
    SHERIFF_SAFE            = 20,

    -- Physics
    COIN_REACH              = 2.0,    -- XZ radius (floor mode) / 3D (head mode)
}

-- ───────────────────────────────────────────────
-- STATE
-- ───────────────────────────────────────────────
local visited      = {}     -- coinID -> true (cleared on CoinsStarted)
local deferredUntil = {}    -- coinID -> os.clock() to retry after
local parkedUntil  = 0      -- epoch when current park ends
local parkedCoin   = nil    -- coin currently being stood on
local tripTarget   = nil    -- current trip's coin (for abort logic)
local roundStartAt = 0      -- os.clock() when CoinsStarted fired

local myRole       = "innocent"
local wasFarming   = false
local headOffset   = 1.5    -- refreshed per character
local charParts    = {}     -- cached array of character BaseParts
local coinContainer = nil
local waitingLabel  = nil

local Remotes       = ReplicatedStorage:WaitForChild("Remotes")
local Gameplay      = Remotes:WaitForChild("Gameplay")
local CoinCollected = Gameplay:WaitForChild("CoinCollected")
local CoinsStarted  = Gameplay:WaitForChild("CoinsStarted")

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
CoinCollected.OnClientEvent:Connect(function(coinID)
    if coinID ~= nil then
        visited[coinID] = true
        deferredUntil[coinID] = nil
        if tripTarget and tripTarget:GetAttribute("CoinID") == coinID then
            tripTarget = nil
        end
    end
end)

CoinsStarted.OnClientEvent:Connect(function()
    visited = {}
    deferredUntil = {}
    tripTarget = nil
    parkedCoin = nil
    parkedUntil = 0
    roundStartAt = os.clock()
    cacheCoinContainer()
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
    -- START_DELAY after round start
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

-- Returns {threats = {{pos, dist}, ...}, murdererPos = Vector3 or nil, players = {{p=Player,hrp=BasePart,speed=number}}}
local function getWorldThreats()
    local threats, players = {}, {}
    local murdererPos
    for _, p in ipairs(Players:GetPlayers()) do
        if p ~= lp and p.Character then
            local hrp = p.Character:FindFirstChild("HumanoidRootPart")
            local hum = p.Character:FindFirstChildOfClass("Humanoid")
            if hrp and hum and hum.Health > 0 then
                table.insert(players, {p = p, hrp = hrp, speed = math.max(1, hum.WalkSpeed)})
                for _, t in ipairs(p.Character:GetChildren()) do
                    if t:IsA("Tool") then
                        local n = t.Name:lower()
                        if n:find("knife") then
                            murdererPos = hrp.Position
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
    return threats, murdererPos, players
end

local function isSafe(pos, threats)
    for _, d in ipairs(threats) do
        if (pos - d.pos).Magnitude < d.dist then return false end
    end
    return true
end

-- ───────────────────────────────────────────────
-- Map bbox (for MAP_MARGIN filter)
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
local function arrivalTime(from, to, speed)
    return (from - to).Magnitude / speed
end

-- Returns true if WE will clearly reach coinPos first vs other players.
local function winsContest(coinPos, myPos, mySpeed, players)
    if not CONFIG.CONTEST then return true end
    local ourTime = arrivalTime(myPos, coinPos, mySpeed)
    for _, pl in ipairs(players) do
        local theirPos = pl.hrp.Position
        local theirTime = arrivalTime(theirPos, coinPos, pl.speed)
        -- Clear win for them
        if theirTime < ourTime * CONFIG.TIME_MARGIN then
            return false
        end
        -- Tie -> lower UserId wins
        if theirTime < ourTime * CONFIG.TIE_MARGIN and pl.p.UserId < lp.UserId then
            return false
        end
    end
    -- Distance-mode fallback (if speeds equal or missing)
    if not CONFIG.CONTEST then return true end
    return true
end

-- Weighted distance: XZ + Y * HEIGHT_WEIGHT
local function weightedDist(from, to)
    local dx, dz = to.X - from.X, to.Z - from.Z
    local dy = to.Y - from.Y
    return math.sqrt(dx*dx + dz*dz + (dy * CONFIG.HEIGHT_WEIGHT)^2)
end

-- Cluster bonus: how many coins within CLUSTER_RADIUS of coinPos
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
    local threats, murdererPos, players = getWorldThreats()
    local allCoins = CollectionService:GetTagged("CoinVisual")
    local bS, bSD = nil, math.huge
    local bA, bAD = nil, math.huge
    local now = os.clock()
    for _, coin in ipairs(allCoins) do
        local coinID = coin:GetAttribute("CoinID")
        local deferTs = coinID and deferredUntil[coinID]
        if coin:IsA("BasePart")
            and coin.Parent
            and not coin:GetAttribute("Collected")
            and not coin:GetAttribute("RoundEnd")
            and not (coinID and visited[coinID])
            and (not deferTs or now >= deferTs)
        then
            local pos = coin.Position
            if insideMap(pos) then
                -- AVOID_MURDERER_RADIUS: skip if coin itself is in murderer bubble
                local inMurdererZone = murdererPos and (murdererPos - pos).Magnitude < CONFIG.AVOID_MURDERER_RADIUS
                -- CONTEST: skip if another player will reach first
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
    end

    hum.PlatformStand = true

    -- Re-apply noclip over cached parts (cheap — no GetDescendants).
    for _, p in ipairs(charParts) do
        if p.Parent then p.CanCollide = false end
    end

    local bv       = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
    local myPos    = hrp.Position
    local mySpeed  = math.max(1, hum.WalkSpeed)
    local threats, murdererPos, _ = getWorldThreats()

    -- Immediate personal danger (we're inside a threat's bubble)
    for _, d in ipairs(threats) do
        if (myPos - d.pos).Magnitude < d.dist * 0.6 then
            local away = myPos - d.pos
            if away.Magnitude > 0 then
                hrp.CFrame = CFrame.new(myPos + away.Unit * CONFIG.SPEED * dt)
            end
            bv.Velocity = Vector3.zero
            parkedCoin = nil
            parkedUntil = 0
            tripTarget = nil
            return
        end
    end

    -- If parked on a coin, hold position until TIME_ON_COIN elapses or the
    -- server confirms (visited is set by the remote listener).
    if parkedCoin and os.clock() < parkedUntil then
        local coinID = parkedCoin:GetAttribute("CoinID")
        if coinID and visited[coinID] then
            parkedCoin = nil
            parkedUntil = 0
        else
            bv.Velocity = Vector3.zero
            return
        end
    elseif parkedCoin then
        -- Park expired without confirmation -> defer this coin
        local coinID = parkedCoin:GetAttribute("CoinID")
        if coinID and not visited[coinID] then
            deferredUntil[coinID] = os.clock() + CONFIG.RETRY_AFTER
        end
        parkedCoin = nil
        parkedUntil = 0
    end

    -- Pick a coin
    local coin = getBestCoin(myPos, mySpeed)
    if not coin then
        bv.Velocity = Vector3.zero
        tripTarget = nil
        return
    end

    -- ABORT_IF_MURDERER_NEAR: if we are already en route and a murderer
    -- entered the coin's avoid radius, defer and bail.
    if CONFIG.ABORT_IF_MURDERER_NEAR and tripTarget == coin and murdererPos then
        if (murdererPos - coin.Position).Magnitude < CONFIG.AVOID_MURDERER_RADIUS then
            local coinID = coin:GetAttribute("CoinID")
            if coinID then deferredUntil[coinID] = os.clock() + CONFIG.RETRY_AFTER end
            tripTarget = nil
            bv.Velocity = Vector3.zero
            return
        end
    end

    tripTarget = coin

    -- Compute target. STAND_ON_FLOOR keeps HRP at normal height;
    -- otherwise we drop HRP by headOffset so the head collides with the coin.
    local target
    if CONFIG.STAND_ON_FLOOR then
        target = Vector3.new(coin.Position.X, myPos.Y, coin.Position.Z)
    else
        target = Vector3.new(coin.Position.X, coin.Position.Y - headOffset, coin.Position.Z)
    end

    -- Optional STOP_SHORT: back off along the approach vector
    if CONFIG.STOP_SHORT > 0 then
        local dir = target - myPos
        if dir.Magnitude > CONFIG.STOP_SHORT then
            target = target - dir.Unit * CONFIG.STOP_SHORT
        end
    end

    local diff = target - myPos
    local dist = diff.Magnitude

    if dist < CONFIG.COIN_REACH then
        hrp.CFrame  = CFrame.new(target)
        bv.Velocity = Vector3.zero
        -- Park on coin so the server has a window to register the touch.
        parkedCoin  = coin
        parkedUntil = os.clock() + CONFIG.TIME_ON_COIN
        return
    end

    local step = math.min(dist, CONFIG.SPEED * dt)
    hrp.CFrame  = CFrame.new(myPos + diff.Unit * step)
    bv.Velocity = Vector3.zero
end)
