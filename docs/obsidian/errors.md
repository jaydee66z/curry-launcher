# Errors

## Fall-at-round-start (recurring, unresolved across v0.29-v0.43)

Operator reported MANY times: when the 10s countdown ends and a new
round starts, the bot falls through the floor. Rescue teleport to
map top then caused fall-damage. Pattern repeats on multiple maps.

### Attempts that failed
- **v0.29**: floor raycast guard + Y descent cap -3 → raycast often
  returned "no floor" during map transition, bot still fell
- **v0.30**: visual-only hide + stall watchdog → didn't address fall
- **v0.31**: hard snap to bbox center on no-floor → caused rejoin
  loop (snap position triggered the same check next frame)
- **v0.34**: softer floor guard, stall 180s → still fell
- **v0.43**: removed noclipEntireMap + removed rescue snap →
  operator reported fall happened AGAIN immediately

### Root cause (finally identified v0.44)
The hover BodyVelocity is only created INSIDE the heartbeat the
first time `wasFarming` becomes true. During the START_DELAY window
(2s after CoinsStarted) and during the countdown, the character has
no vertical hold. PlatformStand=false (humanized) means humanoid
gravity + Freefall state activates, character drops out of mid-air
spawn. By the time wasFarming engages and BV is attached, the
character is already below the map.

**Autodidactic note**: operator is correct to call this out — this
should have been solved on v0.29 by attaching the BV on
CharacterAdded (unconditional), not deferred into the heartbeat.
Lesson: for safety-critical state (gravity hold), set up at the
earliest point, not at the point you first need it.

## Animation freeze was conditional (should be unconditional)

Operator asked for frozen animations ALWAYS, not just during farming.
My implementation only stopped tracks inside `if wasFarming` block,
so between rounds the walking/idle anim played. Fix in v0.44:
parallel task stops all animation tracks every 0.1s, unconditionally,
for the whole session.


Errors encountered during development and their resolution.

Format per entry:

```
## YYYY-MM-DD — short title
- Context:
- Error:
- Cause:
- Fix:
```

(none yet)

See also: [[logs]], [[references]].
