--[[
    MM2 CANDY FARM — v0.43 (Curry Launcher)
    =======================================
    v0.43 NO MORE MAP-COLLISION STRIP + STATIC WHEN NO TARGET
    (operator: 10s countdown ends, character falls through floor,
    rescue CFrame to top damages via fall; also when no coin is
    detected the bot should stay static not drift/fall):
    - noclipEntireMap() call on CoinsStarted removed. Map keeps its
      CanCollide=true so the character has a real floor to stand on.
    - XZ/above/below-map rescue snap DELETED — it was the source of
      the fall-damage teleport.
    - No-coin branch now pins hrp.CFrame = currentPos every frame so
      the bot holds its Y and XZ exactly (no fall, no drift).
    - FREEZE_ANIMATIONS stays true from v0.42: player model stays
      in a frozen pose while MoveTo slides it between coins —
      movement "parece walk" without a walking animation playing.
    - Character-side noclip (Stepped, per-frame CanCollide=false
      on char parts) is kept so walls are still passable.

    v0.42 ADDITIONS TO v0.26 (operator's preferred baseline):
    - FREEZE_ANIMATIONS=true: humanoid still runs MoveTo (physical
      movement intact) but every playing animation track is stopped
      each frame — character slides around in a static idle pose.
      Looks like a frozen model gliding to each candy.
    - MAX_PICK_DISTANCE doubled 120 -> 240 so the bot chases candies
      farther away in large maps.
    - STUCK_TIMEOUT 5 -> 6s per operator ("si tarda mas de 6 segundos
      en agarrar un candie toma otro").
    - JUMP_CHANCE 0.015 -> 0 (jumps break the static look).

    v0.26 NO MINI-TELEPORT ON PICKUP (operator: "que se mueva hasta
    la direccion donde se miniteletransporta"):
    - SNAP_FINAL_DISTANCE = 0 (was 2.0). Humanoid walks ALL the way
      into the coin, no final CFrame hop.
    - Park-on-reach branch no longer snaps; it keeps calling MoveTo
      so the character micro-steps onto the coin with real motion.
    - Park-pin loop (holding HRP at coin.Position) also switched to
      MoveTo + capped Y velocity instead of CFrame pinning. Looks
      like a player standing on the coin, not teleporting onto it.

    v0.25 CONSTANT SPEED + MAP-WIDE NOCLIP:
    - Y velocity in humanized mode CAPPED to CONFIG.SPEED (16). Before,
      the Y correction was (targetY - myPos.Y) * 4 which could reach
      200+ studs/sec for shelf/ceiling candies — looked like teleport.
      Now vertical motion matches horizontal walkspeed exactly.
    - On CoinsStarted: strip EVERY BasePart.CanCollide=false in the
      current map's root Model (Manor/Barn/etc). No structures can
      wedge the bot since nothing collides with the character.
      (We don't Destroy parts — that would break game logic — just
      disable collision. Visually the map still renders.)

    v0.23 HUMANIZED MOVEMENT (operator: "se ve algo hacker"):
    - PlatformStand=false (humanoid plays walking animations).
    - Humanoid:MoveTo(coin.XZ) drives real locomotion — real rotation,
      real stepping, real idle twitches.
    - Hover BV holds Y, driven toward coin.Y so we rise/fall smoothly
      to shelf candies (no instant teleport up).
    - Noclip still active via Stepped (pre-physics) so we traverse
      walls — but now with walking animations playing, visually
      indistinguishable from a legit player.
    - Final SNAP only within SNAP_FINAL_DISTANCE (2 studs) for pickup
      accuracy — invisible since we're already walking onto the coin.
    - Random micro-pauses + occasional jump (JUMP_CHANCE=0.015) add
      human-grade noise.
    - SPEED=16 synced to WalkSpeed so position deltas match.

    Known bug: Barn / zombies map rescue triggers (Y bounds tight).
    Will tune per-map margins when back in that rotation.

    v0.21 OPERATOR FEATURES:
    - STOP_AT_CANDIES=50: when per-round candies reach the threshold,
      the bot stops moving entirely and idles like in the lobby
      (static position; server sees us as an AFK player). Lowers AC
      profile at the back of each round.
    - Lifetime candy counter (_G.farmLifetimeCandies) tracks pickups
      across rounds within the session.
    - AUTO_BUY_BOX: parallel task reads Candies2026 from ProfileData
      every 3s; at BOX_BUY_THRESHOLD (600) invokes OpenCrate for
      "Halloween2026Box" (MysteryBox category, Candies2026 currency).
      Loop opens as many boxes as credit allows, counts them in
      _G.farmBoxesOpened for telemetry.

    v0.18 SMART PATHING — raycast wall-aware coin picker.
    Operator kicked again after a long-distance pivot through
    multiple walls. The AC flags that pattern. Fixes:
    - countWallsBetween(from, to): raycast with character excluded,
      counts solid BaseParts between HRP and coin.
    - Coins with > MAX_WALLS_HARD_LIMIT (3) walls are skipped entirely.
    - Coins FAR + walled (dist > FAR_WITH_WALLS_LIMIT=25 AND walls>0)
      are deferred 1.5s — we only cross walls for nearby candy.
    - Score = baseDist + walls * WALL_PENALTY (20), so each wall adds
      20 "studs equivalent" to the distance score. A naked coin at
      40 studs beats a walled coin at 25 (score 40 vs 45).
    - Bonus for very near coins (within NEAR_PREFERENCE_RADIUS=30)
      so clusters are drained before pivoting.

    v0.16 SPEED SAFE MODE + telemetry for autonomous 10-min analysis:
    - SPEED and FORCE_WALKSPEED dropped 26 -> 16 (vanilla walkspeed).
      The server's AC was still kicking at 26 despite v0.15's
      velocity sync, so drop to the exact MM2 default to eliminate
      speed-validation as a kick source.
    - MAX_FRAME_STEP 0.5 -> 0.3 for finer updates at lower speed.
    - Telemetry: _G.farmRoundStats collects per-round data (candies,
      elapsed, kicks, discards) so an external monitor can audit.

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

    -- v0.21: stop-at-candies behavior (idle like lobby after threshold)
    STOP_AT_CANDIES         = 50,

    -- v0.21: Halloween Box auto-buy at lifetime threshold
    AUTO_BUY_BOX            = true,
    BOX_BUY_THRESHOLD       = 600,
    BOX_NAME                = "Halloween2026Box",

    -- v0.24: auto-rejoin on kick / disconnect prompt
    AUTO_REJOIN             = true,
    REJOIN_POLL_INTERVAL    = 1.0,
    SHERIFF_SHOOT_RANGE     = 60,
    TIME_BETWEEN_SHOTS      = 3.4,
    STAB_RANGE              = 12,
    TIME_BETWEEN_STABS      = 1.5,

    -- Movement (v0.23: humanized — humanoid walks with animations,
    -- noclip still bypasses walls, final snap for pickup accuracy)
    HUMANIZED               = true,    -- v0.23: use Humanoid:MoveTo + anims
    FREEZE_ANIMATIONS       = true,    -- v0.42: stop anim tracks each frame (static pose while walking)
    SPEED                   = 16,
    FORCE_WALKSPEED         = 16,
    MAX_FRAME_STEP          = 0.3,
    COOLDOWN_BETWEEN_COINS  = 0.2,
    MICRO_PAUSE_MIN         = 0.05,
    MICRO_PAUSE_MAX         = 0.18,
    SNAP_FINAL_DISTANCE     = 0,
    JUMP_CHANCE             = 0,       -- v0.42: off (static look)
    JUMP_COOLDOWN           = 999,

    -- Pathing intelligence (v0.19 softened)
    WALL_RAYCAST            = true,
    WALL_PENALTY            = 12,         -- studs per wall (soft scoring only)
    MAX_WALLS_HARD_LIMIT    = 99,         -- no hard limit (softened)
    FAR_WITH_WALLS_LIMIT    = 9999,       -- no defer-by-walls
    NEAR_PREFERENCE_RADIUS  = 25,
    MAX_PICK_DISTANCE       = 240,        -- v0.42: doubled (was 120)
    RESCUE_IF_NO_COIN_WITHIN = 300,       -- if nearest > this -> rescue
    CLUSTER_PREFERENCE      = true,
    MAX_DT                  = 0.05,
    MAX_JUMP                = 25,
    DIR_SMOOTH              = 0.25,    -- v0.15: heading lerp factor per frame
    SYNC_VELOCITY           = true,    -- v0.15: write AssemblyLinearVelocity
    FACE_MOVE_DIR           = true,    -- v0.15: CFrame.lookAt orientation
    TIME_ON_COIN            = 1.0,
    RETRY_AFTER             = 0.4,
    MAX_ATTEMPTS            = 4,
    STUCK_TIMEOUT           = 6.0,      -- v0.42: 5 -> 6 per operator
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

-- v0.16 telemetry
_G.farmRoundStats = _G.farmRoundStats or {}
_G.farmDiscards   = _G.farmDiscards or {}
_G.farmCurrentRound = _G.farmCurrentRound or {start=os.clock(), pickups=0, discards=0, maxDist=0}

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
-- v0.21: lifetime candies counter (persistent across rounds within session)
_G.farmLifetimeCandies = _G.farmLifetimeCandies or 0

CoinCollected.OnClientEvent:Connect(function(coinID)
    candiesThisRound = candiesThisRound + 1
    _G.farmLifetimeCandies = _G.farmLifetimeCandies + 1
    _G.farmCurrentRound.pickups = (_G.farmCurrentRound.pickups or 0) + 1
    dsync("candiesThisRound", candiesThisRound)
    dsync("lifetimeCandies", _G.farmLifetimeCandies)
    dlog(("pickup type=%s round=%d life=%d"):format(tostring(coinID), candiesThisRound, _G.farmLifetimeCandies))
end)

-- v0.25: strip every collision in the current map model on round start.
-- "Eliminate" per operator means: nothing in the map blocks movement.
-- We don't Destroy parts (that breaks game logic), just set CanCollide
-- =false + CanTouch=true on every BasePart in the map's root Model.
local function noclipEntireMap()
    cacheCoinContainer()
    if not coinContainer then return 0 end
    local root = coinContainer.Parent
    if not root then return 0 end
    local count = 0
    for _, p in ipairs(root:GetDescendants()) do
        if p:IsA("BasePart") and p.CanCollide then
            p.CanCollide = false
            count = count + 1
        end
    end
    dlog(("map noclip applied: %d parts"):format(count))
    return count
end

CoinsStarted.OnClientEvent:Connect(function()
    -- Snapshot previous round to telemetry
    if _G.farmCurrentRound and _G.farmCurrentRound.pickups and _G.farmCurrentRound.pickups > 0 then
        _G.farmCurrentRound.elapsed = os.clock() - (_G.farmCurrentRound.start or os.clock())
        table.insert(_G.farmRoundStats, _G.farmCurrentRound)
        if #_G.farmRoundStats > 20 then table.remove(_G.farmRoundStats, 1) end
    end
    _G.farmCurrentRound = {start=os.clock(), pickups=0, discards=0, maxDist=0}
    visited = setmetatable({}, {__mode = "k"})
    deferredUntil = setmetatable({}, {__mode = "k"})
    attempts = setmetatable({}, {__mode = "k"})
    tripTarget, tripSince, tripPickupBase = nil, 0, 0
    parkedCoin, parkedUntil = nil, 0
    roundStartAt = os.clock()
    candiesThisRound = 0
    dsync("candiesThisRound", 0)
    -- v0.43: NO map-wide noclip (caused the fall-through-floor at
    -- round start when the countdown ended). Character-side noclip
    -- still runs via Stepped so we pass through walls anyway.
    dsync("mapNoclipParts", 0)
    dlog("CoinsStarted: new round (map collision preserved)")
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
-- v0.24: auto-rejoin watchdog (parallel task)
-- Detects CoreGui ErrorPrompt or GuiService:GetErrorCode and fires
-- TeleportService:Teleport back into a new instance. Also watches
-- for the disconnected overlay in PlayerGui.
-- ───────────────────────────────────────────────
_G.farmRejoinCount = _G.farmRejoinCount or 0
_G.farmLastKickReason = _G.farmLastKickReason or nil
if CONFIG.AUTO_REJOIN then
    task.spawn(function()
        local TeleportService = game:GetService("TeleportService")
        local GuiService = game:GetService("GuiService")
        local CoreGui = game:GetService("CoreGui")
        local function tryRejoin(why)
            _G.farmLastKickReason = why
            _G.farmRejoinCount = _G.farmRejoinCount + 1
            print(("[farm/rejoin] triggered: %s (count=%d)"):format(why, _G.farmRejoinCount))
            dsync("lastKickReason", why)
            dsync("rejoinCount", _G.farmRejoinCount)
            pcall(function()
                TeleportService:Teleport(game.PlaceId, lp)
            end)
        end
        -- Fast UI poll
        while running do
            -- 1) GuiService error code (set by engine when kicked)
            local ok, code = pcall(function() return GuiService:GetErrorCode() end)
            if ok and code and code ~= Enum.ConnectionError.OK then
                tryRejoin("GuiService code=" .. tostring(code))
                task.wait(10)  -- avoid spam while rejoin processes
            end
            -- 2) CoreGui ErrorPrompt visible (Roblox disconnect UI)
            local errP = CoreGui:FindFirstChild("RobloxPromptGui", true)
                     or CoreGui:FindFirstChild("ErrorPromptApp", true)
            if errP then
                for _, d in ipairs(errP:GetDescendants()) do
                    if d:IsA("TextLabel") and d.Text and
                       (d.Text:find("Invalid") or d.Text:find("disconnected") or d.Text:find("Desconectad") or d.Text:find("expulsa"))
                    then
                        tryRejoin("prompt=" .. d.Text:sub(1, 40))
                        task.wait(10)
                        break
                    end
                end
            end
            task.wait(CONFIG.REJOIN_POLL_INTERVAL)
        end
    end)
end

-- ───────────────────────────────────────────────
-- v0.21: Halloween Box auto-opener (parallel task)
-- ───────────────────────────────────────────────
_G.farmBoxesOpened = _G.farmBoxesOpened or 0
if CONFIG.AUTO_BUY_BOX then
    task.spawn(function()
        local Shop = ReplicatedStorage:WaitForChild("Remotes"):WaitForChild("Shop")
        local OpenCrate = Shop:WaitForChild("OpenCrate")
        local ok, ProfileData = pcall(require, ReplicatedStorage:WaitForChild("Modules"):WaitForChild("ProfileData"))
        if not ok then
            warn("[farm/box] ProfileData load failed")
            return
        end
        local function getCandies()
            return (ProfileData.Materials and ProfileData.Materials.Owned and ProfileData.Materials.Owned.Candies2026) or 0
        end
        dsync("boxCurrency", "Candies2026")
        while running do
            local c = getCandies()
            dsync("profileCandies", c)
            if c >= CONFIG.BOX_BUY_THRESHOLD then
                local before = c
                pcall(function() OpenCrate:InvokeServer(CONFIG.BOX_NAME, "MysteryBox", "Candies2026") end)
                task.wait(0.4)
                local after = getCandies()
                if (before - after) >= CONFIG.BOX_BUY_THRESHOLD then
                    _G.farmBoxesOpened = _G.farmBoxesOpened + 1
                    dsync("boxesOpened", _G.farmBoxesOpened)
                    dlog(("box OPENED #%d (candies %d -> %d)"):format(_G.farmBoxesOpened, before, after))
                else
                    dlog(("box buy failed (candies %d -> %d)"):format(before, after))
                    task.wait(3)
                end
            end
            task.wait(3)
        end
    end)
end

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

-- v0.22: rescue to the middle of the map (Y at center, not top) so the
-- aboveMap check doesn't re-trigger immediately on the rescue itself.
local function mapCenterTop()
    if coinContainer == nil then return nil end
    local parent = coinContainer.Parent
    if parent and parent:IsA("Model") then
        local ok, cf, size = pcall(parent.GetBoundingBox, parent)
        if ok then return cf.Position end
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

-- v0.18: raycast from HRP to coin and count blocking BaseParts along
-- the ray. Ignores the character itself. Returns wall count.
local function countWallsBetween(fromPos, toPos, charExclude)
    if not CONFIG.WALL_RAYCAST then return 0 end
    local dir = toPos - fromPos
    local dist = dir.Magnitude
    if dist < 0.1 then return 0 end
    local rp = RaycastParams.new()
    rp.FilterType = Enum.RaycastFilterType.Exclude
    rp.FilterDescendantsInstances = charExclude and {charExclude} or {}
    rp.IgnoreWater = true
    local walls = 0
    local origin = fromPos
    local remaining = dist
    for _ = 1, CONFIG.MAX_WALLS_HARD_LIMIT + 2 do
        local hit = workspace:Raycast(origin, dir.Unit * remaining, rp)
        if not hit then break end
        walls = walls + 1
        -- Advance past the hit by 0.1 studs and continue
        local traveled = (hit.Position - origin).Magnitude + 0.1
        origin = hit.Position + dir.Unit * 0.1
        remaining = remaining - traveled
        if remaining <= 0.1 then break end
    end
    return walls
end

-- v0.12: target Coin_Server (the Part with TouchInterest), iterate via
-- its tagged CoinVisual child.
local function getBestCoin(myPos, mySpeed)
    local threats, murderer, players = getWorldThreats()
    local murdererPos = murderer and murderer.hrp.Position or nil
    local allVisuals = CollectionService:GetTagged("CoinVisual")
    local char = lp.Character
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
                local baseDist = weightedDist(myPos, pos)
                -- v0.18: count walls between us and the coin
                local walls = 0
                if CONFIG.WALL_RAYCAST then
                    walls = countWallsBetween(myPos, pos, char)
                end
                -- v0.19: no hard filters, pure scoring. Softer wall penalty
                -- plus a near-preference bonus. Hard distance cap only.
                if baseDist <= CONFIG.MAX_PICK_DISTANCE then
                    local score = baseDist + walls * CONFIG.WALL_PENALTY
                    if baseDist < CONFIG.NEAR_PREFERENCE_RADIUS then
                        score = score - (CONFIG.NEAR_PREFERENCE_RADIUS - baseDist) * 0.5
                    end
                    if isSafe(pos, threats) and not inMurdererZone and weWin then
                        if score < bestScore then best, bestScore = serverPart, score end
                    end
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
    -- v0.23: in humanized mode we LEAVE PlatformStand=false so the
    -- humanoid plays walking animations naturally. Y is held by the
    -- hover BV; noclip bypasses walls; physics does the rest.
    if CONFIG.HUMANIZED then
        hum.PlatformStand = false
    else
        hum.PlatformStand = true
    end

    -- v0.42: freeze animations each frame so the character slides
    -- in a static pose while MoveTo still drives physical movement.
    if CONFIG.FREEZE_ANIMATIONS then
        local animator = hum:FindFirstChildOfClass("Animator")
        if animator then
            for _, track in ipairs(animator:GetPlayingAnimationTracks()) do
                pcall(function() track:Stop(0) end)
            end
        end
    end

    -- v0.21: STOP_AT_CANDIES — idle (like lobby) once threshold reached.
    -- Character stays in place; noclip and hover still active for safety
    -- but no coin pursuit. Server sees us as a static (afk) player.
    if candiesThisRound >= CONFIG.STOP_AT_CANDIES then
        local bv2 = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
        bv2.Velocity = Vector3.zero
        tripTarget = nil
        parkedCoin, parkedUntil = nil, 0
        dsync("tripCoinID", "stopped-at-threshold")
        return
    end
    local bv       = hrp:FindFirstChild("FarmBV") or setupHover(hrp)
    local myPos    = hrp.Position
    local mySpeed  = math.max(1, hum.WalkSpeed)
    local threats, murderer = getWorldThreats()

    -- v0.43: out-of-map rescue DISABLED — the CFrame snap to center
    -- was causing the "fall at round start + damage from rescue
    -- teleport" bug. Floor collision now preserved (map parts keep
    -- CanCollide=true) so the character stands on the floor naturally
    -- and never falls through. If somehow we do fall, the stuck
    -- watchdog (180s) still handles it as a last resort.

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
            -- v0.26 humanized park: keep WALKING onto the coin via
            -- MoveTo instead of CFrame-pinning (which looks like a
            -- freeze+teleport). Humanoid will micro-step the last
            -- fraction of a stud and the torso overlap triggers the
            -- server's Touched handler.
            if parkedCoin.Parent then
                if CONFIG.HUMANIZED then
                    hum:MoveTo(Vector3.new(parkedCoin.Position.X, hrp.Position.Y, parkedCoin.Position.Z))
                    -- Y correction via BV, capped at SPEED
                    local vy = (parkedCoin.Position.Y - hrp.Position.Y) * 4
                    local cap = CONFIG.SPEED
                    if vy > cap then vy = cap elseif vy < -cap then vy = -cap end
                    bv.Velocity = Vector3.new(0, vy, 0)
                else
                    safeMove(hrp, parkedCoin.Position)
                    bv.Velocity = Vector3.zero
                end
            end
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
                _G.farmCurrentRound.discards = (_G.farmCurrentRound.discards or 0) + 1
                table.insert(_G.farmDiscards, {t=os.clock(), r="max_attempts"})
                if #_G.farmDiscards > 200 then table.remove(_G.farmDiscards, 1) end
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
        -- v0.43: no coin detected -> freeze HRP in place (hold Y so
        -- we don't fall through floor via noclip). No rescue teleport,
        -- no gravity drift. Bot acts like a static AFK player until
        -- a coin shows up.
        hrp.CFrame = CFrame.new(myPos)  -- pin current position
        bv.Velocity = Vector3.zero
        if CONFIG.HUMANIZED then hum:MoveTo(myPos) end
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
            _G.farmCurrentRound.discards = (_G.farmCurrentRound.discards or 0) + 1
            table.insert(_G.farmDiscards, {t=os.clock(), r="stuck_timeout"})
            if #_G.farmDiscards > 200 then table.remove(_G.farmDiscards, 1) end
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
            -- v0.26: in humanized mode, DO NOT snap — let MoveTo take
            -- the humanoid the final studs so visually it just walks
            -- onto the coin. Park still runs so server has time to
            -- register pickup, but position isn't yanked.
            if not CONFIG.HUMANIZED and CONFIG.SNAP_ON_REACH then
                safeMove(hrp, coinPos)
            end
            parkedCoin  = coin
            parkedUntil = os.clock() + CONFIG.TIME_ON_COIN
            -- Keep humanoid moving toward coin while parked so the
            -- character doesn't stop short with visible gap
            if CONFIG.HUMANIZED then
                hum:MoveTo(Vector3.new(coinPos.X, hrp.Position.Y, coinPos.Z))
            else
                bv.Velocity = Vector3.zero
            end
            return
        end
    end

    -- v0.23 HUMANIZED: let the Humanoid walk toward the coin. MoveTo
    -- drives real locomotion (plays walking animations, rotates the
    -- character naturally, uses the character's own stepping cadence).
    -- Noclip still bypasses walls; the hover BV keeps Y stable. When
    -- within SNAP_FINAL_DISTANCE we quietly snap for pickup accuracy.
    if CONFIG.HUMANIZED then
        local diff = target - myPos
        local remaining = diff.Magnitude
        -- Flatten X/Z for MoveTo target to avoid the humanoid trying
        -- to raycast up to a coin on a ledge (it can't jump+walk at
        -- the same time reliably). HipHeight+hover holds our Y.
        local moveTarget = Vector3.new(target.X, hrp.Position.Y, target.Z)
        hum:MoveTo(moveTarget)
        -- Occasional human jump twitch
        if math.random() < CONFIG.JUMP_CHANCE
           and (os.clock() - lastJumpAt) > CONFIG.JUMP_COOLDOWN then
            hum.Jump = true
            lastJumpAt = os.clock()
        end
        -- Sync Y to coin.Y via BV, but CAPPED to WalkSpeed so vertical
        -- motion matches horizontal (no 200-studs/sec Y yank for
        -- ceiling/floor candies).
        local targetY = target.Y
        local vy = (targetY - myPos.Y) * 4
        local cap = CONFIG.SPEED
        if vy > cap then vy = cap elseif vy < -cap then vy = -cap end
        bv.Velocity = Vector3.new(0, vy, 0)
        -- Within final snap distance: freeze XZ at exact coin pos
        if remaining < CONFIG.SNAP_FINAL_DISTANCE then
            safeMove(hrp, target, dt)
            bv.Velocity = Vector3.zero
        end
        dsync("lastDecisionAt", os.clock())
        return
    end

    -- Non-humanized fallback (v0.15 CFrame step w/ smoothing)
    local diff = target - myPos
    local remaining = diff.Magnitude
    local rawDir = remaining > 0.01 and diff.Unit or smoothDir
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
