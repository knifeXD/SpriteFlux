# Video reference to a Blender armature Action

Status: reusable workflow specification; automated backend pending milestone acceptance.

## Contents

1. Scope and ownership
2. Input contract
3. Dependency selection
4. Processing stages
5. Data contract
6. Blender fitting rules
7. Baking and loop rules
8. QA and engine preview
9. Failure handling
10. Provenance and licensing

## Scope and ownership

Use this route when an accepted video action should drive an existing rigged 3D character for an orthographic game preview or a reusable animation Action. It also covers a split route in which a capture engine first produces a standard-humanoid animation and an external DCC/art library later retargets that animation to the final character.

SpriteFlux owns:

- immutable video identity, extraction report, source indices and PTS;
- the selected action window and loop/terminal semantics;
- timestamped screen-space landmarks, confidence, occlusion flags and corrections;
- root, ground baseline, facing, camera and visible-height contracts;
- overlay, difference and timing QA.

The Blender stage owns:

- armature inspection and rest-pose alignment;
- temporary IK controls and constraints;
- pose solving, deformation inspection and correction;
- baking the accepted result to a new Action on deform bones;
- `.blend` source and GLB/FBX export.

An external animation library or DCC integration owns engine-specific import/export, target-skeleton retargeting, unit/axis normalization, foot-plant correction, deformation acceptance, and final exchange-package validation. SpriteFlux may validate its handoff contract, but it must not absorb private engine project paths, target-character assets, or game-specific import settings.

The game engine owns presentation only. Gameplay timing, damage, cancellation, cooldowns and attributes remain outside the animation asset.

## Input contract

Require:

- an immutable video plus a PTS-aware extraction report;
- one contiguous accepted action window;
- explicit action type: stationary loop, locomotion, displaced action or terminal action;
- declared facing, ground baseline, root convention and orthographic/frontal camera plane;
- a rigged target model with stable bone names and a preserved source file;
- target engine render size and world-height contract.

Record the target armature's Blender version, mesh count, deform-bone count, actions, material dependencies, rest pose, weighted groups and missing/unweighted vertices before fitting.

Reject the route when the action window contains a cut, zoom, camera orbit, subject-scale change, identity swap, severe occlusion, multiple interacting subjects, or an unresolvable ground line.

## Standard-source-skeleton handoff

Prefer this split when a capture engine or animation library already produces reliable motion on a known humanoid skeleton:

```text
video + PTS
  → landmarks / capture solve / motion QA
  → standard humanoid animation
  → engine export
  → DCC rest-pose alignment and offline retarget
  → target deform-bone bake
  → target-character exchange package
  → runtime import
```

The capture engine is an animation-source factory, not the owner of the final character skeleton. Export one action per file or per explicitly declared clip. The target character is adapted offline so the source action can be reused across characters and the baked result can be inspected independently of the capture engine.

Require a handoff manifest containing:

- immutable source video hash, extraction-report hash, selected source indices and PTS;
- action ID, stationary/locomotion/displaced/terminal semantics, loop range and contact markers;
- source skeleton ID/version, reference-pose ID/hash and semantic bone map;
- physical unit, up/forward axes, handedness and object-transform policy;
- top-level root, pelvis/retarget root, root-motion mode and ground plane;
- action duration, sample times, curve list and whether resampling occurred;
- source foot-plant windows, root/foot motion metrics and known occlusion/correction flags;
- exchange-file hash, exporter version and license/provenance.

Fail closed when mesh scale and bone local translations occupy different unit domains. A character mesh with the expected visible height is not sufficient evidence: report reference bone lengths and animated root/pelvis/foot ranges as well. Do not rely on an importer-only scale multiplier to repair a DCC reference skeleton.

### Recommended ownership split

- Use the motion/capture engine to create and visually verify a standard-source animation.
- Use Blender or another approved DCC to map source/target reference poses, retarget, correct contacts and bake the target Action.
- Use the game engine to consume the accepted target Action. Runtime humanoid retargeting is an optional compatibility path, not the default production master.
- Keep engine-internal direct-to-target retargeting as a controlled comparison. It passes only if the same action, scale, root, foot and deformation gates outperform or equal the offline route.

## Dependency selection

Prefer a local, isolated landmark environment. Do not install computer-vision packages into Blender's bundled Python.

Recommended order:

1. Use a side/frontal-plane 2D detector for screen-space joint proposals.
2. Use MediaPipe Pose only as another proposal or fallback.
3. Allow deterministic manual correction for every required landmark.
4. Skip automatic detection and author landmarks directly when confidence is insufficient.

Known references:

- Sports2D: BSD-3-Clause; suitable for motions parallel to a sagittal or frontal plane, with tracking, interpolation and configurable temporal filters. https://github.com/davidpagnon/Sports2D
- MediaPipe: Apache-2.0; supplies timestamped pose-landmark detection but does not make stylized or pixel subjects reliable by itself. https://github.com/google-ai-edge/mediapipe
- BlendArMocap: GPL and historically tied to older Blender/Python dependencies. Study its separation of detection, transfer configuration and rig mapping; do not vendor it by default. https://github.com/cgtinker/BlendArMocap
- FreeMoCap Blender add-on: AGPL-3.0. Treat it as an external interoperability reference, not code to copy into a permissive or commercial plugin. https://github.com/freemocap/freemocap_blender_addon
- Blender Animation Retargeting: useful public workflow evidence for rest-pose alignment, bone mapping, hand/foot IK correction and Visual Keying bake. Verify a repository license before copying any implementation. https://github.com/Mwni/blender-animation-retargeting

Exclude SMPL-family models or weights from a commercial route unless the consuming project proves an appropriate commercial license. A repository's source-code license does not grant rights to separately licensed model files or weights.

## Processing stages

### 1. Lock the source window

Extract all source frames with PTS. Slice the action by source indices without renumbering or copying its identity. Preserve source time, hashes and the loop neighbor relationship.

### 2. Establish the screen contract

Declare one orthographic projection, ground baseline, facing, root point and target visible height. The camera, target object scale and root transform are constant across the action.

### 3. Produce landmark proposals

For each source frame, record head, neck, shoulders, elbows, wrists, pelvis, knees, ankles, heels and toes when visible. Store detector confidence and `visible`, `occluded` or `manual` state separately from coordinates.

Never convert a missing or low-confidence joint into a zero coordinate. Interpolate only a bounded gap with valid support on both sides, and keep the interpolation flag.

### 4. Correct and filter trajectories

Inspect an overlay on the real source frame. Correct left/right swaps, impossible limb lengths and occluded joint guesses. Filter detector trajectories before they reach Blender; retain both raw and corrected data.

Use a low-pass method appropriate to the action and sample count. Preserve intentional impact, overshoot and sharp contacts. Do not smooth foot plants, contact poses or loop endpoints into drift.

### 5. Inspect and map the armature

Map only declared target bones. Validate hierarchy, bone roll, rest-pose orientation, limb side, deform status and vertex groups. Align rest poses without modifying the preserved source model.

Create temporary controls for pelvis, chest, head, hands, feet, elbow poles and knee poles. Keep controls and constraints in the working `.blend`; bake their evaluated result to deform bones for export.

### 6. Solve screen-space poses

Fit each frame by minimizing a weighted objective:

`joint projection error + root/foot error + temporal acceleration + joint-limit penalty + optional silhouette error`

Weight support feet, pelvis and head more strongly than uncertain or occluded extremities. Solve depth conservatively because one view cannot determine it. For strict side views, keep limbs near a declared motion plane unless silhouette evidence requires a small separation.

Start with a small set of strong poses, solve intermediate frames, then inspect every source frame. The final bake may contain one key per source frame even though the underlying motion was built pose-to-pose.

### 7. Add secondary motion deliberately

Do not infer hair, cloth, belts or loose equipment from body landmarks. Add secondary bones, shape keys or authored motion only when the target mesh supports them. Keep this layer separable from the primary body fit and preserve the exact action timing.

## Data contract

Store a project-private JSON document shaped like:

```json
{
  "schemaVersion": 1,
  "actionId": "stable-action-id",
  "source": {
    "extractionReport": "project-private/path.json",
    "sourceIndices": [10, 11],
    "pts": [5120, 5632],
    "sourceTimes": [0.416667, 0.458333]
  },
  "screenContract": {
    "projection": "orthographic_side",
    "facing": "right",
    "baselinePx": 320,
    "rootPx": [192, 320],
    "visibleHeightPx": 256
  },
  "landmarks": [
    {
      "sourceIndex": 10,
      "joints": {
        "pelvis": {"xy": [192.0, 210.0], "confidence": 1.0, "state": "manual"}
      }
    }
  ],
  "targetRig": {
    "sourceHash": "sha256",
    "armature": "Armature",
    "boneMap": {"pelvis": "Hips"}
  },
  "bake": {
    "blenderFps": 24.0,
    "actionName": "stable-action-id",
    "keyEverySourceFrame": true,
    "preserveExistingActions": true
  }
}
```

Never place private video paths, model hashes, character identifiers or project output in this public Skill repository. The schema example is synthetic.

## Blender fitting rules

- Work from a versioned copy of the target model.
- Preserve existing Actions and NLA strips.
- Use quaternion rotation or a declared Euler order consistently.
- Lock character scale and camera throughout the action.
- Do not move the armature object per frame to hide bone-fitting errors.
- Keep stationary-loop root motion fixed unless the action contract declares measured displacement.
- Keep the support foot planted during its declared contact interval.
- Resolve pole-vector flips before baking.
- Evaluate mesh deformation, not only bone overlays.
- Treat hands and fingers as a separate pass when the source cannot resolve them.
- Bake with visual transforms to deform bones, then remove runtime dependency on temporary controls.

## Baking and loop rules

Map source PTS to Blender time without assuming a new nominal cadence. When the target timeline uses the same FPS, preserve one authored pose per source frame. For variable PTS, use fractional frame time or an explicit retiming map before the final engine export.

For a cyclic action, evaluate the last selected frame against the first selected frame as temporal neighbors. An extra duplicate first pose may be used outside the exported display range to establish a continuous curve tangent. Do not export that duplicate as another visible frame.

Keep an unfiltered fit Action, a corrected working Action and an accepted baked Action as separate versioned data blocks until QA completes.

## QA and engine preview

Produce:

- source frame with corrected landmarks;
- target 3D render from the locked camera;
- 50% overlay;
- landmark-error vectors;
- silhouette difference where source alpha is trustworthy;
- loop seam sheet;
- actual-size engine preview.

Report at minimum:

- weighted joint RMS and maximum error in target render pixels;
- support-foot error and sliding distance;
- root and baseline drift;
- head-height and visible-height variation;
- left/right swap count and pole-flip count;
- corrected, interpolated and rejected landmark counts;
- first/last pose and velocity seam error;
- unmapped or unkeyed required bones;
- source-frame-to-baked-key count and PTS parity;
- mesh clipping, self-intersection and visibly collapsed deformation.
- mesh height together with representative source/target reference bone lengths, so 100× or 0.01× split-domain imports cannot pass on silhouette alone;
- root/pelvis/foot animation translation ranges before export, after DCC retarget, and after runtime import;
- foot-plant sliding per declared contact window and foot-ground penetration/clearance;
- source Action count, target baked Action count, stable action IDs, durations and sample-time parity.

Treat metric thresholds as project contracts, not universal constants. Fail closed on foot swaps, inverted limbs, camera/scale drift, missing required poses, overwritten Actions or a timing mismatch.

In the engine, compare the accepted 2D sequence, the 3D render and an overlay/difference view on one clock, facing, camera and world height. Support pause, single-frame stepping, zoom, pan and mode labels. Keep the 3D node as a presentation adapter; animation callbacks must not decide gameplay events.

## Failure handling

If a detector fails on stylized or pixel frames, do not switch to a more aggressive model silently. Preserve the failed report, use manual landmarks or a different approved detector, and keep the same downstream schema.

If one-view depth is ambiguous, prefer a stable planar solution that matches the accepted screen silhouette. Do not invent a dramatic 3D twist that changes the authored side-view action.

If clothing or hair cannot be reproduced by the existing rig, report the missing deformation capability. Do not hide it with camera changes, character scaling, mesh edits per frame or post-render smearing.

## Provenance and licensing

For every optional dependency, record version, source URL, code license, model/weight license, Blender compatibility and whether it runs in-process or as an isolated helper. Review commercial-use rights separately for code, weights, body models and generated outputs.

Study public behavior and interfaces when a license is absent or incompatible; do not copy implementation. Keep GPL/AGPL tools external unless the distribution and source obligations are deliberately accepted for the complete combined work.
