--[[
    MM2 MAP RECON — v0.1 (Curry Launcher)
    =====================================
    Captures the geometry of every MM2 map as it comes up in rotation.

    - Listens to Gameplay.CoinsStarted; 1.5s after each round starts,
      finds the current map model (parent of CoinContainer) and scans:
        * bounding box (center + size)
        * walkable grid: XZ cells every GRID_STEP, per cell the top
          floor hit by a downward raycast
        * part count + total vertices rough (for debugging)
    - Writes each map ONCE per session to mm2-maps/<mapName>.json
      via the executor's writefile (if available), and always keeps
      it in _G.farmMaps[mapName] for in-memory access.
    - If writefile is absent, the JSON is logged to the console and
      can be copy-pasted out.

    Loaded independently of collector.lua. Safe to run alongside it;
    does not touch the character or the pickup logic.
]]

local CollectionService = game:GetService("CollectionService")
local HttpService        = game:GetService("HttpService")
local ReplicatedStorage  = game:GetService("ReplicatedStorage")

local GRID_STEP          = 6         -- studs between walkable raycasts
local SCAN_DELAY         = 1.5       -- wait for map to fully load
local RAY_DOWN           = 500       -- max distance for floor raycast
local SAVE_DIR           = "mm2-maps"

_G.farmMaps = _G.farmMaps or {}
_G.farmMapReconLog = _G.farmMapReconLog or {}

local function log(msg)
    print("[mapRecon] " .. msg)
    table.insert(_G.farmMapReconLog, {t = os.clock(), msg = msg})
    if #_G.farmMapReconLog > 100 then table.remove(_G.farmMapReconLog, 1) end
end

local SKIP_MODELS = {Lobby=true, ServerStatus=true, LeaderboardFolder=true}

local function isLikelyMap(root)
    if not root or not root:IsA("Model") then return false end
    if SKIP_MODELS[root.Name] then return false end
    if root:FindFirstChildOfClass("Humanoid") then return false end  -- characters
    -- Reject empties / tiny decorations
    local okBB, _, size = pcall(root.GetBoundingBox, root)
    if not okBB then return false end
    if size.X < 40 or size.Z < 40 then return false end
    return true
end

local function scanModel(root)
    if not isLikelyMap(root) then return nil end
    local mapName = root.Name
    if _G.farmMaps[mapName] then return _G.farmMaps[mapName] end
    -- bbox
    local okBB, cf, size = pcall(root.GetBoundingBox, root)
    if not okBB then return nil end
    local mapName = root.Name
    local center = cf.Position
    local halfX, halfZ = size.X / 2, size.Z / 2
    local topY = center.Y + size.Y / 2 + 10
    local botY = center.Y - size.Y / 2 - 10

    -- parts count
    local parts = 0
    for _, p in ipairs(root:GetDescendants()) do
        if p:IsA("BasePart") then parts = parts + 1 end
    end

    -- Walkable grid: for each (x, z) cell, raycast down from topY.
    -- Exclude the local character so we don't hit ourselves.
    local rp = RaycastParams.new()
    rp.FilterType = Enum.RaycastFilterType.Exclude
    local lp = game.Players.LocalPlayer
    if lp and lp.Character then
        rp.FilterDescendantsInstances = {lp.Character}
    end
    rp.IgnoreWater = true

    local walkable = {}
    local cells = 0
    for x = math.floor((center.X - halfX) / GRID_STEP) * GRID_STEP,
           math.ceil((center.X + halfX) / GRID_STEP) * GRID_STEP, GRID_STEP do
        for z = math.floor((center.Z - halfZ) / GRID_STEP) * GRID_STEP,
               math.ceil((center.Z + halfZ) / GRID_STEP) * GRID_STEP, GRID_STEP do
            local origin = Vector3.new(x, topY, z)
            local dir    = Vector3.new(0, -(topY - botY), 0)
            local hit = workspace:Raycast(origin, dir, rp)
            if hit then
                -- Keep only if the hit is inside the map's Y range
                local y = hit.Position.Y
                if y >= botY and y <= topY then
                    table.insert(walkable, {
                        x = math.floor(x),
                        z = math.floor(z),
                        y = math.floor(y * 10) / 10,
                        mat = tostring(hit.Material):gsub("Enum.Material.", ""),
                    })
                    cells = cells + 1
                end
            end
        end
    end

    local captured = {
        mapName = mapName,
        capturedAt = os.time(),
        bbox = {
            center = {math.floor(center.X), math.floor(center.Y), math.floor(center.Z)},
            size   = {math.floor(size.X),   math.floor(size.Y),   math.floor(size.Z)},
        },
        gridStep = GRID_STEP,
        parts = parts,
        walkableCount = cells,
        walkable = walkable,
    }
    _G.farmMaps[mapName] = captured

    log(string.format(
        "captured %s | parts=%d walkable=%d bbox=%dx%dx%d",
        mapName, parts, cells,
        math.floor(size.X), math.floor(size.Y), math.floor(size.Z)))

    -- Persist via writefile (executor)
    if type(makefolder) == "function" then
        pcall(makefolder, SAVE_DIR)
    end
    if type(writefile) == "function" then
        local ok, enc = pcall(HttpService.JSONEncode, HttpService, captured)
        if ok then
            pcall(writefile, SAVE_DIR .. "/" .. mapName .. ".json", enc)
            log("wrote " .. SAVE_DIR .. "/" .. mapName .. ".json")
        else
            log("JSONEncode failed: " .. tostring(enc))
        end
    end

    return captured
end

local function scanAllWorkspace()
    for _, v in ipairs(workspace:GetChildren()) do
        if not _G.farmMaps[v.Name] then
            pcall(scanModel, v)
        end
    end
end

-- Hook CoinsStarted → scan after 1.5s
local Remotes      = ReplicatedStorage:WaitForChild("Remotes")
local Gameplay     = Remotes:WaitForChild("Gameplay")
local CoinsStarted = Gameplay:WaitForChild("CoinsStarted")

if _G.farmMapReconConn then pcall(function() _G.farmMapReconConn:Disconnect() end) end
_G.farmMapReconConn = CoinsStarted.OnClientEvent:Connect(function()
    task.spawn(function()
        task.wait(SCAN_DELAY)
        pcall(scanAllWorkspace)
    end)
end)

-- Also poll every 10s so maps that load without a CoinsStarted fire
-- (lobby arrival, intermission maps, player joining mid-round) get
-- captured too.
if _G.farmMapReconPoll then pcall(function() _G.farmMapReconPoll:Disconnect() end) end
task.spawn(function()
    while running ~= false do
        scanAllWorkspace()
        task.wait(10)
    end
end)

-- Initial scan
task.spawn(function() task.wait(1); scanAllWorkspace() end)

log("map recon armed (CoinsStarted + 10s poll, grid=" .. GRID_STEP .. ")")
