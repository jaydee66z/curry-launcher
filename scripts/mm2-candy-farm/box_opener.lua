--[[
    MM2 HALLOWEEN BOX '26 — AUTO OPENER
    v0.1 — Curry Launcher MM2 scripts baseline
    =====================================
    GENERAL LOGIC:
    Loop that checks every few seconds whether the player has >= 600 Candies2026.
    If so, invoke OpenCrate -> the server deducts 600 candies and grants the item.
    Repeats until there are not enough candies or the loop is stopped manually.

    REMOTE:
      game.ReplicatedStorage.Remotes.Shop.OpenCrate (RemoteFunction)
      InvokeServer("Halloween2026Box", "MysteryBox", "Candies2026")

    NOTE: The server returns false when the Shop UI is not active,
    but the purchase IS processed — the item lands straight in the profile.
    We verify by comparing candies before/after to confirm the opening.
]]

-- ───────────────────────────────────────────────
-- CONFIG
-- ───────────────────────────────────────────────
local BOX_ID      = "Halloween2026Box"
local CURRENCY    = "Candies2026"
local BOX_COST    = 600
local CHECK_DELAY = 3
local autoRunning = true

-- ───────────────────────────────────────────────
-- SERVICES AND REMOTES
-- ───────────────────────────────────────────────
local Shop      = game:GetService("ReplicatedStorage"):WaitForChild("Remotes"):WaitForChild("Shop")
local OpenCrate = Shop:WaitForChild("OpenCrate")

local ok, ProfileData = pcall(require, game:GetService("ReplicatedStorage"):WaitForChild("Modules"):WaitForChild("ProfileData"))
if not ok then
    error("[BOX] ProfileData did not load: " .. tostring(ProfileData))
end

local function getCandies()
    return (ProfileData.Materials
        and ProfileData.Materials.Owned
        and ProfileData.Materials.Owned[CURRENCY])
        or 0
end

local function openBox()
    local before = getCandies()
    if before < BOX_COST then
        return false, string.format("Candies insuficientes: %d/%d", before, BOX_COST)
    end

    local result = OpenCrate:InvokeServer(BOX_ID, "MysteryBox", CURRENCY)
    task.wait(0.3)

    local after = getCandies()
    local spent = before - after

    if spent >= BOX_COST then
        return true, string.format(
            "Abierta OK | Item: %s | Candies: %d -> %d (-%d)",
            tostring(result), before, after, spent
        )
    elseif result and result ~= false then
        return true, string.format("Abierta OK | Item: %s", tostring(result))
    else
        return false, string.format(
            "Fallo. Result=%s | Candies: %d->%d",
            tostring(result), before, after
        )
    end
end

-- ───────────────────────────────────────────────
-- MAIN LOOP
-- ───────────────────────────────────────────────
local opened   = 0
local failures = 0
local MAX_FAIL = 3

print("[BOX] Auto-opener iniciado. Para parar: autoRunning = false")
print(string.format("[BOX] Candies actuales: %d | Necesarios: %d", getCandies(), BOX_COST))

task.spawn(function()
    while autoRunning do
        local candies = getCandies()

        if candies < BOX_COST then
            print(string.format("[BOX] Esperando candies... (%d/%d)", candies, BOX_COST))
            task.wait(CHECK_DELAY)
        else
            print(string.format("[BOX] %d candies detectados -> abriendo...", candies))
            local success, msg = openBox()

            if success then
                opened   = opened + 1
                failures = 0
                print(string.format("[BOX #%d] %s", opened, msg))
            else
                failures = failures + 1
                warn(string.format("[BOX] Fallo #%d/%d: %s", failures, MAX_FAIL, msg))
                if failures >= MAX_FAIL then
                    warn("[BOX] Demasiados fallos consecutivos. Parando.")
                    autoRunning = false
                    break
                end
            end

            task.wait(CHECK_DELAY)
        end
    end

    print(string.format("[BOX] Loop terminado. Cajas abiertas: %d | Candies restantes: %d", opened, getCandies()))
end)
