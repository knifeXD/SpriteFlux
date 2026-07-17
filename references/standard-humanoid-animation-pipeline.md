# Standard humanoid animation production and delivery

Status: reusable workflow contract.

For a new workstation or Unreal project, pair this contract with [portable-unreal-godot-bridge.md](portable-unreal-godot-bridge.md). SpriteFlux includes its own installable Editor plugin, so the reproducible bridge does not depend on downloading the community research source.

The community exporter is a research source, not a distribution dependency. Its evaluated revision declared MIT in README but contained no standalone license text; SpriteFlux therefore ships an independently authored bridge that uses public Unreal Python/glTF APIs and records the research provenance without copying upstream files.

## Scope and ownership

Use this route when Unreal Engine or another animation library creates motion on a stable standard humanoid skeleton, and Blender must retarget, clean, bake, and deliver the motion to a project-owned character skeleton.

SpriteFlux owns the reusable orchestration contract, interchange manifests, timing/root/contact QA, and public-safe validators. An external art library owns its private engine assets, DCC scenes, target characters, licensed animation sources, editor automation, and generated deliverables. A game project consumes only an accepted versioned package.

## Production chain

```text
approved motion source
  → standard-source AnimSequence
  → full engine playback QA
  → one-action standard-skeleton FBX
  → Blender import normalization
  → explicit source/target rest-pose and semantic bone mapping
  → offline retarget and contact correction
  → evaluated target deform-bone bake
  → clean-scene FBX/GLB re-import QA
  → versioned target-character package
  → runtime import and rendered QA
```

The engine is a source-animation factory. Do not make it the only place where the target character can play the animation. Prefer an offline target bake so one source animation can serve multiple target rigs and the final target Action can be audited independently.

## Canonical character master gate

Treat the accepted Blender file as the single character-model truth after any provider, scan or external modeling handoff. Do not let Unreal, Godot or a later FBX import silently become a second editable character source.

The canonical master must contain the accepted mesh topology, UVs, material-slot order, texture bindings, skin weights, rest skeleton, reference pose, unique non-deforming root, ground, physical height and character-forward contract. Give it a stable model ID and version, preserve the immutable provider input separately, and record hashes for the Blender master plus every exported derivative.

Export engine-specific packages from that same master:

- Unreal may receive FBX because its skeletal-animation interchange is FBX-oriented.
- Godot should normally receive GLB/glTF when the required skin, materials and animations survive its importer; FBX is a controlled compatibility path.
- The files need not be byte-identical, but their mesh topology, vertex order where promised, UVs, material slots, skin weights, rest-bone hierarchy and reference-pose hash must resolve to the same canonical model version.

Never fix an engine import by editing only the engine copy. Correct the Blender master or the deterministic exporter profile, increment the model version, then regenerate every promised engine derivative. A character manifest must name exactly one canonical master and list Unreal/Godot derivatives with source hash, exporter profile, tool version, units, axes and acceptance state. Reject a delivery when two engine packages claim the same character version but differ in geometry, rest skeleton, weights or material-slot identity without a declared derivative contract.

The normal ownership order is therefore:

```text
generated/authored model candidate
  → Blender topology/UV/material/skin/rest-skeleton standardization
  → one accepted canonical character + skeleton version
      ├─ deterministic Unreal skeletal-mesh derivative
      │    → Unreal acts as animation broker: source animation, retarget, playback QA
      │    → animation-only target-skeleton handoff
      └─ deterministic Godot GLB derivative from the same Blender master
           → attach/bake accepted target-skeleton actions
           → final runtime import and rendered QA
```

Unreal is not the canonical model exporter for Godot. Its imported Skeletal Mesh is an audited derivative used for animation production. Unless a diagnostic explicitly requires otherwise, hand animation back as a single target-skeleton Action/AnimSequence export without making the Unreal mesh copy the next model source. Build the Godot mesh, skin, rest skeleton, materials and textures from the accepted Blender master, then merge/bake the accepted animation onto that same skeleton version in the deterministic DCC build. This prevents an Unreal FBX round trip from silently changing bone representation, scale, axes, rest transforms or materials before Godot intake.

## Engine source-animation gate

Require a real animation asset with readable source skeleton, reference pose, preview mesh, duration, sample times, root-motion settings, curves and contact semantics. Play the complete action in the engine before export; scripting success or an asset filename is not visual evidence.

Use official IK/retarget tooling when an existing animation must first move between standard engine skeletons. Audit source/target retarget roots, root-motion bones, semantic chains, rest poses and operation order. Auto mapping is a starting point, not acceptance.

Create one persistent, versioned IK Rig/IK Retargeter set per accepted target-skeleton version, not a disposable set per action. Reuse it for all compatible source actions; regenerate it only when the canonical target skeleton, reference pose, semantic chains or engine version changes. Keep source IK Rig, target IK Rig and retargeter as auditable production assets, while each action produces only its target AnimSequence and action QA evidence. Record the retargeter version in every output clip manifest.

Auto-generated chains and Auto Align are initialization aids. Require complete engine playback of each generated clip before export or runtime handoff. Validate body line, shoulders, elbows, wrists, spine, hips, knees, ankles, ground, facing and action logic. Finger motion can be a declared model/source limitation, but must never be reported as passed when the source curves or target weights do not form the intended hand shape.

Export one action per FBX by default. Exclude the preview mesh unless a separate mesh-bearing diagnostic file is explicitly required. Record exporter/engine version and FBX compatibility version.

### UE 5.8 official Auto Generate automation profile

For repeatable editor automation, treat the **Auto Generate Retargeter** window as a public-controller workflow, not as a desktop action to replay. A version-locked Editor-only tool may reproduce the UE 5.8 sequence through exported `UIKRigController` and `UIKRetargeterController` APIs:

1. assign the source and target Skeletal Meshes to persistent IK Rig assets;
2. run auto retarget characterization, require a recognized template, apply the returned retarget definition, and generate FBIK data;
3. assign both IK Rigs to one persistent target-skeleton-version Retargeter;
4. rebuild the default operation stack and force exact semantic-chain mapping;
5. reset and Auto Align the target pose, then restore template-excluded bones;
6. keep the automatically generated IK pass disabled by default, matching the editor workflow's conservative result;
7. configure root-motion generation only when root/pelvis topology requires it, and add declared pin-bone pairs;
8. batch-retarget exactly the requested source AnimSequence and write only the target clip per action.

Do not directly link or copy an engine-internal convenience wrapper when its symbols are not exported. Use the public controllers, keep the tool version-locked to the tested engine build, expose a structured success/error result to Blueprint/Python or an approved automation bridge, and add a non-mutating failure-path test before invoking the asset-writing success path. Desktop coordinates, Slate clicking and mouse replay are not pipeline APIs.

The generated Source IK Rig, Target IK Rig and IK Retargeter are durable production assets for one target skeleton/reference-pose version. Reuse them for subsequent compatible actions. A skeleton hierarchy, rest pose, root scale, semantic-chain definition or engine-version change requires a new retargeter version; an action filename change does not. Never delete or overwrite unrelated existing assets during regeneration—write to an owned versioned path or fail on collision.

Before presenting a generated clip, require:

- recognized source and target templates plus mapped spine, clavicle/arm, leg and foot chains;
- declared retarget root and root-motion bone on both rigs;
- operation-stack type/order and enabled-state audit;
- output Skeleton identity, exact clip count/name, source-equivalent duration/sample count and root scale `[1,1,1]`;
- finite sampled root/bone transforms, plausible ground/height/facing, and no bone explosion;
- full engine playback at start, action apex and recovery, with feet and major joints inspected.

A passing structure report advances only to visual review. Foot plants, hand shape and skin-weight defects remain explicit limitations until a human or approved rendered-motion gate accepts them.

### Headless Unreal material dependency and glTF export gate

For Unreal 5.8 automation, use `MaterialEditingLibrary.get_material_used_textures` as the primary public texture-dependency API. Treat the deprecated `get_used_textures` only as a guarded compatibility fallback. Keep dependency discovery separate from material rendering: a valid material can return an empty dependency list in a `NullRHI` commandlet because no render resource exists, even though it displays correctly in the editor.

If the modern query returns no textures, a generic adapter may inspect direct public material-property input nodes and material-instance texture parameters. It must remain read-only, must not save the material, and must not contain asset-specific names. This fallback can recover source texture dependencies and sidecar exports, but it cannot create a render resource or prove that a glTF material was embedded.

When a glTF profile needs baked material inputs, run `UnrealEditor-Cmd` unattended with offscreen rendering and a real RHI, for example `-RenderOffScreen`; do not use `-NullRHI`. This is still non-interactive automation, but it provides the GPU resource context required by Unreal's material baker. Prefer `GLTFMaterialBakeMode.SIMPLE`; select `USE_MESH_DATA` only when the material depends on mesh-specific data. `DISABLED` is an expression-matching control and must fail when a required packed PBR input needs baking.

Parse the produced glTF/GLB and require the declared material count, embedded images/textures and Base Color/Normal/Metallic-Roughness bindings. Separate PNG files, a successful exporter return, or correct editor display are not substitutes. An animation-only package is expected to omit materials; apply this material gate only to mesh-bearing deliveries. Material acceptance never waives skeleton, animation-curve or rendered-motion equivalence.

### Target-skeleton version migration and runtime comparison

An animation baked for a new target reference skeleton must not be inserted into an older runtime GLB merely because bone names and counts look similar. A root scale, rest transform, hierarchy, unit-domain or reference-pose change is a skeleton-version change. Build a new exchange package containing the canonical mesh derivative, that exact skeleton/rest, materials/textures and every included action baked to it.

During migration, keep the last accepted runtime package as a labeled comparison candidate. A debug scene may display the legacy package and the new package side by side under the same camera, ground, clock and world-height contract, but it must not mix their Skeletons or AnimationLibraries. Compare node scale, physical height, ground, forward/up axes, bone hierarchy/rest hash, animation duration/tracks, root motion, foot contact and deformation before promotion. Runtime node scale, negative scale, per-action offsets or camera framing cannot repair an exchange-package mismatch.

## Blender import normalization gate

Never assume the engine FBX maps one-to-one to Blender's object/bone model.

A common UE FBX representation imports the exported top-level skeleton node as the Blender Armature object rather than an explicit pose bone. Centimeter conversion can also appear as Armature object scale `0.01` while child bone lengths are expressed in centimeter-like numeric values. This is a valid interchange representation, but it is not a valid target-retargeting workspace until normalized.

Before mapping any target rig:

1. Record raw imported objects, armature count, mesh count, Actions, scene FPS, object transforms, top-level bones, reference lengths and root/pelvis/foot animation ranges.
2. Classify the source root representation as `explicit_bone`, `armature_object`, or `unsupported`.
3. Convert the imported source into one declared DCC unit domain. Apply object transforms without changing evaluated world-space poses or timing.
4. If the source root is represented by the Armature object, create or map an explicit non-deforming root bone in the normalized working rig and transfer the object animation to that root when root motion exists. Parent former top-level pelvis/IK roots under it while preserving evaluated transforms.
5. Keep raw imported, normalized-source, target-work and accepted-bake Actions/files separate.
6. Re-audit mesh/bone scale, reference lengths, root/pelvis/feet and Action timing after normalization. A `100`, `0.01`, or missing-root mismatch blocks retargeting.

Do not merely apply scale, rename an object to `root`, or add a zero root bone. Normalization must preserve each evaluated source pose and declared root motion.

### Optional Epic BlenderTools adapters

EpicGamesExt/BlenderTools provides two useful reference adapters under the MIT license:

- Send to Unreal validates scene conventions, exports selected mesh/armature/animation data and can automate Unreal import.
- UE to Rigify stores semantic source/control links, drives rigs through constraints and bakes evaluated visual pose/object transforms frame by frame.

Treat these as adapters, not as the interchange contract itself. Pin the repository revision and add-on versions, verify declared Blender/Unreal compatibility against the production versions, and run the same clean re-import and visual QA. A scene-scale check of `1` does not prove that imported reference bone lengths and animation translations occupy the same physical unit domain.

For an Unreal FBX that imports as Armature object scale `0.01` with centimetre-like numeric bone lengths, do not set Blender FBX `global_scale=100`: that can make the object scale display `1` while enlarging the evaluated character one hundred times. Normalize by preserving raw samples, moving the static FBX factor into armature/rest and pose-location data, separating object root motion, and comparing every sampled world transform before and after. Temporarily detach the Action while applying the static Armature scale when object-scale animation curves would otherwise override it. Require object scale `1`, physically plausible representative bone lengths and a declared explicit root representation before retargeting.

When the exported Unreal top-level root becomes the Blender Armature object, the normalized source is still incomplete until object root motion is transferred to an explicit non-deforming root bone and the former pelvis/IK roots are parented without changing evaluated poses. An object renamed `root`, a zero bone with no motion transfer, or importer-scale repair at runtime must fail closed.

Prefer a two-rig visual-bake conversion for that root step. Preserve the normalized imported rig as immutable evidence; create a separate source-working rig with the explicit non-deforming root and the former top-level bones parented beneath it; drive the new root from the source Armature object and every existing target bone from its source bone in world space; then bake evaluated pose transforms at every source sample and remove all temporary constraints. Compare world translations and complete matrices for every bone before accepting. Directly reparenting an animated rig and copying local pose channels is not equivalent and can introduce metre-scale drift.

Object scale `1` on both rigs is not proof of a shared unit domain. Compare character bounds and representative spine, arm and leg bone lengths before retargeting. Fail a representative target/source bone-length median outside `[0.1, 10]`. If a project deliberately uses Unreal-style centimetre numerics in Blender, convert rest data and every pose-location channel together, keep object scale at `1`, and prove that every converted world sample equals the pre-conversion sample multiplied by exactly `100` within a declared centimetre tolerance.

Recommended direction ownership:

- Unreal → Blender: one standard-skeleton Action FBX, raw import evidence, deterministic unit/root normalization, semantic source rig, offline target bake.
- Blender → Unreal: deterministic headless FBX export by default; optionally Send to Unreal after pinned-version compatibility tests. Export one current Action, bake evaluated animation, omit leaf bones and unrequested meshes, then clean-import in Unreal.

For Unreal animation FBX timing, preserve the Unreal asset's authoritative sequence length and sampled-key count in the handoff manifest. Audit every unique Blender Action key time after import using Blender's actual post-import scene FPS, because the classic importer may replace a requested FPS with the FBX time mode. A single leading importer-padding key may be removed only when the raw unique-key count is exactly `authoritativeSampleKeys + 1` and the remaining keys span the authoritative sequence length within the declared tolerance. Record both key sets and the measured duration. Any other mismatch fails closed; do not round the Action range, trim by eye, scale the Action or alter runtime playback speed.

For fractional authoritative sample times, do not force an integer-step bake. Keep the normalized source immutable, evaluate world-space constraints at the exact times, remove temporary constraints, and convert each desired pose matrix into local basis channels with Blender's parent-aware pose conversion before inserting keys. Avoid updating the dependency graph between setting an incomplete pose and writing its channels, because the partially built Action can overwrite the intended visual pose. Require a full-bone, full-sample world-matrix comparison and a clean-reopen audit of hierarchy, object scale, constraints, key count, duration and finite transforms.

### Blender-to-Unreal skeletal interchange profile

For an Unreal 5.x target using the documented FBX pipeline, declare one conversion owner. The measured Blender 5.2 / Unreal 5.8 profile uses Blender Metric with `scale_length=0.01` and centimetre numeric mesh, rest-bone and animation-translation data, while keeping mesh and armature object transforms at identity. Use `+Z` up, `-Y` character forward, and a unique non-deforming `root` above the pelvis/hips retarget root. Export FBX at global scale `1`, apply scene units with `FBX_SCALE_NONE`, use `-Y Forward / Z Up`, disable leaf bones, and include animation only when the package contract requests it. Import to Unreal at translation/rotation zero and uniform scale `1`, with scene conversion, scene-unit conversion and Front X Axis conversion enabled so runtime forward is `+X` and up is `+Z`.

Do not accept configuration flags as orientation evidence. Record a source foot-to-toe forward probe and compare source versus imported horizontal bounds: the expected one-time front-axis conversion swaps source X/Y extents into Unreal Y/X while preserving Z height. Also verify physical height, ground, root hierarchy, root zero weights, material slots, bone count, and that Unreal's IK Rig accepts the declared root-motion and retarget-root bones. Read the imported root's local reference transform from Unreal's reference skeleton and require scale exactly `[1,1,1]`; correct bounds and object/import scale values do not prove this. Reject importer node scale compensation, a root reference scale of 100 or 0.01, split unit domains, duplicated roots, double axis conversion, or a retarget-pose offset used to hide source ground errors.

The critical failure pattern is a mesh that appears at the correct physical height with import scale `1`, while the imported reference skeleton still stores root local scale `100`. Viewport appearance, mesh bounds and actor transforms can all look correct in that state; only a reference-skeleton audit exposes the invalid root. Fix it at the Blender/export profile, re-import to a new versioned asset path, and require exact root scale `[1,1,1]` before creating IK assets or animations. Do not patch the existing Unreal Skeleton in place or compensate in an actor, Animation Blueprint, retarget pose or downstream engine.

Keep diagnostic scans narrow. A forced full-content registry scan can repeatedly load legacy animation packages whose Skeleton dependencies are missing, producing compression noise and delaying automation. Scan only the source mesh, source animation, target mesh and production output paths needed by the operation; report broken legacy packages separately and preserve them unless cleanup is explicitly authorized.

Primary references: Epic's Unreal Engine 5.8 *Importing Skeletal Meshes Using FBX* and *FBX Import Options Reference*, plus Blender's current FBX import/export manual. Pin actual Blender/Unreal versions and validate the local exporter/importer behavior because FBX SDK and add-on behavior can change between releases.

## Offline target retarget

- Map semantic roles, not accidental names: root, pelvis, spine, chest, neck, head, clavicles, arms, hands, legs, feet, toes and optional fingers/IK helpers.
- Align source and target rest poses before judging animation. Fix A/T-pose, shoulder line, elbow/knee poles, wrist/foot orientation and character proportions explicitly.
- Retarget pelvis/root, torso and effectors with declared constraints. Add foot IK or plant correction only for measured contact windows.
- Transfer fingers only when the source has effective finger motion and the target finger rig/weights pass deformation QA. Declared tracks or mapped chains alone are not evidence of a fist.
- Preserve source Action, raw target result, corrected target work and accepted baked Action.
- Bake evaluated visual transforms to target deform bones. Remove export-time dependence on temporary controls, constraints, drivers or engine-only nodes.
- Preserve source sample times unless an explicit retiming contract authorizes resampling.

## Cleaning and acceptance

Report and inspect:

- unique root and root/pelvis responsibility;
- object scale, physical character height and representative reference bone lengths;
- root, pelvis and foot translation/rotation ranges at raw import, normalized source, target bake and runtime import;
- action count, stable action IDs, duration, sample times, loop/terminal semantics and curve inventory;
- foot-plant sliding, penetration and clearance per contact window;
- shoulder, elbow, wrist, fingers, hip, knee, ankle and twist deformation;
- NaN, bone explosions, hierarchy changes, detached equipment, mesh clipping and material/texture loss;
- loop pose/velocity seam or terminal recovery;
- target-camera playback at normal speed, slow motion and key action phases.

Fail closed on split unit domains, missing or duplicated roots, importer-only scale repair, foot sliding above the declared limit, visible deformation collapse, changed timing, extra Actions, missing textures, or a clean-scene re-import mismatch.

## Delivery package

Deliver:

- editable DCC source;
- target-skeleton FBX and/or GLB;
- textures and material mapping;
- a character/rig manifest;
- an animation-source manifest;
- a QA report and rendered evidence.

The manifests must use stable IDs and relative paths and record units, axes, handedness, ground, root/pelvis conventions, reference-pose hash, semantic map, mesh/bone/material/action counts, action timing, loop/root-motion/contact semantics, source/export hashes and tool versions.

Prefer GLB/glTF for the accepted runtime package when the target engine supports it. Keep FBX as the engine/DCC interchange and compatibility path. Re-import both accepted formats independently when both are promised.

Community Unreal-to-Godot exporters that wrap Unreal's built-in glTF exporter may be evaluated as version-pinned animation-only adapters. Require preview-mesh exclusion, explicit `cm → m` conversion, source/target skeleton identity, reference-pose and hierarchy hashes, clip timing/sampling/root metadata, file hashes and a clean target-engine re-import. A generated GLB and a success dialog are not acceptance evidence. Never let such an adapter export the Unreal-imported Skeletal Mesh as the runtime model when the character contract names a canonical DCC master; the runtime mesh, skin, rest skeleton, materials and textures must still derive from that master.

Test combined-preview, animation-only and mesh-only output as controlled variants before blaming a manual animation mapping step. Compare same-name node rest TRS and every animation sampler input/output numerically. If combined and animation-only curves are identical and all three rest-node transforms are identical, matching playback failure in both target-engine routes is not caused by separating the mesh or renaming track paths; it is an exporter/runtime-equivalence failure until the same UE action phase proves otherwise. Keep UE source playback evidence at the same phase and fail the adapter on any visible bone explosion even when bone count, hierarchy, duration and track resolution pass.

Material export is a separate gate. Re-run with the adapter's dependency/texture export options enabled, then inspect the engine exporter messages and dependency count. Audit both the persistent material asset and its actual material-expression texture references; do not infer that the source is empty merely because an adapter reports zero dependencies. Version-mismatched adapters can call a deprecated dependency API that returns an empty list even while the editor renders valid texture samples, and commandlet/offscreen export can fail to acquire a material bake resource that exists in the full editor. Compare the full-editor plugin path against the headless path before assigning ownership. Require a valid material asset path, texture dependencies, glTF images/textures, stable material slots and clean target-engine rendering.

Before copying or redistributing a community adapter, verify an actual license file at the pinned revision. A README license claim without the corresponding license text is sufficient for behavior research, but not sufficient provenance for public redistribution. If a user explicitly authorizes a private repository-local vendor snapshot for reproducibility, preserve the exact commit, upstream URL, README, missing-license warning and non-nested repository boundary; do not describe that snapshot as cleared for redistribution or as a production default until provenance and asset QA both pass.

## Runtime comparison

Compare the offline baked target with any runtime humanoid-retarget candidate using the same source action, clock, camera, world scale and ground. Label both paths. Runtime retargeting is accepted only when unmapped bones, rest pose, root motion, feet and deformation pass the same gates; the ability to play is not sufficient.

Keep animation presentation separate from gameplay truth. Animation callbacks do not own hits, damage, cancellation, cooldowns or attributes.

### Saved-pose versus rest-pose ground

A target that appears grounded in the Blender viewport is not necessarily grounded in bind/rest data. Record both raw mesh-vertex bounds and evaluated depsgraph bounds, plus non-identity pose-channel count, attached Action, current frame, rest-bone coordinates and root/feet transforms. `Object.bound_box` alone can reflect evaluated or cached state and is not an interchange proof.

When appending a target into a source scene, retain the exact object references returned by the library loader. Do not resolve them again by global object name, because name collisions can silently audit a source object.

If an approved posed target must become the interchange reference pose, create a versioned derivative and explicitly apply that pose as the new rest pose. Re-run visual-equivalence, zeroed-pose-channel, mesh/armature unit, unique-root, hierarchy, ground, skinning and clean re-import gates. Treat this as a declared reference-pose migration, never as a hidden ground offset.

### Optional Blender Extensions Retarget adapter

The official Blender Extensions `Retarget` package may be used as a Blender 5.x adapter for semantic presets, rest-pose alignment, scale/action repair, root/root-motion operations, constraint binding and evaluated action baking. Pin the extension version, package hash, Blender version, source/target mappings and every operator option. Keep the package in an isolated authoring environment; do not make it a runtime dependency.

Accept each responsibility independently. A verified `Apply As Rest Pose` result proves only reference-pose migration when evaluated vertices remain visually invariant, pose channels become identity, rest/evaluated ground agrees, and root/skin contracts pass. It does not prove the subsequent retargeted Action, foot contacts, deformation, timing or clean re-import. Retarget and bake outputs remain subject to the full offline-target and delivery gates above.

For headless Retarget automation, lock the selection direction: the active armature drives motion and selected non-active armatures receive constraints. Record both preset roles explicitly. Compare reference-pose modes and location policies before baking; valid constraints and visible motion can still suspend, penetrate or compress the target. If a user authorizes a rough-body preview, bake the least-bad structurally valid profile to a separately named candidate, preserve measured foot/finger defects, and keep it outside the accepted exchange package until plant-window cleanup and hand-shape QA pass.
