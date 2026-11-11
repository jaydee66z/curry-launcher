--[[
    MM2 CANDY FARM — v0.11 (Curry Launcher)
    =======================================
    v0.11 FULL REWRITE — physics-based movement, no CFrame teleports.

    Lessons from v0.1-v0.10:
    - CFrame teleports do NOT fire the server's Touched handler on
      Coin_Server (verified live: teleporting HRP directly onto a
      coin and waiting 3.5s produced zero pickups).
    - AC "Invalid position" (code 267) kicks the account the moment
      position-delta per server tick exceeds walkspeed validation.
      Any CFrame write that exceeds mod * walkspeed * tick_interval
      will eventually trip it.
    - PlatformStand + BodyVelocity breaks the standard humanoid
      replication path, which is how MM2's pickup fires.

    Correct approach (this version):
    - Humanoid:MoveTo(target) every frame toward the current coin.
    - WalkSpeed cranked (default 40) — server validates vs this value.
    - Noclip via per-frame CanCollide=false on every part on
      RunService.Stepped (pre-physics) — the character walks THROUGH
      walls normally; `.Touched` still fires on Coin_Server.
    - NO PlatformStand, NO BodyVelocity, NO CFrame writes to HRP.
    - Hover handled by setting Humanoid.HipHeight so the character
      floats to the coin's Y naturally, respecting the humanoid's
      own replication smoothing (AC-safe).
    - Jump when coin is well above character (JUMP_HEIGHT_DELTA).
    - CoinsStarted resets per-round state; per-coin attempt counter
      keeps us from looping on unreachable candies.

    Kill switch: `running = false` (also wipes _G.farmDebug).
]]

running = false
task.wait(0.4)

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
    ABORT_IF_MURDERER_NEAR  = true,
    DEBUG_LOG               = true,
    DEBUG_EXPOSE            = true,

    -- Combat
    COMBAT_AT_CANDIES       = 50,
    SHERIFF_SHOOT_RANGE     = 60,
    TIME_BETWEEN_SHOTS      = 3.4,
    STAB_RANGE              = 12,
    TIME_BETWEEN_STABS      = 1.5,

    -- Movement (v0.11 physics-based)
    WALK_SPEED              = 40,      -- bumped from default 16 (AC-safe <= 60)
    HIP_HEIGHT              = 2.0,     -- default humanoid hover above floor
    JUMP_HEIGHT_DELTA       = 6,       -- coin this far above HRP triggers jump
    PICK_RADIUS             = 4,       -- consider "touched" if HRP within this
    STUCK_TIMEOUT           = 2.0,     -- same target this long, bury it
    MAX_ATTEMPTS            = 1,
    RETRY_AFTER             = 0.5,
    START_DELAY             = 2,
    MAP_MARGIN              = 20,

    -- Danger / contest
    AVOID_MURDERER_RADIUS   = 35,
    MURDER_SAFE             = 30,
    SHERIFF_SAFE            = 20,
    CONTEST                 = true,
    CONTEST_RADIUS          = 15,
    TIME_MARGIN             = 0.7,
    TIE_MARGIN              = 1.15,
    HEIGHT_WEIGHT           = 1,
}

-- ───────────────────────────────────────────────
-- STATE
-- ───────────────────────────────────────────────
local visited        = setmetatable({}, {__mode = "k"})
local deferredUntil  = setmetatable({}, {__mode = "k"})
local attempts       = setmetatable({}, {__mode = "k"})
local tripTarget     = nil
local tripSince      = 0
local tripPickupBase = 0
local lastJumpAt     = 0
local roundStartAt   = 0
local candiesThisRound = 0

local myRole         = "innocent"
local wasFarming     = false
local coinContainer  = nil
local waitingLabel   = nil
local defaultWalkSpeed = 16
local defaultHipHeight = 2
local defaultAutoRotate = true

local nextShotAt     = 0
local nextStabAt     = 0

local Remotes       = ReplicatedStorage:WaitForChild("Remotes")
local Gameplay      = Remotes:WaitForChild("Gameplay")
local CoinCollected = Gameplay:WaitForChild("CoinCollected")
local CoinsStarted  = Gameplay:WaitForChild("CoinsStarted")

_G.farmDebug = _G.farmDebug or {}
local DBG = _G.farmDebug
local lastLogAt = 0
local function dlog(msg)
    if not CONFIG.DEBUG_LOG then return end
    if os.clock() - lastLogAt < 0.25 then return end
    lastLogAt = os.clock()
    print("[farm] " .. msg)
end
local function dsync(k, v) if CONFIG.DEBUG_EXPOSE then DBG[k] = v end end

-- ───────────────────────────────────────────────
-- Weapon helpers
-- ───────────────────────────────────────────────
local function findHeldTool(matchers)
    local char = lp.Character
    if not char then return nil end
    for _, t in ipairs(char:GetChildren()) do
        if t:IsA("Tool") then
            local n = t.Name:lower()
            for _, m in ipairs(matchers) do
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

-- ───────────────────────────────────────────────
-- Remote listeners
-- ───────────────────────────────────────────────
CoinCollected.OnClientEvent:Connect(function(coinID)
    candiesThisRound = candiesThisRound + 1
    dsync("candiesThisRound", candiesThisRound)
    dlog(("pickup type=%s total=%d"):format(tostring(coinID), candiesThisRound))
end)

CoinsStarted.OnClientEvent:Connect(function()
    visited = setmetatable({}, {__mode = "k"})
    deferredUntil = setmetatable({}, {__mode = "k"})
    attempts = setmetatable({}, {__mode = "k"})
    tripTarget, tripSince, tripPickupBase = nil, 0, 0
    roundStartAt = os.clock()
    candiesThisRound = 0
    dsync("candiesThisRound", 0)
    dlog("CoinsStarted: new round")
end)

-- ───────────────────────────────────────────────
-- Character / noclip
-- ───────────────────────────────────────────────
local noclipStepConn

-- v0.11 noclip: pre-physics, iterates every part live. Humanoid walking
-- still works because humanoid only needs any collidable part under
-- the hip-height raycast to stand on — but with ALL CanCollide=false,
-- the character floats on the humanoid's own HipHeight logic through
-- any geometry.
local function noclipStep()
    if not running or not wasFarming then return end
    local char = lp.Character
    if not char then return end
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") and p.CanCollide then
            p.CanCollide = false
        end
    end
end

local function saveDefaults(hum)
    defaultWalkSpeed = hum.WalkSpeed
    defaultHipHeight = hum.HipHeight
    defaultAutoRotate = hum.AutoRotate
end

local function applyFarmTuning(hum)
    hum.WalkSpeed  = CONFIG.WALK_SPEED
    hum.HipHeight  = CONFIG.HIP_HEIGHT
    hum.AutoRotate = true
end

local function restoreDefaults(hum)
    if not hum then return end
    hum.WalkSpeed  = defaultWalkSpeed
    hum.HipHeight  = defaultHipHeight
    hum.AutoRotate = defaultAutoRotate
end

local function onCharacter(char)
    char:WaitForChild("HumanoidRootPart", 5)
    cacheWaitingLabel()
    tripTarget, tripSince, tripPickupBase = nil, 0, 0
    wasFarming = false
    local hum = char:FindFirstChildOfClass("Humanoid")
    if hum then saveDefaults(hum) end
end

if lp.Character then onCharacter(lp.Character) end
lp.CharacterAdded:Connect(onCharacter)

cacheCoinContainer()
cacheWaitingLabel()

if noclipStepConn then noclipStepConn:Disconnect() end
noclipStepConn = RNS.Stepped:Connect(noclipStep)

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
        local r = scan(lp.Character); if r then return r end
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
                table.insert(players, {p=p, hrp=hrp, hum=hum, speed=math.max(1, hum.WalkSpeed)})
                for _, t in ipairs(p.Character:GetChildren()) do
                    if t:IsA("Tool") then
                        local n = t.Name:lower()
                        if n:find("knife") then
                            murderer = {p=p, hrp=hrp, hum=hum}
                            table.insert(threats, {pos=hrp.Position, dist=CONFIG.MURDER_SAFE, kind="murderer"})
                        elseif (n:find("gun") or n:find("sheriff") or n:find("revolver"))
                            and myRole == "innocent" then
                            table.insert(threats, {pos=hrp.Position, dist=CONFIG.SHERIFF_SAFE, kind="sheriff"})
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
            local c = cf.Position
            local h = size / 2 + Vector3.new(1, 1, 1) * CONFIG.MAP_MARGIN
            local d = pos - c
            if math.abs(d.X) <= h.X and math.abs(d.Y) <= h.Y and math.abs(d.Z) <= h.Z then
                return true
            end
            return false
        end
    end
    return true
end

-- ───────────────────────────────────────────────
-- Coin scoring
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

-- v0.11: iterate Coin_Server (the Part with TouchInterest) via its
-- child CoinVisual (which carries the CollectionService tag).
local function getBestCoin(myPos, mySpeed)
    local threats, murderer, players = getWorldThreats()
    local murdererPos = murderer and murderer.hrp.Position or nil
    local allVisuals = CollectionService:GetTagged("CoinVisual")
    local best, bestScore = nil, math.huge
    local now = os.clock()
    for _, visual in ipairs(allVisuals) do
        local serverPart = visual.Parent  -- Coin_Server (actual pickup target)
        if serverPart and serverPart:IsA("BasePart")
            and not visual:GetAttribute("Collected")
            and not visual:GetAttribute("RoundEnd")
            and not visited[serverPart]
            and (not deferredUntil[serverPart] or now >= deferredUntil[serverPart])
        then
            local pos = serverPart.Position
            if insideMap(pos) then
                local inMurdererZone = murdererPos and (murdererPos - pos).Magnitude < CONFIG.AVOID_MURDERER_RADIUS
                local weWin = winsContest(pos, myPos, mySpeed, players)
                local score = weightedDist(myPos, pos)
                if isSafe(pos, threats) and not inMurdererZone and weWin then
                    if score < bestScore then best, bestScore = serverPart, score end
                end
            end
        end
    end
    return best
end

-- ───────────────────────────────────────────────
-- Farm stop (restore on round end / death)
-- ───────────────────────────────────────────────
local function stopFarm()
    local char = lp.Character
    local hum  = char and char:FindFirstChildOfClass("Humanoid")
    if hum then restoreDefaults(hum) end
    tripTarget, tripSince, tripPickupBase = nil, 0, 0
end

-- ───────────────────────────────────────────────
-- HEARTBEAT (decision + MoveTo)
-- ───────────────────────────────────────────────
local farmConn
farmConn = RNS.Heartbeat:Connect(function()
    if not running then
        farmConn:Disconnect()
        if noclipStepConn then noclipStepConn:Disconnect() end
        stopFarm()
        return
    end

    local char = lp.Character
    local hum  = char and char:FindFirstChildOfClass("Humanoid")
    local hrp  = char and char:FindFirstChild("HumanoidRootPart")
    if not hum or not hrp or hum.Health <= 0 then return end

    if not shouldFarm() then
        if wasFarming then
            stopFarm()
            wasFarming = false
            dsync("wasFarming", false)
        end
        return
    end

    if not wasFarming then
        wasFarming = true
        myRole     = getMyRole()
        saveDefaults(hum)
        applyFarmTuning(hum)
        dlog(("ENGAGE: role=%s speed=%d"):format(myRole, CONFIG.WALK_SPEED))
        dsync("myRole", myRole)
        dsync("wasFarming", true)
    end

    local myPos    = hrp.Position
    local mySpeed  = math.max(1, hum.WalkSpeed)
    local threats, murderer = getWorldThreats()

    -- ─── COMBAT MODE ───
    if candiesThisRound >= CONFIG.COMBAT_AT_CANDIES then
        if myRole == "sheriff" and murderer then
            local mhrp = murderer.hrp
            local dist = (mhrp.Position - myPos).Magnitude
            if dist <= CONFIG.SHERIFF_SHOOT_RANGE then
                hum:MoveTo(myPos)  -- stand still (MoveTo to self)
                tryShoot(mhrp)
                return
            end
        end
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
                    hum:MoveTo(myPos)
                    tryStab()
                else
                    hum:MoveTo(best.Position)
                end
                return
            end
        end
    end

    -- Immediate personal danger → walk away
    for _, d in ipairs(threats) do
        if (myPos - d.pos).Magnitude < d.dist * 0.6 then
            local away = (myPos - d.pos)
            if away.Magnitude > 0 then
                hum:MoveTo(myPos + away.Unit * 20)
            end
            tripTarget = nil
            return
        end
    end

    -- Pick a coin (operating on Coin_Server parts)
    local coin = getBestCoin(myPos, mySpeed)
    if not coin then
        hum:MoveTo(myPos)
        tripTarget = nil
        dsync("tripCoinID", "none")
        return
    end

    -- Abort trip if murderer entered target's zone
    if CONFIG.ABORT_IF_MURDERER_NEAR and tripTarget == coin and murderer then
        if (murderer.hrp.Position - coin.Position).Magnitude < CONFIG.AVOID_MURDERER_RADIUS then
            deferredUntil[coin] = os.clock() + CONFIG.RETRY_AFTER
            tripTarget = nil
            return
        end
    end

    if tripTarget ~= coin then
        tripTarget = coin
        tripSince  = os.clock()
        tripPickupBase = candiesThisRound
        dsync("tripCoinID", coin:GetAttribute("CoinID") or coin.Name)
    else
        -- Watchdog: same target too long, no pickup → bury it
        if (os.clock() - tripSince) > CONFIG.STUCK_TIMEOUT
            and candiesThisRound == tripPickupBase then
            local n = (attempts[coin] or 0) + 1
            attempts[coin] = n
            if n >= CONFIG.MAX_ATTEMPTS then
                visited[coin] = true
                dlog("discard: stuck timeout")
            else
                deferredUntil[coin] = os.clock() + CONFIG.RETRY_AFTER
            end
            tripTarget = nil
            return
        end
    end

    -- If we're inside pickup radius, the Touched already fires naturally
    -- as the humanoid stands on/near the coin. Just hold position briefly
    -- so the server can register.
    local toCoin = coin.Position - myPos
    local dist   = toCoin.Magnitude
    if dist < CONFIG.PICK_RADIUS then
        hum:MoveTo(coin.Position)  -- continue toward exact spot
        return
    end

    -- Jump if coin is well above us (candy on ledges/shelves)
    if toCoin.Y > CONFIG.JUMP_HEIGHT_DELTA
       and (os.clock() - lastJumpAt) > 0.9
       and hum.FloorMaterial ~= Enum.Material.Air then
        hum.Jump = true
        lastJumpAt = os.clock()
    end

    -- Walk toward coin. The humanoid handles pathing + replication.
    hum:MoveTo(coin.Position)
    dsync("lastDecisionAt", os.clock())
end)
