# References

External docs, URLs, APIs, SDKs relevant to Curry Launcher.

## Repo

- https://github.com/jaydee66z/curry-launcher

## Lua / Luau

- Lua 5.4 reference: https://www.lua.org/manual/5.4/
- Luau docs: https://luau.org/
- Roblox Luau: https://create.roblox.com/docs/luau
- Luau source and headers: https://github.com/luau-lang/luau

## RakNet / transport

- RakNet reference implementation: https://github.com/facebookarchive/RakNet (see `Source/RakPeer.cpp` — `protocol.py` points here)
- ChaCha20-Poly1305 RFC: https://datatracker.ietf.org/doc/html/rfc8439
- X25519 RFC: https://datatracker.ietf.org/doc/html/rfc7748
- Python `cryptography` package: https://cryptography.io/

## Roblox

- Account/identity endpoint: https://users.roblox.com/v1/users/authenticated
- Join endpoints: https://gamejoin.roblox.com/v1/join-game, /join-game-instance, /join-private-game
- Steal a Brainrot (placeId): 109983668079237
- Steal An Egg (placeId): 107778070777162

## Python runtime

- Python 3.14 compression.zstd (standard library — required by `luau_bytecode.py`)
- `websockets>=13`

See also: [[lua-luau]], [[scripting]], [[rakbot-analysis/overview]].
