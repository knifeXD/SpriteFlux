# Godot 4 runtime preview

Read this reference when importing a generated sprite sequence into Godot or migrating a browser preview.

## Asset boundary

- Preserve the accepted runtime and HTML preview. Create a separate Godot project and sync immutable PNG/JSON inputs with a deterministic script that records source mapping, byte size, and SHA256.
- Keep raw, hard-edge, temporal-stable, and optimized-key tiers selectable. If a tier lacks a native-size asset, mark the fallback explicitly.
- Import PNG textures Lossless with Nearest filtering, mipmaps off, and no lossy VRAM compression. Set the project canvas default filter to Nearest as a second guard.

## Registration and scale

- Treat the manifest canvas, root, and baseline as authoritative. Centered `Sprite2D` offset is `(canvas / 2 - root) * displayScale`; the parent node is the gameplay root.
- Snap the parent world position to integer pixels. Do not derive root or scale from the current frame's alpha bounds.
- Compare native 128 at 2× with native 256 at 1× at the same display size. Expect small authored-body-height differences, but never compensate per frame.

## Playback

- Load action frames and recorded art FPS from JSON/FileAccess. Preserve right-facing semantics.
- Use an explicit locomotion state machine: short `start`, true gait `loop` while held, short `end` on release, then canonical idle. Forward moves root right and backward moves root left while the character keeps facing right.
- Play non-looping actions once and return to idle. Keep missing actions labelled as fallbacks rather than substituting another quality silently.

## Runtime outline and lighting

- Generate exterior outline pixels in a `CanvasItem` shader by sampling current texture alpha inside the transparent canonical canvas. Do not modify PNG alpha, collision, root, normals, or shadow masks.
- Specify outline thickness in final screen pixels. Convert to texture samples with `nativeRadius = max(1, round(screenPixels / displayScale))`; therefore 128@2× uses radius 1 for a 2-screen-pixel outline, while 256@1× uses radius 2.
- Hide the outline in normal-preview mode. Keep lighting independent from alpha/key cleanup; alpha-gradient pseudo normals are useful for preview but are not authored normal maps.
- Use contact and cast-shadow nodes driven by the same root and light controls. Do not blur the sprite to hide temporal defects.

## Validation

1. Run Godot editor import and reject parse, shader, missing-resource, or import errors.
2. Run headless structural tests for manifests, canvas/root/baseline, all actions, InputMap, state transitions, tier paths, and outline-radius conversion.
3. Run a real graphics window. Long-play both quality tiers, forward/back `start → loop → end`, every non-loop action, return-to-idle, tier changes, and same-size comparison.
4. Capture screenshots with Godot's own viewport. Select comparison modes before the first rendered frame; switching after the first capture can produce incomplete OpenGL compatibility damage-region screenshots even when the live window is correct.
5. Show source, action/frame, tokens/cost, canvas/root/baseline, native/body/display sizes, green-edge/flicker QA, outline width/count, and fallback state.

Prefer native Godot nodes and shaders. Add a plugin only when a concrete feature cannot be covered natively; record its version, source, license, and reason.

Official references: [Godot Windows downloads](https://godotengine.org/download/windows/), [Godot documentation](https://docs.godotengine.org/).

