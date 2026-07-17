# SpriteFlux Roadmap

Status: Active

## Product direction

SpriteFlux will become a reusable, local-first production tool for turning references into inspected 3D character, static environment, modular level, and pixel-styled model candidates, and for turning video motion sources into registered, game-ready 2D or 3D animation assets. Development will be driven by real project assets instead of isolated demos.

The tool owns reusable planning, provider, extraction, matte, registration, preview, validation, and export capabilities. A consuming game owns its private characters, prompts, paid outputs, tuning, runtime manifests, and engine adapters.

## Current baseline

Available and tested:

- action batch and source-pixel planning;
- schematic SVG action storyboards and motion-envelope JSON;
- cost estimation;
- offline HTML motion-plan dashboard;
- PNG sequence manifest validation;
- publication-safety audit and written provider/Godot guidance.
- bounded provider preflight/submission/resume with idempotent private receipts;
- PTS-aware video extraction, one-model-per-sequence chroma keying, compositing-based edge-colour recovery, shared registration, pixel-channel construction, candidate manifests, and synthetic self-tests;
- `clean-chroma-v2` prompt/preflight contract separating neutral subject rendering, exact extraction field, body-bound motion texture, and detached-effect exclusions;
- fail-closed chroma-field diagnostics for border spatial variation and cross-frame key drift, plus dark/light/checker visual QA.
- documentation-locked Tripo P-series character-modeling route covering image/multiview generation, low-poly face budgets, standard textures, free rig checks, optional rig/animation costs, temporary-output handling, and DCC acceptance; no Tripo API execution has been validated yet.
- documentation-locked Tripo static-prop/modular-level route covering asset classification, pixel-3D authoring intent, direct Godot DCC Bridge intake when version-compatible, immutable-export preservation, collision separation, and engine-render acceptance; no Tripo generation or Bridge integration has been validated yet.
- portable `SpriteFluxUnrealGodotBridge` Editor plugin and installer for new Unreal projects, using public UE glTF APIs, hashed GLB inventory reports, animation-only/preview-mesh profiles, and the validated `RenderOffScreen + SIMPLE` material route without downloading the community research plugin.

Not implemented yet:

- direct turnaround/keyframe image intake;
- a persistent interactive Preview Lab;
- animated sequence/contact-sheet comparison;
- one-command transparent PNG, manifest, QA, and Godot handoff export.
- end-to-end video-reference-to-existing-armature pose fitting and per-frame Action baking; the reusable contract is documented, but detector, solver, correction UI, and synthetic acceptance fixture are not yet delivered as one tested backend.
- a Tripo provider adapter, private receipt fixture, downloaded model candidate, Blender acceptance report, deformation test, and pixel-render comparison; the current modeling route is documentation research only.
- a validated Tripo-to-Godot Bridge fixture for static props, versioned source/import manifests, modular-snap and collision fixtures, and an accepted target-pixel render comparison.

## Iteration order

### M1 — Reference and planning Preview Lab

Build a local Preview Lab that accepts one to three turnaround/reference images plus optional action keyframes without uploading them. It must display the real references alongside the schematic storyboard, canvas, root, baseline, safe margins, motion envelope, batch plan, and cost preflight.

Acceptance:

- local-only input with no tracked private copies;
- explicit missing/invalid-input diagnostics;
- one core action contract and stable project-relative IDs;
- standalone preview output that opens without a paid provider call;
- no claim that planning diagrams are final character frames.

### M2 — Source-video inspection and extraction

Import an existing MP4 as a motion source, inspect presentation timestamps, mark action/take windows, extract full-resolution source frames, and generate raw contact sheets.

Acceptance:

- original video remains immutable;
- extraction uses actual timestamps instead of assumed nominal frame indexes;
- action/take boundaries are saved and reproducible;
- animated playback and contact sheets expose every source frame used.

### M3 — Matte, registration, and asset preview

Add constant-background chroma keying, edge-colour recovery, temporal QA, one shared transform per take, canonical root/baseline registration, visible-height measurement, and actual-size animation preview.

Acceptance:

- raw and processed views can be compared on light/dark backgrounds;
- no per-frame recentering or destructive overwrite;
- root, baseline, alpha bounds, scale, frame timing, memory, and defects are visible;
- transparent PNG sequences, manifest, contact sheet, and QA report export together.

### M4 — Provider adapters and bounded paid execution

Implement provider adapters behind build-request, redacted dry-run, submit, poll, download, cancel, and report stages. Start with the provider selected by the consuming project.

Acceptance:

- no submission before explicit bounded authorization;
- duplicate billable submission protection;
- secrets and signed URLs never enter logs, previews, or Git;
- task state, actual usage, price basis, failures, and retry cost are preserved;
- result video downloads before its temporary URL expires.

### M5 — Runtime handoff and project feedback

Provide deterministic export contracts and reusable runtime-preview guidance. Validate complete routes in a generic Godot fixture while keeping downstream game runtime code independent from SpriteFlux internals.

Acceptance:

- game-ready assets are reproducible from recorded inputs;
- Godot imports Lossless/Nearest/no-mipmap assets and respects manifest root/baseline;
- real-window playback validates idle return, locomotion phases, displacement, scale, and memory;
- reusable fixes return to SpriteFlux with synthetic public-safe fixtures only.

### M6 — Video reference to existing 3D armature

Fit one accepted, PTS-preserving action window to a user-supplied rig without changing the source video, rest pose, camera, character scale, or existing Actions. Keep pose detection outside Blender in an isolated environment, retain confidence and manual corrections as data, solve screen-space targets through temporary IK controls, and bake the accepted result to deform bones.

Acceptance:

- source frame indices and PTS map one-to-one to baked authored poses;
- side/frontal plane detection is confidence-gated and supports deterministic manual landmark correction;
- root, support foot, ground baseline, facing, camera and character scale remain explicit and stable;
- detector noise is filtered before solving, while the final Action remains inspectable at every source frame;
- rest-pose alignment, bone mapping, IK pole directions and unmapped bones fail closed;
- existing Actions remain immutable and the new Action has a stable ID;
- an orthographic overlay/difference preview reports joint error, foot slip, root drift, loop seam and silhouette mismatch;
- the target engine compares video-derived 2D motion, 3D render and overlay at one clock and world scale;
- optional dependencies and model weights pass version, license and commercial-use review;
- public tests use synthetic references and rigs only.

### M7 — Character reference to accepted 3D model candidate

Add a provider-neutral reference-to-model contract and begin with Tripo P-series image/multiview generation. Keep single-view repair, model generation, topology/texture processing, riggability, rigging, preset animation, DCC cleanup, and final acceptance as separately costed and inspectable stages.

Acceptance:

- a redacted dry run identifies the immutable references, selected model/version, face budget, texture tier, optional stages, expected credits, worst-case retry cap, and temporary-output lifetime before submission;
- multi-view input is preferred when front/back/asymmetry matters, while an AI-generated multi-view is preserved and reviewed as a separate paid inference rather than treated as reference truth;
- the low-poly generator is used before paid retopology, and standard texture is the default for pixel-style downstream rendering;
- rig-check runs before paid auto-rig, while provider preset animations remain optional when an existing motion library or video-retarget route supplies actions;
- provider files and responses remain private, are downloaded immediately, and are never committed to the public Skill;
- Blender/DCC validation rejects bad topology, UV/material structure, scale/axis/root, rest pose, bone semantics, weights, or deformation instead of hiding defects in the pixel render;
- an engine import and fixed-camera pixel-style comparison prove silhouette, material separation, motion readability, and performance before the derivative is accepted;
- documentation-only support is not presented as an implemented provider adapter or a production-validated character pipeline.

### M8 — Static environment and modular level asset intake

Extend the provider-neutral 3D candidate contract to props, architecture modules, terrain/decor pieces, and occluders. Prefer Tripo's Godot DCC Bridge only when the target editor version is officially supported; retain manual versioned GLB as an equivalent transport fallback.

Acceptance:

- the asset is declared `environment_static` or `environment_articulated` before generation, and static packages contain no accidental armature, skin weights, or animation tracks;
- the immutable provider export, source rights/terms snapshot, stable asset ID, hashes, units, axes, pivot, bounds, materials, textures, and generation settings are recorded before promotion;
- dimensions, target-scale silhouette, topology/normals, UV/texel density, material/alpha/normal orientation, ground contact, and modular seams pass independent inspection;
- collision, navigation, placement rules, occluder/shadow flags, and gameplay metadata are stored separately from the visual mesh;
- the consuming engine wraps imported source scenes non-destructively, so Bridge refresh or GLB reimport cannot erase project-side collision, scripts, or overrides;
- LOD, triangle, material, draw-call, texture-memory, and shadow budgets are measured in the target scene;
- a true target-resolution render proves the low-resolution/pixel-style silhouette, palette/material separation, lighting, depth, and placement quality;
- Bridge installation or engine upgrade requires authorization, and documentation-only support is not described as a tested integration.

## Development rule

Implement the smallest complete milestone needed by the current real character. Do not build speculative provider, UI, or game-specific branches. Each milestone requires automated tests, representative synthetic fixtures, a visual inspection artifact, failure diagnostics, documentation, and publication-safety audit before release.
