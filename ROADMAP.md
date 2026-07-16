# SpriteFlux Roadmap

Status: Active

## Product direction

SpriteFlux will become a reusable, local-first production tool for turning character references and video motion sources into inspected, registered, game-ready 2D animation sequences. Development will be driven by real project characters instead of isolated demos.

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

Not implemented yet:

- direct turnaround/keyframe image intake;
- a persistent interactive Preview Lab;
- animated sequence/contact-sheet comparison;
- one-command transparent PNG, manifest, QA, and Godot handoff export.

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

## Development rule

Implement the smallest complete milestone needed by the current real character. Do not build speculative provider, UI, or game-specific branches. Each milestone requires automated tests, representative synthetic fixtures, a visual inspection artifact, failure diagnostics, documentation, and publication-safety audit before release.
