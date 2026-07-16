# Extraction, registration, and QA

## Preserve the source

Keep the downloaded video, provider response, prompt, reference hashes, and task ID outside the runtime asset directory. Runtime outputs must be reproducible from these sources.

Probe the file before extraction: coded size, display aspect, duration, average and real frame rates, time base, rotation metadata, alpha, color space, and start PTS.

## Frame extraction

- Use timestamps/PTS. A provider may return 24 FPS even when the game logic is 30 FPS.
- `fps=N` copies, drops, or duplicates frames to a constant rate; it does not create genuinely new motion.
- Extract an art sequence at its intended art FPS, not the game's logic FPS.
- For repeated takes, cut each take window first, then sample within it. Save original timestamp beside every frame.
- Detect duplicate/frozen frames with perceptual difference; keep intentional impact holds but reject accidental frozen runs.
- Avoid motion-blurred source frames for sprite art. Prefer clear authored-looking phases around the blur.

## Chroma key

Estimate the key from border pixels only when the border is known to be background. For a stable chroma clip, estimate one robust key model from green-dominant border samples across the complete video or take; do not independently re-estimate the key on every frame. Build alpha from color distance plus color dominance, optionally feather 0.5–1.5 pixels at source resolution for non-pixel output, and despill before resizing.

Before writing any keyed frame, quantify the source field itself. Record the shared key RGB, border colour-distance P50/P95/P99, per-sampled-frame border median, maximum temporal drift from the shared key, and the configured limits. Fail closed when spatial variation or temporal drift exceeds the contract. A stronger matte is not a valid cure for a gradient, animated background, exposure/white-balance pulse, floor shadow, glow, or key-coloured lighting on the subject.

Use two complementary background confidences: proximity to the shared key RGB removes ordinary near-key background, while key-channel dominance captures darker/lighter chroma variations and mixed antialiased edges. Combine them into one alpha estimate, then recover edge foreground colour with the compositing equation below. Never choose a different key per frame; that converts background drift into foreground shimmer.

Do not remove a chroma-like pixel solely from its colour score. The candidate background region must also connect to the full-frame border before cell cropping. Preserve enclosed chroma-like pixels as foreground, report their count, and fail closed if the resulting matte contains a transparent region enclosed inside the retained subject. This topology gate prevents costume, skin, and shaded body regions near the key colour from turning into internal holes; it is not permission to dilate the whole silhouette.

Topology protection must restore colour as well as alpha. A pixel that was first classified as key background may already contain key-colour RGB or a despilled near-black value; merely forcing its alpha back to opaque creates dark/green specks inside the body. Before the final spill cap, propagate colour only into topology-protected foreground pixels from adjacent retained foreground with valid colour, using a bounded local median or wavefront and preserving the protected pixel's alpha. Report the recovered-pixel count. Never borrow from transparent background, change the silhouette, globally clamp green, or use this pass to repaint ordinary dark costume detail.

Repeat the topology check on final native-size Beauty/Normal/Mask after shared registration, premultiplied reduction, binary alpha, and palette quantization. A final enclosed transparent region is allowed only when it projects from border-connected background in the preserved full-resolution keyed frame through the recorded source crop and shared transform; report it as source-connected negative space. Treat every unsupported enclosed pixel as matte loss and fail closed. Also fail on declared adjacent foreground-area drops or any channel-alpha mismatch. This source-evidence rule preserves legitimate gaps between hair, cloth, limbs, and equipment without permitting a blanket hole fill.

Alpha integrity does not prove colour stability. At final gameplay size, measure opaque near-black spatial outliers and their frame-to-frame variation inside an eroded foreground core. If video noise or unstable shading becomes isolated black specks after palette mapping, repair only pixels that are substantially darker than their opaque local neighbourhood under an explicit contract; preserve alpha, silhouette, coherent outlines, eyes, seams, and sustained shadow masses. Report repaired pixels per frame and recheck the full loop. Do not use whole-frame blur, temporal averaging, global black removal, grade changes, or lighting to hide RGB flicker.

Run the colour-stability audit again after the shared fixed palette is applied. Nearest palette assignment can map an otherwise moderate source pixel to the darkest palette entry and recreate a speck that did not exist in the pre-palette cleanup. A post-palette repair may change only a small dark connected component that is inside an eroded opaque core, substantially darker than its immediate opaque neighbourhood, and unsupported within a declared motion radius in both temporal neighbours (including the loop seam). Stable eyes, outlines, seams, hair masses, and costume shadows therefore remain protected by connectivity or temporal support. Report this post-palette count separately from pre-palette repairs.

Inspect keyed frames on dark, light, and checkerboard backgrounds. Reject green fringes, holes in similarly colored costume regions, transparent weapons, and background shadows. If costume colors conflict with green, regenerate on another key color or use matte segmentation.

### Foreground-colour recovery and green-spill suppression

Constant-colour matting is a compositing inversion problem, not merely an HSV selection. Smith and Blinn formalize the observation as `C = αF + (1-α)B` and explain why the unconstrained problem is underdetermined. When this workflow has a measured, nearly constant backing colour `B` and a stable alpha estimate, recover mixed edge colour with `F = (C - (1-α)B) / α` before premultiplied coverage reduction. Clamp numerical extremes and leave high-confidence opaque foreground unchanged. References: [Microsoft Research publication](https://www.microsoft.com/en-us/research/publication/blue-screen-matting-2/) and [SIGGRAPH paper PDF](https://graphics.stanford.edu/courses/cs148-10-summer/docs/1996--smith_blinn--blue_screen_matting.pdf).

After registration and temporal silhouette stabilization, measure green excess only in a narrow contour band. For retained contaminated pixels, borrow chroma from nearby masked subject pixels that are below the green-excess threshold, scale that chroma to preserve the source pixel's value, and apply a small final excess cap. Do not change alpha in this colour-repair pass. If the character contract contains intentional green material, exclude it with a material/semantic mask or use another key colour; never sanitize the whole palette blindly.

Background Matting V2 is a strong alternative when a separate clean background image is available; its official implementation explicitly requires that additional background and uses a learned high-resolution refinement model. Robust Video Matting uses recurrent temporal memory and needs no auxiliary background, but it is a general human-video model rather than a deterministic chroma solver. Prefer these learned methods when the backing is unknown, textured, or changing, not automatically for a clean constant key where preserving tiny authored pixel geometry is the main gate. References: [Background Matting V2 project](https://grail.cs.washington.edu/projects/background-matting-v2/), [official BGMv2 repository](https://github.com/PeterL1n/BackgroundMattingV2), [RVM paper](https://arxiv.org/abs/2108.11515), and [official RVM repository](https://github.com/PeterL1n/RobustVideoMatting).

In the verified 256×256 project pass, full-video background estimation, compositing inversion, premultiplied BOX reduction, binary alpha, registered narrow-band colour reconstruction, and a fixed non-dithered action palette reduced measured retained contour pixels with green excess above 6 from 52,374 to 0 for the 480p sources and from 57,418 to 0 for the 720p source. Unsupported unprotected one-frame components remained 0. This character has no intentional green material, so its shared palette may also be sanitized; that project-specific permission must not be generalized.

Audit the actual rendered game canvas after lighting and display quantization, not only the PNG. Independent channel rounding can recreate a one-step green excess even from a clean palette. In the same verified preview, the source sprites measured 0 green-excess pixels but lighting quantization produced as many as 30 in a sampled 720p walk frame. Applying the declared no-green material constraint after lighting quantization reduced every sampled 480p/720p action canvas to 0 without changing alpha, root, or silhouette. Do not apply this constraint when intentional green materials exist.

Lightweight video models can synthesize chroma-coloured trails or rim contamination
even when the prompt forbids VFX. When the source background itself is clean and no
paid retry is allowed, use a separately recorded strict-key profile: extend the matte
range for green-dominant mixed pixels, combine distance and green-excess confidence,
and despill all non-opaque edge pixels. Recheck intentional green gems, costume accents,
and weapons on dark/light/checker backgrounds; a lower green-edge count is not enough
if semantic foreground details were erased.

### Low-pixel re-key and constrained contour repair

For final sprites around 64–128 px high, source-alpha blur and direct straight-RGBA nearest-neighbour reduction can make the game preview softer than the video while also causing edge pixels to blink. Use this order:

1. Estimate one robust chroma key per complete video/take from green-dominant border samples across many frames. Exclude white grid strokes, dark gutters, foreground contamination, and extreme distance outliers.
2. Key the full video frame before cell cropping. Remove known cell-divider bands or boundary-connected divider components before scaling.
3. Despill RGB in proportion to background confidence. Do not blanket-desaturate opaque costume pixels.
4. Downsample premultiplied RGB and alpha coverage together with an area/BOX filter. Unpremultiply after reduction, then decide the final low-pixel contour. Do not blur alpha at output scale.
5. Use binary final alpha for deliberately crisp pixel art unless the art contract explicitly retains coverage alpha. Quantize with one fixed palette per action/take and disable dithering.
6. Repair a missing contour corner only when it is a tiny 1–2 px weak-alpha component, is tightly surrounded by the current silhouette, and has nearby foreground support in both adjacent frames. Fill its color from the retained coverage sample or immediate opaque neighbours.
7. Protect moving hair, cloth, hands, feet, weapon tips, and VFX anchors with a motion neighbourhood. Prefer leaving an uncertain gap over applying full-frame morphological close, median filtering, or dilation.
8. Preserve the previous runtime tier and report key RGB/statistics, restored corner pixels, temporal fills, removed one-frame components, final palette size, semi-transparent count, silhouette IoU, and dark/light/checker QA.

In the verified 128×128 experiment, the final video-wide key plus premultiplied BOX reduction, binary alpha, per-action fixed palette, motion-neighbourhood protection, constrained corner repair, loop-subgroup handling, and complete-action reconciliation reduced measured unsupported edge pixels from 289 to 0 for 480p sources and from 293 to 0 for 720p sources. Treat these values as reference measurements, not universal thresholds.

### Native precision upgrade from preserved video

When a runtime needs higher native pixel precision, return to the preserved MP4 or full-resolution keyed frames. Do not upscale the old runtime PNGs. Apply one scaled copy of the accepted registration contract: if the canvas doubles from 128×128 to 256×256, double the root, baseline, offsets, shared transform, motion envelope, and declared idle-height range while retaining the exact source PTS, action boundaries, and state-machine phases. Check the union of every accepted action before writing frames.

Run the same full-video key and premultiplied coverage reduction at the new target size. Scale only spatial cleanup limits that are defined in asset pixels. Keep final alpha binary for crisp pixel art, use one non-dithered palette per action, protect fast thin features, and never substitute blur, optical flow, interpolation, whole-frame median filtering, or full-outline dilation. If a loop subgroup is processed cyclically, run a final complete-action reconciliation without cross-action neighbours.

For visual QA, compare both assets at identical CSS dimensions and gameplay state. A valid 128-versus-256 check uses 128 native pixels enlarged by an integer 2× and 256 native pixels at 1×, both displayed at 256 CSS pixels with nearest-neighbour rendering, identical root/baseline, lighting, frame index, and world displacement. Record internal canvas, CSS size, visible idle height, frame count, compressed bytes, decoded RGBA bytes, semi-transparent output count, and unsupported unprotected component count per action. Doubling both dimensions uses four times the decoded RGBA memory for the same frame count.

In the verified native-precision run, 420 frames were rebuilt independently at each precision from the same three source MP4 files. The 128×128 tier used root `[64,112]` and a 70–71 px canonical body; the 256×256 tier used root `[128,224]` and a 140–142 px canonical body. Final unsupported edge components were 0 for every action in both 480p and 720p sources. Compressed PNG bytes increased from 2,376,909 to 6,730,137, while decoded RGBA memory increased from 27,525,120 to 110,100,480 bytes. These are project measurements, not universal compression ratios.

### Temporal pixel stabilization

Apply this after registration and final nearest-neighbour reduction when isolated edge pixels or colors flicker between otherwise valid frames:

1. Preserve the original runtime sequence and write a separate stabilized tier.
2. Split alpha into low, decision, and high-confidence bands. Apply previous/next agreement only to ambiguous edge pixels; never vote over the whole silhouette.
3. Mark a one-frame component as disposable only when it is small and has no foreground trajectory within a small spatial radius in both temporal neighbors. Protect coherent motion around hair, cloth, hands, feet, weapon tips, and VFX anchors.
4. Treat idle and locomotion loops cyclically so the last and first loop frames are neighbors. Do not let different actions vote into each other.
5. Build one fixed palette per action/take and map every opaque pixel to it with dithering disabled. Do not independently derive a palette per frame.
6. Record before/after one-frame outliers, semi-transparent pixels, palette size, per-frame silhouette IoU, high-confidence pixel retention, and loop-seam change. Inspect raw/stabilized contact sheets on dark and light backgrounds.
7. Reject the pass if it creates trails, removes meaningful thin features, changes canvas/root/baseline/timing, or lowers silhouette fidelity beyond the declared tolerance. Prefer leaving a doubtful moving cluster intact over deleting it.

In the verified 128×128 pixel-character experiment, a conservative three-pixel component limit with a two-pixel motion neighborhood removed 97.8% of measured 480p outliers and 86.9% of 720p outliers while retaining at least 99.825% and 99.831% of high-confidence pixels respectively. Treat these as reference measurements, not universal thresholds.

## Shared registration

If a keyed source contains a contract-forbidden effect but otherwise passes motion and identity QA, preserve the keyed source and remove the effect only into a separate versioned diagnostic layer before registration. Use `scripts/remove_external_vfx.py` with an explicit frame range, ROI, colour gate, minimum removal count, and protected opaque-subject radius. For effects with opaque detached fragments, `removeAllUnprotectedForeground` plus `protectLargestOpaqueComponentOnly` may be used; the tool must fail closed if any protected subject core changes. Inspect the cleaned result on dark, light, and checker backgrounds. A short contour smear attached to the moving body may remain only when the action contract explicitly permits it and it is elongated along measured motion, behind/between prior and current part positions, mostly silhouette-overlapping, non-emissive, colour-neutral, never ahead of contact, and gone within one or two authored frames after deceleration. Circular/elliptical glow, blob, orb, halo, ring, disc, capsule, pressure puff, bloom, or luminous outline is forbidden even when attached to or overlapping a limb or weapon. Unless the product explicitly approves the cleaned source, deterministic removal does not retroactively make the original provider generation visually accepted.

For motion-texture QA, compare the responsible part across adjacent frames and inspect a local ROI. Fail closed when the candidate component is near-isotropic instead of elongated, lies mainly outside the body mask, extends ahead of the measured motion/contact point, changes hue or luminance like emission, or persists after the part settles. This motion-aware check supplements, and never replaces, gameplay-size human inspection.

Registration order:

1. key/matte the full video frame;
2. select one reference frame or authored root track for the entire take;
3. compute one uniform scale from camera/canvas geometry, never per-frame alpha height;
   integer raster dimensions may differ by at most the one-source-pixel quantization bound after rounding; reject larger effective X/Y scale divergence;
4. compute one X/Y placement from canonical root and baseline;
5. apply that exact transform to every frame in the take;
6. record natural root motion separately if the action intentionally lunges or jumps.

For displaced actions, estimate the support-foot/pelvis root at each accepted frame, smooth only tracking noise, and store the resulting `rootMotion` curve in asset pixels or world units. Keep the sprite frame registered to the canonical root and apply the recorded world displacement exactly once at runtime. Never both preserve baked translation in the frame and apply the same curve again.

Do not clamp a shared baseline correction to a small convenience range. Provider
framing can leave hundreds of source pixels beneath the support foot; clamping the
offset silently imports a floating actor even though every frame remains internally
consistent. Compute the full correction from the chosen registration frame, then
reject the take if that one shared transform would clip any frame rather than reducing
the correction. Treat later alpha-bottom excursions from weapons, trails, skirts, or
deep impact poses as diagnostics, not as reasons to renormalize individual frames.

The lowest alpha pixel is not always the support foot; it may be cloth, hair, a weapon, shadow, or antialiasing. Measure the foot/contact region explicitly. Do not cancel intentional crouch/jump height changes by per-frame normalization.

### Match an imported take to an existing idle sprite

When a provider keeps the camera fixed but renders the subject smaller than the accepted idle sprite, compute one additional scale from a declared stable reference frame and the idle reference. Apply that same scale to every frame around the canonical root; never fit each frame to the idle alpha bounds.

Before writing assets, project every frame bbox through the proposed shared transform and calculate the union. If the union fits the canonical canvas, choose the smallest shared X/Y translation that keeps the full union inside it and record the transformed root. If it does not fit, enlarge the canonical canvas or lower the one sequence scale; do not crop individual poses. Store the idle bbox, source reference bbox, uniform scale, shared offset, transformed root, and pre/post bboxes in the manifest. Add an asset revision to invalidate cached frames in web previews.

Generate a QA sheet that places idle, the normalized reference frame, and at least one impact/recovery frame on the same baseline. A matching canvas size is not evidence of matching character size; compare visible alpha height and body mass at gameplay scale.

### Mandatory size pass for every delivery

Run this after keying and again in the actual runtime preview for every source cell/take and every quality/provider choice:

1. Declare the target visible body height and tolerance before import. For this project's 128×128 pixel-character contract, the canonical-idle body must be 64–72 px.
2. Measure the largest connected canonical-idle body component after the same chroma cleanup used for export. Exclude key-field residue, grid gutters, detached shadows, VFX, and long detached weapon pixels from the body-height measurement.
3. Compute one transform from that cleaned canonical idle and apply it unchanged to the whole take. Never use a noisy whole-cell alpha union and never resize frames or actions independently.
4. Record `canonicalIdleHeightPx`, allowed range, pass/fail, canvas, root, baseline, and shared transform in every action manifest. Compare tiers in a table; fail the size gate if any selectable tier is outside tolerance.
5. Inspect every action at gameplay scale for apparent size popping. Crouches, jumps, lunges, and recoil may change pose height, but head/body proportions and camera scale must remain constant when the action returns to idle.
6. Render the primary preview at 1 CSS pixel per asset pixel, or at an explicitly labelled integer zoom. Test the computed CSS size and baseline; do not infer them from the PNG canvas dimensions.

If the size gate fails but the source contains enough pixels and margins, fix registration locally and regenerate runtime assets without another paid provider call. Regenerate from the provider only when the source itself changes camera scale, clips the body, or lacks enough resolution.

## Sequence manifest

Minimum fields:

```json
{
  "source": {
    "provider": "...",
    "taskId": "...",
    "model": "...",
    "promptSha256": "...",
    "videoSha256": "...",
    "selectedTake": 0
  },
  "logicFps": 30,
  "artFps": 10,
  "canvas": [2048, 1536],
  "root": [1024, 1470],
  "baseline": 1470,
  "holdPattern": [3, 3, 3],
  "sharedTransform": {"scale": 1.0, "offset": [0, 0]},
  "frames": [
    {"file": "runtime/frame-00.png", "sourceTime": 0.0, "alphaBbox": [0, 0, 1, 1]}
  ],
  "qa": {"status": "pending"}
}
```

Keep hit/cancel windows in logic-frame indices, not art-frame indices.

## Runtime integration

- Load each accepted sequence from its own manifest and keep provider/model choices selectable until gameplay QA is complete. Preserve the previous authored sequence as a fallback.
- Drive the beauty frame index from the recorded source timestamps or `sourceFps`. Do not silently route a 24 FPS provider sequence through an existing 10, 30, or 60 FPS action scheduler.
- For locomotion sources authored as `idle → move → idle`, detect and preserve three separate runtime phases instead of looping the whole extraction. Choose `start` from the first intentional weight transfer, choose loop endpoints from matching support-foot/body poses and low seam error, and choose `end` through the last recovery into canonical idle. Record phase frame/timestamp lists plus phase FPS. On input, play start once, loop only the gait cycle, then play a short end once on release; never include leading/trailing idle holds in the loop.
- Store the selected sequence's frame count, source FPS, active-frame window, shared transform, root, and baseline in runtime state so browser/game QA can inspect them.
- Render video-derived beauty frames directly. Do not add optical flow, mesh warp, cross-fade, or frame dropping unless the user separately requests retiming or interpolation.
- A runtime pixel outline may be generated non-destructively from the final hard alpha mask. Write it only into the display buffer outside the foreground mask; do not alter the source PNG, collision mask, root, baseline, normal field, or cast-shadow source. Declare thickness in final CSS pixels and convert it to an integer native radius with `nativeRadius = cssWidth / displayScale`. When comparing 128 native enlarged 2× against 256 native 1×, use screen widths divisible by 2 (for example 2 or 4 CSS px) so both tiers have exact integer radii. Provide an immediate on/off control, disable the outline during normal-map inspection, and report native radius plus generated pixel count in runtime QA.
- Apply facing exactly once after canonical registration. Mirror the complete registered frame and any hit anchors together; never mirror the source frame and runtime container independently.
- Finish the action after `frame_count / source_fps`, clear attack state, and return to the accepted idle pose. Repeated attacks, movement, cancellation, and mode switching must not leave a stale source frame or VFX.
- Account for all selectable sequences that are preloaded together. Twenty `2048x1536` RGBA frames decode to about 240 MiB per sequence even when the PNG files total only a few megabytes. Report this honestly and consider lazy decode only as a later optimization after the comparison build is accepted.

For a playable comparison, verify each mode independently: start pose, first source frame, active window, final source frame, return to idle, left/right facing, movement before and after attack, and zero console errors. Record the actual frame count and measured duration from runtime state instead of relying on UI labels.

Also verify direction semantics against the declared contract. For the default right-facing side view, test forward walk/right root, backward walk/left root without mirroring, forward dodge/right root, backward dodge/left root, block force arriving from the right, and hit recoil to the left. Mark direction failure separately from identity, size, idle-envelope, and motion-readability QA.

## Visual gates

Inspect the whole sequence at gameplay size and frame-by-frame:

- one stable identity, costume, face, hair, and weapon;
- no extra/missing limbs, weapon heads, halos, or duplicate subjects;
- camera, character scale, ground line, and facing remain fixed;
- action reads in the intended plane and has anticipation, force peak, recoil, and recovery;
- support foot and root motion are believable;
- silhouette stays inside safe margins;
- transparent edges remain clean in both facings;
- collision/hit frames match the visual contact;
- playback returns to idle and clears VFX/state.

For a low-pixel batch, additionally inspect after final nearest-neighbour reduction: face/weapon readability, palette stability, no subpixel shimmer, no cross-cell contamination, and no cell whose source character height fell below budget.

## Resource accounting

Report:

- raw video bytes;
- extracted source-frame bytes;
- runtime compressed bytes;
- decoded RGBA memory (`width × height × 4 × frame_count`);
- provider call count and generated seconds;
- packed takes/cells and accepted outputs;
- cost per accepted take when billing data is available.

Remove temporary full-resolution frames from the release package after QA, but keep reproducible source and manifests outside runtime distribution.
