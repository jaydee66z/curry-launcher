--[[
    MM2 CANDY FARM — v0.15 (Curry Launcher)
    =======================================
    v0.15 HUMANIZED MOVEMENT (operator feedback — AC kick from
    inconsistent motion):
    - FORCE_WALKSPEED=26 on the Humanoid so the server's speed
      validator sees exactly what our CFrame cadence produces
      (SPEED * dt per frame). Mismatch between the Humanoid's
      declared speed and our actual position delta is a classic
      "Invalid position" trigger.
    - MAX_FRAME_STEP tightened 1.1 -> 0.5 (~SPEED/60) for smoother
      visual flow and more granular position updates to the server.
    - Direction smoothing: smoothDir := lerp(smoothDir, newDir,
      DIR_SMOOTH=0.25) so pivots between coins ease in instead of
      snapping — looks less botty.
    - CFrame.lookAt in safeMove orients HRP toward the move
      direction (character actually faces where it's going).
    - AssemblyLinearVelocity synced to the position delta so the
      server's physics replicator sees matching velocity.
    - stopFarm restores WalkSpeed=16 so lobby feels normal.

    v0.14 PICKUP BREAKTHROUGH:
    - Reverse-engineered MM2's pickup remote: ReplicatedStorage.Remotes
      .Gameplay.GetCoin. Signature: GetCoin:FireServer(coinServerPart).
    - Verified live: firing it with the Coin_Server Part as arg sets
      Collected=true immediately (server acknowledges pickup).
    - We no longer need the server's .Touched handler (it wasn't
      firing from CFrame teleports anyway). The collector now moves
      near the coin at SPEED=26 and fires GetCoin directly when within
      PICK_FIRE_RADIUS. The remote replaces the park/wait-for-Touched
      loop entirely.
    - Per-coin fire budget (one fire per coin, retry only if server
      didn't set Collected within FIRE_CONFIRM_TIMEOUT).

    v0.13 OPERATOR FIX:
    - Combat disabled (COMBAT_ENABLED=false). Sheriff/murderer don't
      shoot or stab; we just farm candies the whole round.
    - Movement aims HRP EXACTLY at coin.Position so the Upper/Lower
      Torso (both centered on HRP) physically overlap the coin.
      Previous versions aimed at coin.Y - headOffset which put the
      head at the coin but torso below — some candies did not count.
    - Hard snap HRP to coin.Position on reach (SNAP_ON_REACH=true).
      Jump is < COIN_PICK_RADIUS (1.5) << MAX_JUMP (25), AC-safe.
    - COIN_PICK_RADIUS tightened 3.0 → 1.5 so we actually LAND on
      the coin before parking instead of giving up 3 studs short.
    - TIME_ON_COIN raised 0.2 → 0.5 so the server has time to register
      the pickup before we abandon.
    - MAX_ATTEMPTS raised 2 → 3 so we retry a coin a few times before
      giving up (some candies take two park cycles to confirm).

    v0.12: operator feedback — CFrame-based movement was working,
    v0.10 blew it up with SPEED=60 (effective 100+). The normal
    reference-bot speed is 26. Going back to the v0.9 model
    (PlatformStand + hover BV + CFrame step) at SPEED=26 and
    targeting Coin_Server (the Part with TouchInterest) instead
    of CoinVisual.

    Changes vs v0.9:
    - SPEED locked at 26 (the reference tuning that used to work).
    - MAX_FRAME_STEP back to 1.1 (SPEED * 1/60 * ~2.5 safety).
    - Target coin = Coin_Server (verified live: it carries the
      TouchInterest / Touched handler). CoinVisual is just the mesh.
    - Reach radius uses HRP → Coin_Server.Position (no more head
      offset math; Coin_Server is roughly at HRP level after hover).
    - Hover BV restored (Y-only MaxForce) so PlatformStand + physics
      cancel vertical gravity but let X/Z move freely.
    - Noclip still on Stepped (v0.9 fix) so torsos never collide.
    - Below-map rescue: if HRP.Y falls below -100 relative to
      coinContainer bbox, CFrame snap back to coinContainer.Position +
      Vector3.new(0, 10, 0).
    - Floor-sink guard reinstated: targetY = max(coin.Y - headOffset,
      myPos.Y - 1) so we never descend into the floor.
]]

running = false
task.wait(0.3)

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
    FARM_COINS              = true,
    ABORT_IF_MURDERER_NEAR  = true,
    DEBUG_LOG               = true,
    DEBUG_EXPOSE            = true,

    -- Combat (v0.13: disabled per operator; sheriff/murderer don't engage)
    COMBAT_ENABLED          = false,
    COMBAT_AT_CANDIES       = 999,
    SHERIFF_SHOOT_RANGE     = 60,
    TIME_BETWEEN_SHOTS      = 3.4,
    STAB_RANGE              = 12,
    TIME_BETWEEN_STABS      = 1.5,

    -- Movement (v0.15: humanized, SPEED=26 synced to humanoid)
    SPEED                   = 26,
    FORCE_WALKSPEED         = 26,      -- v0.15: hum.WalkSpeed locked at this
    MAX_FRAME_STEP          = 0.5,     -- v0.15: ~SPEED/60, smoother
    MAX_DT                  = 0.05,
    MAX_JUMP                = 25,
    DIR_SMOOTH              = 0.25,    -- v0.15: heading lerp factor per frame
    SYNC_VELOCITY           = true,    -- v0.15: write AssemblyLinearVelocity
    FACE_MOVE_DIR           = true,    -- v0.15: CFrame.lookAt orientation
    TIME_ON_COIN            = 1.0,
    RETRY_AFTER             = 0.4,
    MAX_ATTEMPTS            = 4,
    STUCK_TIMEOUT           = 5.0,
    START_DELAY             = 2,
    MAP_MARGIN              = 20,

    -- Reach to pickup — tight so we actually LAND on the coin
    COIN_PICK_RADIUS        = 1.5,     -- was 3.0; now HRP must be within 1.5 studs
    SNAP_ON_REACH           = true,    -- hard snap HRP to coin.Position on reach
    AIM_AT_TORSO            = true,    -- target = coin.Position (torso), not head

    -- v0.14: GetCoin DISABLED per operator ("hagamoslo legal")
    USE_GETCOIN_REMOTE      = false,
    PICK_FIRE_RADIUS        = 6,
    FIRE_CONFIRM_TIMEOUT    = 0.35,
    FIRES_PER_COIN          = 2,

    -- Below-map rescue
    BELOW_MAP_Y_DELTA       = -80,   -- if HRP.Y < bboxBottom + delta, rescue

    -- Contest / danger
    CONTEST                 = true,
    AVOID_MURDERER_RADIUS   = 35,
    MURDER_SAFE             = 30,
    SHERIFF_SAFE            = 20,
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
local parkedUntil    = 0
local parkedCoin     = nil
local tripTarget     = nil
local tripSince      = 0
local tripPickupBase = 0
local roundStartAt   = 0
local candiesThisRound = 0

local myRole         = "innocent"
local wasFarming     = false
local headOffset     = 1.5
local coinContainer  = nil
local waitingLabel   = nil

local nextShotAt     = 0
local nextStabAt     = 0

local Remotes       = ReplicatedStorage:WaitForChild("Remotes")
local Gameplay      = Remotes:WaitForChild("Gameplay")
local CoinCollected = Gameplay:WaitForChild("CoinCollected")
local CoinsStarted  = Gameplay:WaitForChild("CoinsStarted")
local GetCoin       = Gameplay:WaitForChild("GetCoin")  -- v0.14 direct pickup remote

local firedAt       = setmetatable({}, {__mode = "k"})
local firesForCoin  = setmetatable({}, {__mode = "k"})

-- v0.15: smoothed heading (lerp'd move direction) for humanized motion
local smoothDir     = Vector3.new(0, 0, 1)

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

-- v0.15 humanized CFrame writer:
-- - rejects jumps > MAX_JUMP (AC anti-teleport)
-- - preserves orientation via CFrame.lookAt in the move direction (flattened)
-- - writes AssemblyLinearVelocity consistent with position delta so the
--   server's physics/replication model agrees (prevents "Invalid position")
local function safeMove(hrp, targetPos, dt)
    local delta = targetPos - hrp.Position
    local jump = delta.Magnitude
    if jump > CONFIG.MAX_JUMP then return false end
    if jump < 0.001 then return true end
    local flat = Vector3.new(delta.X, 0, delta.Z)
    if CONFIG.FACE_MOVE_DIR and flat.Magnitude > 0.01 then
        hrp.CFrame = CFrame.lookAt(targetPos, targetPos + flat.Unit)
    else
        hrp.CFrame = CFrame.new(targetPos) * (hrp.CFrame - hrp.CFrame.Position)
    end
    if CONFIG.SYNC_VELOCITY and dt and dt > 0 then
        hrp.AssemblyLinearVelocity = Vector3.new(delta.X/dt, 0, delta.Z/dt)
    end
    return true
end

-- ───────────────────────────────────────────────
-- Weapon helpers
-- ───────────────────────────────────────────────
local function findHeldTool(matchers)
    local char = lp.Character; if not char then return nil end
    for _, t in ipairs(char:GetChildren()) do
        if t:IsA("Tool") then
            local n = t.Name:lower()
            for _, m in ipairs(matchers) do if n:find(m) then return t end end
        end
    end
    return nil
end

local function tryShoot(targetHRP)
    if os.clock() < nextShotAt then return end
    local gun = findHeldTool({"gun", "revolver"}); if not gun then return end
    local shoot = gun:FindFirstChild("Shoot")
    if not shoot or not shoot:IsA("RemoteEvent") then return end
    local hrp = lp.Character and lp.Character:FindFirstChild("HumanoidRootPart")
    if not hrp then return end
    local att = hrp:FindFirstChild("GunRaycastAttachment")
    local origin = att and att.WorldCFrame or (hrp.CFrame * CFrame.new(0, 0, -1))
    shoot:FireServer(origin, CFrame.new(targetHRP.Position))
    nextShotAt = os.clock() + CONFIG.TIME_BETWEEN_SHOTS
end

local function tryStab()
    if os.clock() < nextStabAt then return end
    local knife = findHeldTool({"knife"}); if not knife then return end
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
        local d = head.Position.Y - hrp.Position.Y
        if d > 0 and d < 5 then headOffset = d end
    end
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
    parkedCoin, parkedUntil = nil, 0
    roundStartAt = os.clock()
    candiesThisRound = 0
    dsync("candiesThisRound", 0)
    dlog("CoinsStarted: new round")
end)

-- ───────────────────────────────────────────────
-- Character / noclip (Stepped, pre-physics)
-- ───────────────────────────────────────────────
local noclipStepConn
local function noclipStep()
    if not running or not wasFarming then return end
    local char = lp.Character; if not char then return end
    local hrp = char:FindFirstChild("HumanoidRootPart"); if hrp then hrp.CanCollide=false end
    local lt = char:FindFirstChild("LowerTorso"); if lt then lt.CanCollide=false end
    local ut = char:FindFirstChild("UpperTorso"); if ut then ut.CanCollide=false end
    local t  = char:FindFirstChild("Torso");      if t  then t.CanCollide=false end
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") and p.CanCollide then p.CanCollide = false end
    end
end

local function onCharacter(char)
    char:WaitForChild("HumanoidRootPart", 5)
    refreshHeadOffset(char)
    cacheWaitingLabel()
    tripTarget, tripSince, tripPickupBase = nil, 0, 0
    parkedCoin, parkedUntil = nil, 0
    wasFarming = false
end

if lp.Character then onCharacter(lp.Character) end
lp.CharacterAdded:Connect(onCharacter)

cacheCoinContainer()
cacheWaitingLabel()

if noclipStepConn then noclipStepConn:Disconnect() end
noclipStepConn = RNS.Stepped:Connect(noclipStep)

-- ───────────────────────────────────────────────
-- Gates / role / danger / map
-- ───────────────────────────────────────────────
local function shouldFarm()
    if not CONFIG.FARM_COINS then return false end
    if waitingLabel == nil then cacheWaitingLabel() end
    if waitingLabel and waitingLabel.Visible then return false end
    if coinContainer == nil or coinContainer.Parent == nil then cacheCoinContainer() end
    if coinContainer == nil or #coinContainer:GetChildren() == 0 then return false end
    if roundStartAt > 0 and (os.clock() - roundStartAt) < CONFIG.START_DELAY then return false end
    return true
end

local function getMyRole()
    local function scan(container)
        for _, t in ipairs(container:GetChildren()) do
            if t:IsA("Tool") then
                local n = t.Name:lower()
                if n:find("knife") then return "murderer" end
                if n:find("gun") or n:find("sheriff") or n:find("revolver") then return "sheriff" end
            end
        end
    end
    if lp.Character then local r = scan(lp.Character); if r then return r end end
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
                        elseif (n:find("gun") or n:find("sheriff") or n:find("revolver")) and myRole == "innocent" then
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
    for _, d in ipairs(threats) do if (pos - d.pos).Magnitude < d.dist then return false end end
    return true
end

local function insideMap(pos)
    if CONFIG.MAP_MARGIN <= 0 or coinContainer == nil then return true end
    local parent = coinContainer.Parent
    if parent and parent:IsA("Model") then
        local ok, cf, size = pcall(parent.GetBoundingBox, parent)
        if ok then
            local c = cf.Position
            local h = size/2 + Vector3.new(1,1,1)*CONFIG.MAP_MARGIN
            local d = pos - c
            if math.abs(d.X)<=h.X and math.abs(d.Y)<=h.Y and math.abs(d.Z)<=h.Z then return true end
            return false
        end
    end
    return true
end

local function mapCenterTop()
    if coinContainer == nil then return nil end
    local parent = coinContainer.Parent
    if parent and parent:IsA("Model") then
        local ok, cf, size = pcall(parent.GetBoundingBox, parent)
        if ok then return cf.Position + Vector3.new(0, size.Y/2 + 5, 0) end
    end
    return nil
end

local function arrivalTime(from, to, speed) return (from-to).Magnitude/speed end

local function winsContest(coinPos, myPos, mySpeed, players)
    if not CONFIG.CONTEST then return true end
    local ourTime = arrivalTime(myPos, coinPos, mySpeed)
    for _, pl in ipairs(players) do
        local theirTime = arrivalTime(pl.hrp.Position, coinPos, pl.speed)
        if theirTime < ourTime * CONFIG.TIME_MARGIN then return false end
        if theirTime < ourTime * CONFIG.TIE_MARGIN and pl.p.UserId < lp.UserId then return false end
    end
    return true
end

local function weightedDist(from, to)
    local dx, dz = to.X-from.X, to.Z-from.Z
    local dy = to.Y-from.Y
    return math.sqrt(dx*dx + dz*dz + (dy*CONFIG.HEIGHT_WEIGHT)^2)
end

-- v0.12: target Coin_Server (the Part with TouchInterest), iterate via
-- its tagged CoinVisual child.
local function getBestCoin(myPos, mySpeed)
    local threats, murderer, players = getWorldThreats()
    local murdererPos = murderer and murderer.hrp.Position or nil
    local allVisuals = CollectionService:GetTagged("CoinVisual")
    local best, bestScore = nil, math.huge
    local now = os.clock()
    for _, visual in ipairs(allVisuals) do
        local serverPart = visual.Parent
        if serverPart and serverPart:IsA("BasePart")
            and not visual:GetAttribute("Collected")
            and not visual:GetAttribute("RoundEnd")
            and not visited[serverPart]
            and (not deferredUntil[serverPart] or now >= deferredUntil[serverPart])
        then
            local pos = serverPart.Position
            if insideMap(pos) then
                local inMurdererZone = murdererPos and (murdererPos-pos).Magnitude < CONFIG.AVOID_MURDERER_RADIUS
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
-- Hover / stopFarm
-- ───────────────────────────────────────────────
local function setupHover(hrp)
    local bv = hrp:FindFirstChild("FarmBV") or Instance.new("BodyVelocity", hrp)
    bv.Name     = "FarmBV"
    bv.MaxForce = Vector3.new(0, 1e6, 0)  -- Y-only hold
    bv.P        = 1e5
    bv.Velocity = Vector3.zero
    return bv
end

local function stopFarm(char, hrp, hum)
    if not char or not hrp or not hum then return end
    hum.PlatformStand = false
    hum.WalkSpeed = 16  -- restore default so lobby/menu feels normal
    local bv = hrp:FindFirstChild("FarmBV"); if bv then bv:Destroy() end
    for _, p in ipairs(char:GetDescendants()) do
        if p:IsA("BasePart") then p.CanCollide = true end
    end
    parkedCoin, parkedUntil = nil, 0
    tripTarget = nil
end

-- ───────────────────────────────────────────────
-- HEARTBEAT
-- ───────────────────────────────────────────────
local farmConn
farmConn = RNS.Heartbeat:Connect(function(dt)
    if not running then
        farmConn:Disconnect()
        if noclipStepConn then noclipStepConn:Disconnect() end
        return
    end

    if dt > CONFIG.MAX_DT then dt = CONFIG.MAX_DT end

    local char = lp.Character
    local hum  = char and char:FindFirstChildOfClass("Humanoid")
    local hrp  = char and char:FindFirstChild("HumanoidRootPart")
    if not hum or not hrp or hum.Health <= 0 then return end

    if not shouldFarm() then
        if wasFarming then
            stopFarm(char, hrp, hum)
            wasFarming = false
            dsync("wasFarming", false)
        end
        return
    end

    if not wasFarming then
        wasFarming = true
        myRole     = getMyRole()
        refreshHeadOffset(char)
        smoothDir  = Vector3.new(hrp.CFrame.LookVector.X, 0, hrp.CFrame.LookVector.Z)
        if smoothDir.Magnitude < 0.01 then smoothDir = Vector3.new(0,0,1) else smoothDir = smoothDir.Unit end
        dlog(("ENGAGE: role=%s head=%.2f speed=%d"):format(myRole, headOffset, CONFIG.SPEED))
        dsync("myRole", myRole)
        dsync("wasFarming", true)
        dsync("headOffset", headOffset)
    end

    -- v0.15: force WalkSpeed to the configured value so the server's
    -- speed-validation reference matches our actual CFrame cadence.
    if hum.WalkSpeed ~= CONFIG.FORCE_WALKSPEED then
        hum.WalkSpeed = CONFIG.FORCE_WALKSPEED
    end
    hum.PlatformStand = true
    local bv       = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
    local myPos    = hrp.Position
    local mySpeed  = math.max(1, hum.WalkSpeed)
    local threats, murderer = getWorldThreats()

    -- Below-map rescue
    if coinContainer and coinContainer.Parent then
        local parent = coinContainer.Parent
        if parent and parent:IsA("Model") then
            local ok, cf, size = pcall(parent.GetBoundingBox, parent)
            if ok then
                local bottom = cf.Position.Y - size.Y/2
                if myPos.Y < bottom + CONFIG.BELOW_MAP_Y_DELTA then
                    local rescue = mapCenterTop()
                    if rescue then
                        hrp.CFrame = CFrame.new(rescue)
                        bv.Velocity = Vector3.zero
                        tripTarget = nil
                        dlog("rescue: below-map snap to map top")
                        return
                    end
                end
            end
        end
    end

    -- ─── COMBAT MODE (disabled in v0.13) ───
    if CONFIG.COMBAT_ENABLED and candiesThisRound >= CONFIG.COMBAT_AT_CANDIES then
        if myRole == "sheriff" and murderer then
            local mhrp = murderer.hrp
            local dist = (mhrp.Position - myPos).Magnitude
            if dist <= CONFIG.SHERIFF_SHOOT_RANGE then
                hrp.CFrame = CFrame.lookAt(myPos, Vector3.new(mhrp.Position.X, myPos.Y, mhrp.Position.Z))
                tryShoot(mhrp)
                bv.Velocity = Vector3.zero
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
                    tryStab()
                    bv.Velocity = Vector3.zero
                    return
                else
                    local diff = best.Position - myPos
                    local step = math.min(diff.Magnitude, CONFIG.MAX_FRAME_STEP, CONFIG.SPEED * dt)
                    safeMove(hrp, myPos + diff.Unit * step)
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
                local step = math.min(CONFIG.MAX_FRAME_STEP, CONFIG.SPEED * dt)
                safeMove(hrp, myPos + away.Unit * step)
            end
            bv.Velocity = Vector3.zero
            parkedCoin, parkedUntil, tripTarget = nil, 0, nil
            return
        end
    end

    -- Parked (waiting for server-side Collected flag). v0.14: HOLD HRP
    -- exactly at coin.Position every frame so torso overlap persists
    -- across physics ticks — gives the server's region/touch check
    -- maximum opportunity to fire.
    if parkedCoin and os.clock() < parkedUntil then
        if (not parkedCoin.Parent) or parkedCoin:GetAttribute("Collected")
           or (parkedCoin:FindFirstChildWhichIsA("BasePart") and parkedCoin:FindFirstChildWhichIsA("BasePart"):GetAttribute("Collected")) then
            visited[parkedCoin] = true
            parkedCoin, parkedUntil = nil, 0
        else
            -- Keep HRP pinned exactly on the coin every frame
            if parkedCoin.Parent then
                safeMove(hrp, parkedCoin.Position)
            end
            bv.Velocity = Vector3.zero
            return
        end
    elseif parkedCoin then
        -- Park window elapsed. Bump attempts; bury after MAX_ATTEMPTS.
        local isCollected = parkedCoin:GetAttribute("Collected")
                         or (parkedCoin:FindFirstChildWhichIsA("BasePart") and parkedCoin:FindFirstChildWhichIsA("BasePart"):GetAttribute("Collected"))
        if parkedCoin.Parent and not isCollected then
            local n = (attempts[parkedCoin] or 0) + 1
            attempts[parkedCoin] = n
            if n >= CONFIG.MAX_ATTEMPTS then
                visited[parkedCoin] = true
                dlog("discard: max attempts on coin")
            else
                deferredUntil[parkedCoin] = os.clock() + CONFIG.RETRY_AFTER
            end
        else
            visited[parkedCoin] = true
        end
        parkedCoin, parkedUntil = nil, 0
    end

    -- Pick a coin (operating on Coin_Server parts)
    local coin = getBestCoin(myPos, mySpeed)
    if not coin then
        bv.Velocity = Vector3.zero
        tripTarget = nil
        dsync("tripCoinID", "none")
        return
    end

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
        tripSince  = os.clock()
        tripPickupBase = candiesThisRound
        dsync("tripCoinID", coin:GetAttribute("CoinID") or coin.Name)
    else
        if (os.clock() - tripSince) > CONFIG.STUCK_TIMEOUT
            and candiesThisRound == tripPickupBase then
            visited[coin] = true
            tripTarget = nil
            bv.Velocity = Vector3.zero
            dlog("discard: stuck timeout")
            return
        end
    end

    -- v0.14: target HRP at coin.Position. Move until close, then fire
    -- GetCoin:FireServer(coin) — the server accepts it and sets
    -- Collected=true without needing Touched to fire.
    local coinPos = coin.Position
    local target  = coinPos
    local hrpToCoin = (coinPos - myPos).Magnitude

    -- Within fire radius: fire GetCoin remote
    if hrpToCoin < CONFIG.PICK_FIRE_RADIUS then
        if CONFIG.USE_GETCOIN_REMOTE then
            local last = firedAt[coin] or 0
            local fires = firesForCoin[coin] or 0
            -- Check if server already confirmed from previous fire
            if coin:GetAttribute("Collected")
               or (coin:FindFirstChild("CoinVisual") and coin.CoinVisual:GetAttribute("Collected")) then
                visited[coin] = true
                tripTarget = nil
                dsync("lastDecisionAt", os.clock())
                return
            end
            -- Otherwise fire (with cooldown and retry budget)
            if (os.clock() - last) > CONFIG.FIRE_CONFIRM_TIMEOUT then
                if fires < CONFIG.FIRES_PER_COIN then
                    pcall(function() GetCoin:FireServer(coin) end)
                    firedAt[coin] = os.clock()
                    firesForCoin[coin] = fires + 1
                    dsync("lastFiredCoin", coin:GetAttribute("CoinID") or coin.Name)
                else
                    -- Burned through retries, bury this coin
                    visited[coin] = true
                    tripTarget = nil
                    dlog("discard: GetCoin ignored by server after retries")
                end
            end
            -- Hold position while waiting for server to confirm
            bv.Velocity = Vector3.zero
            return
        else
            -- Fallback (not used in v0.14): snap + park
            if CONFIG.SNAP_ON_REACH then safeMove(hrp, coinPos) end
            bv.Velocity = Vector3.zero
            parkedCoin  = coin
            parkedUntil = os.clock() + CONFIG.TIME_ON_COIN
            return
        end
    end

    -- v0.15 HUMANIZED STEP: smooth heading via lerp toward target
    -- direction so sharp coin-to-coin pivots feel natural (not a
    -- teleport flick). Step size still SPEED*dt capped so the
    -- humanoid's own WalkSpeed validation on the server matches.
    local diff = target - myPos
    local remaining = diff.Magnitude
    local rawDir = remaining > 0.01 and diff.Unit or smoothDir
    -- Lerp smoothDir toward rawDir
    smoothDir = (smoothDir:Lerp(rawDir, CONFIG.DIR_SMOOTH))
    if smoothDir.Magnitude < 0.01 then smoothDir = rawDir end
    smoothDir = smoothDir.Unit
    local stepCap = math.min(CONFIG.MAX_FRAME_STEP, CONFIG.SPEED * dt)
    local step = math.min(remaining, stepCap)
    local nextPos = myPos + smoothDir * step
    local ok = safeMove(hrp, nextPos, dt)
    if not ok then
        deferredUntil[coin] = os.clock() + CONFIG.RETRY_AFTER
        tripTarget = nil
        bv.Velocity = Vector3.zero
        dlog("defer: jump > MAX_JUMP")
        return
    end
    bv.Velocity = Vector3.zero
    dsync("lastDecisionAt", os.clock())
end)
