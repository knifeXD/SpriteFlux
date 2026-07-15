---
name: generate-video-sprite-sequences
description: Generate game-ready 2D sprite or hand-painted action sequences from Seedance and other video-generation services, including API task submission, prompt/reference planning, distinct-action or repeated-take packing within minimum-duration clips, low-resolution multi-cell batching, precise frame extraction, chroma keying, canonical scale/root/baseline registration, take selection, resource accounting, and runtime manifests. Use when Codex needs to turn AI-generated video into consistent animation frames, compare video providers, reduce per-action generation cost, batch pixel-art motions, or import generated motion into a 2D/HD-2D game.
---

# 视频生成序列帧管线

Treat video generation as motion-source acquisition, not as the final game asset. Preserve accepted art, keep provider calls auditable, and reject inconsistent sequences before runtime import.

## Core workflow

1. Inspect the target project and preserve accepted assets. Identify the playable entry point, canonical sprite contract, existing prompts/references, and fallback sequence.
2. Lock a sequence contract before calling any provider: action semantics, logic FPS, art FPS, duration, canvas, camera, facing, root, ground baseline, character scale, weapon length, safe margins, background, and active/hit frames.
   Classify each action as stationary, looping locomotion, or displaced root motion. For displaced motion, also lock the world-direction convention, expected root path, motion envelope, and padded canvas before choosing resolution or batch density.
3. Before writing a provider prompt, create an action-design preflight for every action: canonical start/end or loop seam, 4–6 key poses, facing/force direction, root path, body/weapon union, padded motion envelope, required final canvas, and source-cell pixel budget. Render a simple storyboard with `scripts/plan_action_storyboard.py`, inspect it, and preserve the plan beside the dry run. Do not make a paid call when an action lacks a storyboard or the proposed cell fails the envelope.
4. Read [references/provider-adapters.md](references/provider-adapters.md) before using any provider. For Seedance 2.0, also read [references/seedance-2-official.md](references/seedance-2-official.md). Verify current official documentation at execution time; provider model IDs, limits, request fields, billing, and result URL lifetimes are unstable.
5. Choose one packing strategy using [references/prompt-and-batching.md](references/prompt-and-batching.md):
   - one action per clip for long or complex motion;
   - sequential distinct actions in one minimum-duration clip when the user prioritizes unique-action yield or forbids repeats;
   - repeated takes in one minimum-duration clip when selection robustness matters and repetition is allowed;
   - fixed-grid multi-subject generation only for low-resolution output that passes the source-pixel budget; prefer fewer simultaneous characters when the cost difference is small because action logic and identity are more controllable.
6. Generate a dry-run request preview containing no secret and no billable submission. Store API keys only in environment variables or an ignored secret file. Require explicit user authorization before the first billable call; do not ask again for retries already covered by that authorization, but cap automatic retries.
7. Submit, poll, download immediately, and preserve the raw response plus provider task ID. Never depend on a temporary result URL after import.
8. Split repeated takes by authored time windows. Extract frames from presentation timestamps; do not assume the provider's nominal FPS. Keep all takes until visual selection is complete.
9. Remove the background, then apply one shared affine transform per take. Never normalize individual frames from their own alpha bounds. Read [references/extraction-registration-qa.md](references/extraction-registration-qa.md).
10. Visually compare takes at gameplay size. Select the best coherent take, not the sharpest isolated frames from different takes. Mixing takes often causes identity, scale, costume, and weapon discontinuity.
   Before acceptance, run the mandatory size pass from [references/extraction-registration-qa.md](references/extraction-registration-qa.md) on every source cell/take and every selectable quality tier. A shared canvas size is not evidence that the visible character size matches.
11. Write a runtime manifest with source task, prompt hash, extraction timestamps, logic-to-art hold map, shared transform, root/baseline, alpha bounds, selected take, resource cost, and QA state.
12. Integrate as a new selectable/fallback sequence until the generated result passes gameplay QA. Play extracted frames from their recorded source timestamps or source FPS unless the product contract explicitly requests retiming. Do not destructively overwrite the last accepted animation.
    For a Godot 4 runtime or preview, read [references/godot-runtime-preview.md](references/godot-runtime-preview.md) before importing frames or writing the state machine.
13. Update reusable findings only after an end-to-end run is visually verified.

## Hard rules

- Keep logic FPS independent from authored art FPS. A 30 FPS combat timeline may use 10 FPS art with explicit holds such as `1拍3`.
- Default every independently reusable action to an idle envelope: begin from the canonical idle pose, perform one complete action, and return to the same canonical idle pose. Allow a different start/end only when gameplay explicitly requires locomotion continuity, a held state, knockdown, death, a combo link, or another declared terminal pose.
- For side-view pixel characters, default the authored facing to screen-right unless the brief says otherwise. Treat attacks and impacts as frontal from screen-right: block receives force from the right, hit reaction recoils left, forward movement/dodge travels right, and backward movement/dodge travels left while the face and torso remain oriented right. Do not mirror or reverse these semantics implicitly.
- Author forward and backward walking as seamless locomotion loops with matching cycle endpoints. `walk_forward` moves right while facing right; `walk_backward` moves left while still facing right. A loop cycle is an explicit exception to the idle-envelope rule, but entering and exiting locomotion must still transition cleanly to canonical idle.
- Never loop an entire generated `idle → locomotion → idle` clip. After extraction, use PTS, motion energy, and visual pose comparison to trim locomotion into `start`, one seamless `loop` cycle, and `end`. Store explicit source-frame/timestamp lists and playback FPS for all three phases in the runtime manifest. Keep start/end brisk (normally about 0.15–0.30 seconds when the source permits), loop only the true gait cycle while input is held, and play end once on release before returning to canonical idle. Test press, hold, release, rapid repress, and forward/back direction changes in the actual state machine.
- Preserve intentional displacement. A jump, lunge, forward/back dodge, knockback, or other root-motion action must carry a recorded root-motion path and receive enough padded canvas for its full union. Do not prompt it as in-place, recenter each frame, or cancel the translation during registration unless the user explicitly requests an in-place game animation.
- Default to the lowest supported resolution that safely passes character-pixel, padded motion-envelope, direction, and identity gates; for the current Seedance Mini pixel-character workflow, use 480p whenever it fits. Prefer fewer simultaneous cells/characters over maximizing theoretical actions per request because lower subject count improves motion logic, direction control, and identity consistency. Escalate to 720p only when 480p would clip real displacement, shrink the character below budget, or has measured acceptance yield poor enough to erase the cost advantage. Compare candidates using actual or estimated `cost / fully accepted distinct action`.
- For short actions inside a provider's longer minimum duration, honor explicit no-repeat/cost-maximization requests by packing distinct complete actions sequentially. Use repeated complete takes only when repetition is allowed and selection robustness matters. Never stretch one action into slow motion merely to fill the clip.
- Seedance 2.0 does not reliably obey exact per-beat timestamps. Describe ordered shots/action beats and detect the real motion boundaries after download.
- For simultaneous low-pixel batches, reserve fixed cells and gutters. Reject a layout when the expected source character height is below the required oversampled height.
- Generate pixel-style source larger than the final sprite, then downsample with nearest-neighbour and deliberately quantize the palette. Video generators are unreliable at literal 16–64 px output.
- Treat one-frame edge specks and palette shimmer as temporal asset defects, not CSS antialiasing. Before temporal cleanup, audit the matte itself: estimate one robust key per video/take rather than per frame, key the full frame, despill, and downsample premultiplied color plus alpha coverage before making the final low-pixel contour binary. Stabilize locally before paying for regeneration: preserve raw frames, use confidence-banded alpha plus adjacent-frame consensus, remove only tiny pixels without a nearby motion trajectory, repair only tiny weak-alpha contour gaps supported by both adjacent frames, and map every frame in one action to one shared non-dithered palette. Process loop endpoints as temporal neighbors. Never use whole-frame median filtering, output-scale blur, optical flow, or per-frame cleanup that erases fast tips or creates trails; read [references/extraction-registration-qa.md](references/extraction-registration-qa.md).
- For a known constant chroma background, recover foreground edge colour with the compositing model `C = αF + (1-α)B` before downsampling; do not treat spill suppression as a green-channel clamp. After registration, repair only residual green in a narrow contour band from nearby non-green subject chroma while preserving value and alpha. Use a general human-matting network only when the backing model is unavailable or materially non-constant, and first assess geometry drift, temporal behavior, weights/license, and whether it was trained for the subject domain. Never globally remove green when the character contains intentional green materials.
- Treat visible character size as a delivery gate. Measure the cleaned canonical-idle body in pixels for every cell/take and quality tier, register it to the declared target range with one shared transform per take, and inspect every action for scale popping. Do this on every run, even when canvas, root, and baseline metadata already match.
- When raising native runtime precision, rebuild every frame directly from the preserved source video or full-resolution keyed frames. Never enlarge an existing low-resolution runtime PNG and label it native. Scale canvas, root, baseline, shared transform, motion envelope, and QA thresholds by the same declared factor; keep the same source PTS, action boundaries, state machine, and per-take transform semantics. Before export, project the full-action union into the larger canvas and reject any clipped pose.
- Compare a precision upgrade at the same on-screen size: for example, place a native 128×128 asset at CSS 256×256 beside a native 256×256 asset at CSS 256×256, with nearest-neighbour rendering, integer CSS dimensions, identical world root/baseline, lighting, frame index, and action state. Report both compressed bytes and decoded RGBA memory; doubling both dimensions costs exactly four times the decoded texture memory for the same frame count.
- Scale local temporal-cleanup radii and disposable-component limits with native precision, but do not introduce blur, interpolation, full-contour dilation, or cross-action voting. Reconcile any cyclic loop-only pass against the complete action afterward so start/end frames cannot retain newly exposed one-frame components. Require the final unsupported unprotected component count to be reported per action, not only as a tier total.
- Show the gameplay preview at 1:1 asset pixels or an explicitly labelled integer zoom. Never let responsive CSS, `object-fit`, or an unlabeled 2× enlargement hide an undersized or mismatched sprite.
- Request a locked camera, constant subject scale, fixed ground line, one complete subject per cell, no cuts, no zoom, no motion blur, no VFX, and no shadows when chroma extraction is required.
- Generate combat VFX separately from the clean character motion unless the final game intentionally bakes effects into the sprites.
- Treat a contact sheet or grid video as a source container. Chroma-key the full frame first, group content by expected cell/take, then crop with padding; never assume generated figures remain inside exact equal cells.
- Use one take's frame-to-frame continuity as an acceptance gate: identity, anatomy, costume, weapon, camera, scale, root, support foot, and action arc must remain stable.
- Stop retries when the remaining problem is deterministic post-processing. Do not spend another provider call on crop, keying, timing, scale, or baseline issues that local tools can fix.
- Keep each model/provider result isolated through generation, extraction, registration, manifest, and runtime selection. Never overwrite a higher-cost accepted result while testing a cheaper model.
- In Godot, keep 128@2× and 256@1× at one world scale by deriving sprite offset from manifest root/baseline, not per-frame bounds. Convert a requested final-screen outline width back to source texels (`nativeRadius = round(screenPixels / displayScale)`), generate it from current alpha at runtime, and suppress it in normal-preview mode. Verify Nearest/Lossless/no-mipmap import, integer root motion, `start → loop → end`, action return-to-idle, tier switching, and comparison views inside an actual rendered Godot window; headless parsing alone is insufficient.

## Reusable tools

Plan a repeat or grid batch before generating:

```text
python scripts/plan_sequence_batch.py --mode repeat --provider-min-duration 4 --action-duration 0.8 --gap 0.3
python scripts/plan_sequence_batch.py --mode grid --width 1280 --height 720 --rows 2 --cols 2 --target-character-height 64
```

Design actions and calculate padded canvases before prompt authoring:

```text
python scripts/plan_action_storyboard.py action-plan.json --output preflight
```

Render an offline visual dashboard from the envelope report and optional measured costs:

```text
python scripts/visualize_motion_plan.py preflight/envelope-report.json --costs cost-report.json --output motion-plan.html
```

Validate a normalized sequence manifest and its images:

```text
python scripts/validate_sequence.py path/to/manifest.json
```

Run script self-tests after modifying this Skill:

```text
python scripts/plan_sequence_batch.py --self-test
python scripts/plan_action_storyboard.py --self-test
python scripts/visualize_motion_plan.py --self-test
python scripts/validate_sequence.py --self-test
```

## Delivery

- Deliver the selected sequence preview, extraction/contact sheet, runtime manifest, resource statistics, and direct game/open path.
- Include measured canonical-idle visible height, allowed range, pass/fail, root, baseline, and preview display scale for every selectable tier. Do not call the delivery complete until this size table and an actual gameplay-size visual pass are present.
- Report provider calls, generated duration, number of packed takes/cells, accepted take, extracted art FPS, final frame count, compressed bytes, and estimated decoded texture memory.
- State visual failures honestly. A structurally valid sequence is not accepted until its motion reads correctly at gameplay scale.
