# AS Port Test Suite — WPAI-native, local-only

Testing tooling for the **Astral Sorcery → Forge 1.20.1 port**. Lives *outside* the
`astral-sorcery-port` workload (which is a registered Janus-receipt path — not directly mutated here).

## The correct architecture (two halves)

Porting bugs split cleanly, and each half has the *right* tool — which is **not** the external
Mineflayer/vision-bot the common tutorials push:

| Half | What breaks | Right tool | Status |
|------|-------------|-----------|--------|
| **Logic** | multiblock assembly, starlight networks, altar recipes, packet sync, perks | **Forge GameTest** (headless `GameTestServer`, in-engine, sees your block entities) + JUnit | **already in the port** (`AstralGameTests`, `src/test/…`) |
| **Render / VFX** | starlight beams, constellation lines, night sky, particles, custom shaders | **local vision-LLM** auditing screenshots | **added here** (`vfx_qa.py`) |

### Why not Mineflayer (the tutorial's answer)
Mineflayer has **no native Forge FML handshake** — a Forge server kicks it (or it silently
disconnects), its `minecraft-data` registry doesn't know AS's block IDs, and `block.blockEntity`
can't read custom modded tile-entity NBT. It's blind to modded content *and* to all rendering.
In-engine GameTest sidesteps all of that.

### Why local, not cloud
The tutorial ships frames to `gemini-2.5-flash` / GPT-4o. This suite uses a **local** vision model
through the same Ollama the rest of WPAI runs on — nothing leaves the box, no API key, no per-call
cost. Current good picks (July 2026): `qwen2.5vl:7b` (flagship, best on structured/UI), `minicpm-v`
(6 GB-VRAM friendly), `moondream` (<4 GB), `internvl2.5:8b` (strongest on UI/code screenshots).

## Tools

### `vfx_qa.py` — the render half
Audits a folder of screenshots for AS render-port failure modes (missing-texture magenta, shader
white-screen, beam/constellation/particle/altar glitches, UI clipping). Exit code = number of FAILs.

```bash
python vfx_qa.py --dir "C:/Users/<you>/.minecraft/screenshots" --scenario beam
VFX_VLM_MODEL=minicpm-v python vfx_qa.py --dir ./frames        # lighter model on a 6 GB card
```
Scenarios focus the checks: `general | beam | constellation | altar | particle`.

**Capturing frames** (decoupled on purpose): press **F2** in-game (frames land in
`.minecraft/screenshots`), or script a capture. Set up a scene (place an altar, fire a collector
beam, open the constellation view), screenshot from a few angles, point `vfx_qa.py` at the folder.
For repeatable shots, use fixed coordinates + `/tp` with set yaw/pitch, or the game's spectator cam.

### `run_regression.py` — one Janus-gateable verdict
Runs the port's headless GameTest (`gradlew runGameTestServer`, exit code = failed tests) **and**
the VFX QA, and writes one `regression-*.json` with an `overall` PASS/FAIL for Janus / the WPAI
blackboard to gate on. `--skip-logic` / `--skip-render` to run one half.

```bash
python run_regression.py --port "C:/WPAI/Gaming/Minecraft/Mods-1.20.1-Forge/Astral_Sorcery_Port" \
                         --frames "C:/Users/<you>/.minecraft/screenshots" --scenario constellation
```

## Notes verified July 2026
- Forge **1.20.1 uses `SimpleChannel`**; the `CustomPacketPayload` network rewrite is NeoForge 1.20.4+.
- Forge GameTest requires MC ≥1.18.1 / Forge ≥39.0.88 — 1.20.1 (forge 47.3.0) qualifies.
- `MatrixStack→PoseStack`, `DeferredRegister`, `RegisterShadersEvent` are correct for 1.20.1; but much
  AS rendering needs buffer/pose-API migration (`VertexConsumer`/`MultiBufferSource`), not new shaders.
- `online-mode=false` (needed for any scripted client) disables auth — localhost only, never public.
