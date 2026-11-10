# Lua / Luau

Snippets, patterns, and language notes.

## In this project

Rakbot inspects **compiled Luau bytecode (version 14)** statically. It never executes it. The flow (see [[rakbot-analysis/file-manifest#luau-bytecode-py]] and [[rakbot-analysis/file-manifest#luau-static-py]]):

1. A captured `0x9b` / RSB1 packet arrives.
2. `luau_bytecode.unpack_rsb` decompresses it with Python 3.14's `compression.zstd`.
3. `luau_static.parse`:
   - Reads the 2-byte version header (expects `0e 03`).
   - Walks the string table (bounded 65 535 entries).
   - Reads per-function headers using line-info skip markers.
   - Walks instructions. Opcode names come from `Bytecode.h`'s `LuauOpcode` enum (regex `^\s*LOP_([A-Z0-9_]+),`). The 2-slot opcodes come from `BytecodeUtils.h`'s `getOpLength` switch (regex `case LOP_(...)`).
4. Catalog data (`Animals`, `Mutations`, `Traits`) is extracted as literal table constants via `egg_catalog.literal_tables` — a bounded straight-line dataflow walk, not an interpreter.

## Differences at a glance

- Luau adds types, `continue`, compound assignment, string interpolation, generalized iteration.
- Luau has stricter mode and sandboxing hooks (Roblox context).
- Luau bytecode format diverges from Lua 5.x — opcode set and encoding are its own.

## Snippets

(none yet — add as needed when extending the static reader or writing new catalog extractors)

See also: [[scripting]], [[references]], [[rakbot-analysis/architecture]].
