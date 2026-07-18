# VRM Unreal-to-Godot character pipeline

Use this route when one VRM character must receive Unreal-authored humanoid actions and retain its native materials, expressions and secondary motion in Godot.

## Ownership

- The original versioned VRM is the canonical runtime model source for mesh, skin, rest skeleton, MToon materials, textures, morph expressions and `VRMC_springBone` data.
- Unreal is an animation broker. VRM4U may import the same VRM, create its generated humanoid/IK assets and retarget standard Unreal actions, but the Unreal Skeletal Mesh is not promoted to the Godot model source.
- The portable SpriteFlux UE-to-Godot Bridge transports approved target-skeleton animation as an animation-only GLB with a hashed inventory.
- The Godot project owns `godot-vrm` import, `SkeletonProfileHumanoid`/`BoneMap` configuration, AnimationLibrary assembly and final rendered QA.

## Reproducible route

1. Preserve and hash the original VRM. Record VRM version, humanoid mapping, physical height, forward/up, root/hips semantics, material and expression counts, SpringBone chains and license metadata.
2. Pin VRM4U to the actual Unreal Engine version. Import into a versioned content path and reuse the plugin-generated character-level IK assets when they pass structural inspection.
3. Retarget one approved standard action to the VRM target skeleton. Check complete playback, timing, root, ground, body joints and known finger/secondary limitations in Unreal.
4. Export only that approved target animation through the portable bridge. Require zero meshes and materials, one declared clip, target skeleton identity, duration/sample metadata, unit/axis contract and SHA-256.
5. Pin `V-Sekai/godot-vrm` and its MToon dependency to a tested commit. Install them at their required unrenamed addon paths and load-test the exact Godot version before importing content.
6. Import the same original VRM into Godot. Require its original meshes, material slots, MToon textures, morphs, `GeneralSkeleton` and `secondary` SpringBone node; do not replace them with Unreal exports.
7. Import the animation-only GLB with an explicit `SkeletonProfileHumanoid` BoneMap. Normalize the mapped position/rest contract once at import, keep all wrapper scales at one, and resolve tracks to the target `GeneralSkeleton` without per-action offsets.
8. Add the non-looping action to a separate AnimationLibrary. A QA player may replay it, but must not change the asset's terminal semantics.
9. Validate raw materials and animation first, then SpringBone as a separate presentation layer. Save start/contact/recovery frames, exercise pause/frame-step/camera controls, and confirm the main game does not reference the experiment before approval.

## Secondary-motion contract

VRM hair, skirt, coat-tail and optional body secondary motion is normally bone-based, not vertex-cloth simulation. The body Action may key the root of a secondary chain so the attachment follows the animated body. `godot-vrm` then evaluates the remaining chain every frame using VRM SpringBone stiffness, drag, gravity, hit radius and colliders, applying the result after animation through Godot's skeleton modifier stage.

Therefore:

- keyed secondary roots do not mean the complete sway is baked;
- a skinned mesh following simulated bones is not full cloth, self-collision or vertex folding;
- preserve helper bones, weights, chain parameters and colliders from the original VRM;
- do not bake SpringBone into every body Action unless the delivery contract explicitly requests deterministic baked secondary motion;
- compare physics on/off with a control that truly disables the active SkeletonModifier callback, not merely the visible `secondary` node.

## Version-specific failure gate

Importer cleanup options are not assumed safe. In one validated Godot 4.7.1 plus pinned godot-vrm route, enabling `retarget/remove_tracks/*` caused out-of-bounds `Animation::remove_track` failures. The accepted control preserved mapped and secondary tracks while keeping BoneMap rename/rest normalization enabled. Re-test this behavior for every Godot/plugin version; never silently discard tracks to make an import finish.

## Acceptance

Pass only when the VRM source hash, plugin commits, model/material/expression/SpringBone inventory, target skeleton map, animation timing/track inventory, scale/axis/ground, real playback and final rendering are recorded. Material success, retarget success and secondary-physics success remain independent gates.
