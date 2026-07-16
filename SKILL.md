---
name: generate-video-sprite-sequences
description: Generate game-ready 2D sprite or hand-painted action sequences from Seedance and other video-generation services, including API task submission, prompt/reference planning, distinct-action or repeated-take packing within minimum-duration clips, low-resolution multi-cell batching, precise frame extraction, chroma keying, canonical scale/root/baseline registration, take selection, resource accounting, and runtime manifests. Use when Codex needs to turn AI-generated video into consistent animation frames, compare video providers, reduce per-action generation cost, batch pixel-art motions, or import generated motion into a 2D/HD-2D game.
---

# 视频生成序列帧管线

Treat video generation as motion-source acquisition, not as the final game asset. Preserve accepted art, keep provider calls auditable, and reject inconsistent sequences before runtime import.

Current implementation status and planned Preview Lab milestones are recorded in [ROADMAP.md](ROADMAP.md). A planned milestone is not an available capability until its acceptance evidence is complete.

On every new user-facing project, first read and follow [references/user-intake-protocol.md](references/user-intake-protocol.md). Use it to tell the user what to provide, produce a free cost/batch preflight, and obtain a bounded paid-call authorization without ever asking the user to paste a secret. Read [references/getting-started.md](references/getting-started.md) for the detailed input contract. For Seedance Mini cost planning or comparison, also read [references/measured-seedance-mini-study.md](references/measured-seedance-mini-study.md); keep measured examples separate from current official prices.

## Core workflow

1. Inspect the target project and preserve accepted assets. Identify the playable entry point, canonical sprite contract, existing prompts/references, and fallback sequence.
2. Lock a sequence contract before calling any provider: action semantics, logic FPS, art FPS, duration, canvas, camera, facing, root, ground baseline, character scale, weapon length, safe margins, background, and active/hit frames.
   Classify each action as stationary, looping locomotion, or displaced root motion. For displaced motion, also lock the world-direction convention, expected root path, motion envelope, and padded canvas before choosing resolution or batch density.
3. Before writing a provider prompt, create an action-design preflight for every action: canonical start/end or loop seam, 4–6 key poses, facing/force direction, root path, body/weapon union, padded motion envelope, required final canvas, and source-cell pixel budget. Render a simple storyboard with `scripts/plan_action_storyboard.py`, inspect it, and preserve the plan beside the dry run. Do not make a paid call when an action lacks a storyboard or the proposed cell fails the envelope.
4. Read [references/provider-adapters.md](references/provider-adapters.md) before using any provider. For Seedance 2.0, also read [references/seedance-2-official.md](references/seedance-2-official.md). Verify current official documentation at execution time; provider model IDs, limits, request fields, billing, and result URL lifetimes are unstable.
   For any chroma-extracted character motion, derive the provider prompt from [references/clean-chroma-prompt-contract.md](references/clean-chroma-prompt-contract.md). Treat neutral character rendering, a uniform extraction field, and detached-VFX exclusion as separate mandatory sections rather than one vague “green screen” sentence.
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
- For a native gameplay character near 256 px standing height, prefer Seedance Mini 480p with one subject when its padded motion envelope and source-pixel budget pass. This is a measured human-accepted workflow default, not a universal provider guarantee. Select the aspect ratio independently for every action from the provider's currently supported ratios: fit the body/root/weapon union plus 20–30% safety padding with the least unused area, and do not force 4:3. Before every paid call, estimate that exact model, resolution, ratio, duration, subject count, and call count from the current official price plus the closest measured token anchor; show the estimate and bounded worst case before submission.
- For short actions inside a provider's longer minimum duration, honor explicit no-repeat/cost-maximization requests by packing distinct complete actions sequentially. Use repeated complete takes only when repetition is allowed and selection robustness matters. Never stretch one action into slow motion merely to fill the clip.
- Seedance 2.0 does not reliably obey exact per-beat timestamps. Describe ordered shots/action beats and detect the real motion boundaries after download.
- For simultaneous low-pixel batches, reserve fixed cells and gutters. Reject a layout when the expected source character height is below the required oversampled height.
- Prefer one-subject sequential packing or repeated takes of one action. A same-character grid with distinct actions is exceptional and must declare `packingMode: independent_grid_distinct_actions`, independent anchors, disjoint motion envelopes, no contact, no shared target, and no complementary roles. The prompt must call them independent animation previews that never interact and preserve an empty isolation corridor. Never pair attack with guard/hit/reaction or other complementary semantics. Billable preflight rejects an incomplete isolation contract.
- Generate pixel-style source larger than the final sprite, then downsample with nearest-neighbour and deliberately quantize the palette. Video generators are unreliable at literal 16–64 px output.
- For an established game character, require two default identity inputs for every generated action: the approved canonical runtime pixel Idle and an approved front/side/back turnaround rendered in the same native game-art style and practical gameplay quality. The Idle owns exact pixels, alpha, visible height, root, baseline, facing, proportions, costume, and palette; the turnaround owns hidden-side anatomy, costume placement, hair volume, front/back asymmetry, and three-dimensional identity continuity. Do not substitute high-resolution concept art, illustration, or a differently rendered model sheet. Build provider reference boards without smooth resampling; if enlargement is required, use only a declared integer nearest-neighbour scale.
- Do not require action keyframe reference art by default. Add an action-specific pose/keyframe board only when the user explicitly requests it or a declared exceptional action needs stronger pose/path control after ordinary identity references prove insufficient. Treat it as motion control only; it never replaces the runtime Idle or matching turnaround and must not introduce a different renderer, costume, scale, or identity.
- Treat one-frame edge specks and palette shimmer as temporal asset defects, not CSS antialiasing. Before temporal cleanup, audit the matte itself: estimate one robust key per video/take rather than per frame, key the full frame, despill, and downsample premultiplied color plus alpha coverage before making the final low-pixel contour binary. Stabilize locally before paying for regeneration: preserve raw frames, use confidence-banded alpha plus adjacent-frame consensus, remove only tiny pixels without a nearby motion trajectory, repair only tiny weak-alpha contour gaps supported by both adjacent frames, and map every frame in one action to one shared non-dithered palette. Process loop endpoints as temporal neighbors. Never use whole-frame median filtering, output-scale blur, optical flow, or per-frame cleanup that erases fast tips or creates trails; read [references/extraction-registration-qa.md](references/extraction-registration-qa.md).
- For a known constant chroma background, recover foreground edge colour with the compositing model `C = αF + (1-α)B` before downsampling; do not treat spill suppression as a green-channel clamp. Require every removed background region to be connected to the full-frame border, preserve enclosed chroma-like subject pixels, report protected interior candidates, and fail if any transparent region remains enclosed inside the retained subject. After registration, repair only residual green in a narrow contour band from nearby non-green subject chroma while preserving value and alpha. Use a general human-matting network only when the backing model is unavailable or materially non-constant, and first assess geometry drift, temporal behavior, weights/license, and whether it was trained for the subject domain. Never globally remove green when the character contains intentional green materials.
- Treat visible character size as a delivery gate. Measure the cleaned canonical-idle body in pixels for every cell/take and quality tier, register it to the declared target range with one shared transform per take, and inspect every action for scale popping. Do this on every run, even when canvas, root, and baseline metadata already match.
- When a provider is known to copy the input backing, prepare the identity board deterministically on the exact requested chroma before submission. Preserve original foreground pixels, record the source/output hashes and mask bounds, use one shared target height/baseline per board, and visually reject a mask that removes costume parts or leaves a large backing halo. Do not use a generative redraw merely to change the reference background.
- When raising native runtime precision, rebuild every frame directly from the preserved source video or full-resolution keyed frames. Never enlarge an existing low-resolution runtime PNG and label it native. Scale canvas, root, baseline, shared transform, motion envelope, and QA thresholds by the same declared factor; keep the same source PTS, action boundaries, state machine, and per-take transform semantics. Before export, project the full-action union into the larger canvas and reject any clipped pose.
- Compare a precision upgrade at the same on-screen size: for example, place a native 128×128 asset at CSS 256×256 beside a native 256×256 asset at CSS 256×256, with nearest-neighbour rendering, integer CSS dimensions, identical world root/baseline, lighting, frame index, and action state. Report both compressed bytes and decoded RGBA memory; doubling both dimensions costs exactly four times the decoded texture memory for the same frame count.
- Scale local temporal-cleanup radii and disposable-component limits with native precision, but do not introduce blur, interpolation, full-contour dilation, or cross-action voting. Reconcile any cyclic loop-only pass against the complete action afterward so start/end frames cannot retain newly exposed one-frame components. Require the final unsupported unprotected component count to be reported per action, not only as a tier total.
- Show the gameplay preview at 1:1 asset pixels or an explicitly labelled integer zoom. Never let responsive CSS, `object-fit`, or an unlabeled 2× enlargement hide an undersized or mismatched sprite.
- Request a locked camera, constant subject scale, fixed ground line, one complete subject per cell, no cuts, no zoom, no camera/global blur, no combat or environmental VFX, and no shadows when chroma extraction is required. The safest default is no authored trail. A stylized brief may explicitly allow motion-native deformation such as squash/stretch, contour smear, or a short limb-bound directional trail only when it passes the directional-trail gate below and preserves a clean extraction boundary.
- A stylized brief may push squash/stretch into pronounced spring or rubber-body motion: deep anticipation compression, long directional extension, overshoot, recoil, and elastic recovery are allowed. Keep one continuous body topology, the declared action path and gameplay facing, the support-foot/root contract, a sharp readable contact pose, stable identity/costume, and an exact recovery to the approved runtime Idle. Reject extra/disconnected limbs, detached body fragments, wrong-way stretch, permanent proportion drift, or deformation that hides the action.
- For game characters that will receive runtime lighting, request neutral albedo-reference illumination and stable exposure/white balance. Reject baked directional light, rim light, environmental colour cast, contact/cast shadows, reflection, dramatic highlight, per-action grade, and key-coloured illumination on the silhouette. A locally removable shadow or arc does not make the original generation visually accepted.
- Require an exact, temporally stable extraction field: the same declared key RGB across the entire background and all frames, with no gradient, floor, horizon, texture, vignette, noise, reflection, glow, shadow, exposure pulse, white-balance drift, or animation. Quantify border spatial variation and temporal drift before writing keyed frames; fail closed when either exceeds the declared contract instead of hiding source failure with a more aggressive matte.
- Keep the character-motion source clean. Generate hit sparks, impact flashes, shockwaves, energy slashes, explosions, ground cracks, dust, smoke, debris, footstep clouds, screen flashes, and camera shake separately unless the final game intentionally bakes a named effect into the sprites. Do not classify those effects as motion smear.
- **Attachment is not evidence of a valid smear.** Reject every circular or near-circular glow, blob, orb, halo, ring, disc, capsule, pressure puff, bloom, or luminous outline even when it touches, overlaps, or appears to originate from a fist, foot, hair, cloth, or weapon. A permitted trail must be elongated along the measured motion vector, remain behind or between the responsible part's previous and current positions, overlap the moving silhouette for most of its area, never extend ahead of the contact point, introduce no emission or colour shift, and disappear within one or two authored frames when the part slows. The contact/readability pose stays sharp. If shape, direction, placement, or lifetime is ambiguous, fail closed.
- Treat a contact sheet or grid video as a source container. Chroma-key the full frame first, group content by expected cell/take, then crop with padding; never assume generated figures remain inside exact equal cells.
- Use one take's frame-to-frame continuity as an acceptance gate: identity, anatomy, costume, weapon, camera, scale, root, support foot, and action arc must remain stable.
- Stop retries when the remaining problem is deterministic post-processing. Do not spend another provider call on crop, keying, timing, scale, or baseline issues that local tools can fix.
- Keep each model/provider result isolated through generation, extraction, registration, manifest, and runtime selection. Never overwrite a higher-cost accepted result while testing a cheaper model.
- In Godot, keep 128@2× and 256@1× at one world scale by deriving sprite offset from manifest root/baseline, not per-frame bounds. Convert a requested final-screen outline width back to source texels (`nativeRadius = round(screenPixels / displayScale)`), generate it from current alpha at runtime, and suppress it in normal-preview mode. Verify Nearest/Lossless/no-mipmap import, integer root motion, `start → loop → end`, action return-to-idle, tier switching, and comparison views inside an actual rendered Godot window; headless parsing alone is insufficient.
- Before committing or pushing this Skill, run `scripts/audit_publication_safety.py`. Never track an API key, Bearer credential, private key, signed result URL, provider task response, receipt, paid source video, private character reference, or user-project output in the public Skill repository. `.gitignore` is a guardrail, not proof; audit the actual tracked file set.
- Before every billable create-task call, run a fail-closed preflight over the current official price lock, bounded authorization, cumulative ledger, stable task key, receipt directory, redacted request fields, prompt guard phrases, reference hashes and credential presence. A task ID, ledger entry, receipt, or output makes creation non-idempotent and must block resubmission; polling and downloading remain resumable. Never print the credential or full private prompt in the preflight report.
- Declare every paid correction with a distinct task key and `retryOfTaskKey`. The preflight must prove that the source task exists in both plan and ledger, corrected actions are a subset of the failed source actions, and `paidRetryCount` remains below the authorized maximum; successful submission increments both paid task and paid retry counters atomically.
- Write an exclusive submission intent before the create-task network call. On success persist the raw task ID only in the private receipt/ledger before clearing that intent; on timeout, malformed response, or uncertain transport retain the intent and block automatic resubmission. Console output may expose only a task-ID hash, never the raw ID, signed URL, credential, base64 reference, or private prompt.

## Reusable tools

Plan a repeat or grid batch before generating:

```text
python scripts/plan_sequence_batch.py --mode repeat --provider-min-duration 4 --action-duration 0.8 --gap 0.3
python scripts/plan_sequence_batch.py --mode grid --width 1280 --height 720 --rows 2 --cols 2 --target-character-height 64
```

Estimate task and accepted-action cost before paying, then replace estimates with receipt tokens:

```text
python scripts/estimate_action_cost.py --resolution 480p --clips 2 --actions-per-clip 4 --acceptance-rate 0.625
python scripts/estimate_action_cost.py --resolution 720p --clips 1 --actions-per-clip 8 --actual-tokens 87850 --accepted-actions 2
```

Fail closed before a billable task creation:

```text
python scripts/preflight_billable_task.py --plan plan.json --ledger ledger.json --price-lock price.json --request request.json --receipt-dir receipts --credential-env PROVIDER_API_KEY
```

Prepare an exact-chroma identity board without generative redrawing:

```text
python scripts/prepare_chroma_reference_board.py approved-runtime-idle.png reference-board.png --canvas 752x560 --columns 1 --native-size --baseline-y 500 --chroma 0,255,0 --report reference-board.qa.json
```

Create exactly one preflighted Seedance task with a write-ahead receipt:

```text
python scripts/submit_seedance_task.py --plan plan.json --ledger ledger.json --price-lock price.json --request request.json --receipt-dir receipts --credential-env ARK_API_KEY
```

Resume, poll, and immediately download that existing task without another create call. The command prints only safe status and hashes; raw task IDs, provider responses, and signed URLs stay in the private receipt directory:

```text
python scripts/resume_seedance_task.py --ledger ledger.json --price-lock price.json --task-key stable-task-key --receipt-dir receipts --output-dir raw/task-key --credential-env ARK_API_KEY
```

Extract every original provider frame with its PTS, preserve full frames before cell crops, and generate motion/cell diagnostics plus a visual contact sheet:

```text
python scripts/extract_video_frames.py raw/provider.mp4 --frames-dir source-frames --report qa/extraction-report.json --contact-sheet qa/contact-sheet.png --columns 2 --rows 1
```

Create an auditable contiguous action window without copying or renumbering source frames:

```text
python scripts/slice_extraction_report.py --source-report qa/extraction-report.json --output-report qa/action-slice.json --start-source-index 0 --end-source-index-inclusive 23
```

Audit full-resolution keyed alpha topology, adjacent stability, and loop seam candidates before registration:

```text
python scripts/audit_keyed_sequence.py --key-report qa/key-report.json --output qa/temporal-matte-report.json --min-loop-frames 12
```

Repair only tiny enclosed one-frame alpha holes with opaque support in both temporal neighbours, then re-audit the new layer:

```text
python scripts/repair_temporal_alpha_holes.py --key-report qa/key-report.json --output-dir keyed/temporal-repaired --report qa/temporal-repair.json --max-component-pixels 24
```

Render a candidate cyclic window without resampling or modifying source pixels:

```text
python scripts/render_loop_preview.py --frame-report qa/temporal-repair.json --start-source-index 9 --end-source-index-inclusive 22 --fps 24 --gif qa/loop.gif --seam-sheet qa/loop-seam.png --report qa/loop-preview.json
```

After shared registration, pass the registration report plus `--action-id` to inspect the exact fixed-canvas original-colour frames with the same non-resampling preview gate.

Fail closed on tiny near-black islands that are spatial outliers inside the eroded opaque core and lack motion-radius support in both cyclic neighbours:

```text
python scripts/audit_registered_colour_stability.py --registration-report registration-report.json --action-id idle --output qa/registered-colour-stability.json
```

If that audit fails, repair only its explicitly listed pixels from opaque 8-neighbour RGB evidence, preserve alpha exactly, and then rerun the same audit on the new report:

```text
python scripts/repair_registered_colour_outliers.py --registration-report registration-report.json --audit-report qa/registered-colour-stability.json --action-id idle --output-dir registered/colour-repaired --report qa/colour-repair.json
```

For runtimes that generate normal response from current Beauty/alpha, build only aligned Beauty plus binary coverage after the colour audit passes; do not write authored Normal frames:

```text
python scripts/build_beauty_coverage_sequence.py --registration-report colour-repair.json --colour-audit registered-colour-stability-pass.json --action-id idle --art-fps 24 --output-dir runtime/beauty-coverage --report runtime/beauty-coverage.json
```

After final native-size registration, audit green excess again in the one-pixel opaque contour band. When the character contract explicitly declares no intentional green material, recover contaminated contour chroma from nearby clean eroded-core foreground while preserving each pixel's value and alpha:

```text
python scripts/repair_registered_contour_spill.py --registration-report registration-report.json --action-id idle --output-dir registered/contour-clean --report qa/contour-spill.json --qa-sheet qa/contour-spill.png --green-excess-limit 6 --no-intentional-green-material
```

Build one shared constant-chroma model for the complete extracted sequence, key full frames before cell crops, preserve PTS, and render dark/light/checker QA sheets. Declare the absence of intentional green explicitly; otherwise stop for a semantic protection mask or a different key colour:

```text
python scripts/key_chroma_sequence.py --extraction-report qa/extraction-report.json --output-dir keyed/full --report qa/key-report.json --qa-dir qa/key-sheets --columns 2 --rows 1 --no-intentional-green-material
```

After the full-frame key passes, split declared cells and register each take with one fixed premultiplied BOX transform into a shared canvas/root/baseline. The private contract owns cell/action windows and the canonical size; the tool fails safe-margin violations instead of recentering frames:

```text
python scripts/register_sprite_cells.py --contract registration-contract.json --output-dir registered --report registration-report.json --qa-sheet registration-qa.png --columns 2 --rows 1
```

Build sampled runtime candidates with one non-dithered palette per action and exactly aligned beauty/normal/mask channels. Treat luminance-derived normals as lighting-QA candidates, never as accepted physical truth before a rendered-light review:

```text
python scripts/build_pixel_sequence_channels.py --contract runtime-contract.json --output-dir runtime-candidate --report runtime-report.json --qa-sheet runtime-channels-qa.png
```

The runtime-channel build is also a fail-closed matte gate after resize, binary-alpha selection, and palette quantization. It must report adjacent foreground-area loss and exact Beauty/Normal/Mask alpha parity. Re-evaluate every enclosed transparent region at final native size: it is legitimate negative space only when the same pixels project from border-connected background in the preserved full-resolution keyed source under the recorded shared transform. Any enclosed region without that source support is an internal matte loss and blocks runtime registration. Do not fill all enclosed regions, dilate the silhouette, or hand-paint exceptions; those shortcuts destroy valid gaps between hair, cloth, limbs, and equipment.

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
python scripts/estimate_action_cost.py --self-test
python scripts/preflight_billable_task.py --self-test
python scripts/prepare_chroma_reference_board.py --self-test
python scripts/submit_seedance_task.py --self-test
python scripts/resume_seedance_task.py --self-test
python scripts/extract_video_frames.py --self-test
python scripts/slice_extraction_report.py --self-test
python scripts/audit_keyed_sequence.py --self-test
python scripts/repair_temporal_alpha_holes.py --self-test
python scripts/render_loop_preview.py --self-test
python scripts/audit_registered_colour_stability.py --self-test
python scripts/repair_registered_colour_outliers.py --self-test
python scripts/build_beauty_coverage_sequence.py --self-test
python scripts/repair_registered_contour_spill.py --self-test
python scripts/key_chroma_sequence.py --self-test
python scripts/remove_external_vfx.py --self-test
python scripts/register_sprite_cells.py --self-test
python scripts/build_pixel_sequence_channels.py --self-test
python scripts/build_godot_candidate_manifest.py --self-test
python scripts/visualize_motion_plan.py --self-test
python scripts/validate_sequence.py --self-test
python scripts/audit_publication_safety.py
```

## Delivery

- Deliver the selected sequence preview, extraction/contact sheet, runtime manifest, resource statistics, and direct game/open path.
- Include measured canonical-idle visible height, allowed range, pass/fail, root, baseline, and preview display scale for every selectable tier. Do not call the delivery complete until this size table and an actual gameplay-size visual pass are present.
- Report provider calls, generated duration, number of packed takes/cells, accepted take, extracted art FPS, final frame count, compressed bytes, and estimated decoded texture memory.
- State visual failures honestly. A structurally valid sequence is not accepted until its motion reads correctly at gameplay scale.
