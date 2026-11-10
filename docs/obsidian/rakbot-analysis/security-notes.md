# Security and operational notes

## Cookies file

`cookies.txt` holds 1,250 full Roblox session cookies. Each
`.ROBLOSECURITY` token grants full account access. Protection in this
tool:

- The Tk GUI process never reads it directly.
- Only `mass.read_mass_credentials` opens it, streaming line by line.
- Credentials cross subprocess boundaries over stdin only — never argv,
  env, log files, temp files, or the server-browser process.
- The shipped `README_RUNTIME.txt` states explicitly: "this archive
  contains no account sessions" (the cookie file ships separately with
  the operator).

## Crypto

- **Session AEAD:** ChaCha20-Poly1305, keyed via X25519. Counter base
  `b"UniqueNu"` little-endian, matching native 0.744.
- **Application envelope:** AES block cipher with native-ordered block
  chain (`first, last, penultimate, …, second`). Not CBC; recovered
  verbatim from the native binary.
- **Build hash** stored ROT13 to avoid grep hits in the source.
- **No cryptographic shortcuts.** `cryptography` Python package provides
  the primitives; no custom AES/ChaCha implementations.

## Protocol provenance

Comments all over the modules reference native 0.744 addresses:
`0x1059d3ac7`, `0x1057b2fed`, `0x10580dcfa`, `0x1057ac06a`,
`0x105713118`, etc. These are symbol offsets in the MacPlayer 0.744
binary. Supporting evidence is expected to live in `research/REVERSE.md`
(referenced by `native_crypto.py`) — that file is not present in the
distributed tree. Worth asking the author / repo for it.

## What the tool does and does not do

**Does:**
- Join Roblox servers as a mass of accounts
- Replicate game state to read fields (pet stats, egg stats)
- Send chat / movement / teleport / team-change / character-spawn RPCs
- Emit observed Featured finds to a local WS relay

**Does not:**
- Execute replicated Luau (no VM, no interpreter)
- Modify server state beyond legal client RPCs the game accepts
- Drive the official Roblox Player
- Decrypt or store other users' credentials

## Operational risks

- **Account bans.** Running 999,999 cookies through what Roblox will
  detect as non-official clients is a known Terms-of-Service issue.
  Every account in `cookies.txt` is burnable.
- **Rate limiting.** `scanner_health` has explicit `rate_limit (429)`,
  `forbidden (403)`, `unauthorized (401)` categories. Backoff is
  implemented but mass runs still trigger them.
- **Server refusals.** Code 273 waits ≥60s before retry. Other codes
  immediately rejoin a different server after 5 consecutive failures.
- **Relay exposure.** Default binds `0.0.0.0:8765`. The random key in
  `relay.json` is the only auth. Treat `relay.json` as a secret.
- **Fingerprinting.** `PROTOCOL_FINGERPRINT` and `BUILD_HASH` are fixed
  constants. If Roblox rotates them server-side without publishing an
  updated matching binary, the tool stops working until re-reversed.
- **Native extension:** `rakbot/_reader.pyd` is compiled binary with no
  shipped source. Trust requires rebuilding it or auditing it by hand.

## What's missing from the package

- `research/REVERSE.md` (referenced in `native_crypto.py`'s docstring) —
  evidence trail for the reversed primitives.
- Source for `_reader.pyd`.
- Tests. Several comments reference "synthetic native fixtures" but no
  `tests/` directory ships.

See also: [[overview]], [[architecture]], [[root-files]].
