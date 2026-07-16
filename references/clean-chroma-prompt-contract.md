# Clean chroma motion-source prompt contract

Use this contract for video intended for sprite extraction. It translates provider guidance into observable constraints and separates three independent facts: the character's albedo-like appearance, the motion, and the extraction field.

## Prompt order

1. **Identity anchor:** for an established game character, bind both the approved canonical runtime pixel Idle and the matching game-quality front/side/back turnaround. Preserve the Idle's exact pixel geometry, alpha, visible height, root, baseline, facing, proportions, costume, and palette; use the matching turnaround to preserve hidden-side anatomy, hair volume, costume construction, and asymmetry. Reject concept art, smooth illustration, or any turnaround rendered in a different style. Ordinary actions need no separate keyframe art; add it only for an explicit special motion-control need.
2. **Sprite camera:** locked camera, fixed framing, constant scale, fixed ground line, no cut, pan, tilt, orbit, zoom, rack focus, exposure shift, or depth-of-field change. Seedance 2.0 does not expose `camera_fixed`, so this remains a prompt constraint and a visual QA gate.
3. **Neutral character rendering:** even albedo-reference illumination; stable exposure and white balance; no directional key light, rim light, volumetric light, dramatic highlight, environmental colour cast, contact shadow, cast shadow, reflection, or per-action grade. Runtime lighting belongs to the game engine.
4. **Action beats:** body part, direction, amplitude, speed, force, support foot, root path, inertia, recovery, and canonical start/end. Use ordered beats rather than exact timestamps.
5. **Motion-native stylization:** allow declared squash/stretch, including pronounced spring/rubber-body compression, long directional extension, overshoot, recoil, and elastic recovery. Keep one continuous body topology, the authored action path/facing, support foot/root, readable contact pose, identity/costume, and exact recovery to the approved Idle. Default to no authored trail. When a trail is explicitly requested, require an elongated low-opacity smear along the measured motion vector, behind or between the responsible part's previous/current positions, mostly overlapping its silhouette, never ahead of contact, non-emissive, colour-neutral, and gone within one or two authored frames as that part settles.
6. **Flat extraction field:** one exact high-saturation key colour across every pixel outside the subject. Require no gradient, texture, floor plane, horizon, vignette, noise, compression pattern, shadow, reflection, glow, light spill, exposure pulse, colour-temperature shift, or background animation. Keep the subject separated from every frame edge and cell gutter.
7. **Effect exclusions:** no attack arc, energy slash, impact ring, flash, spark, particle, projectile, smoke, dust, debris, ground reaction, screen flash, camera shake, duplicate subject, detached afterimage, subtitle, logo, or watermark. Also forbid fist/foot glow, aura, orb, blob, circular or elliptical blur, halo, pressure puff, impact disc, bloom, luminous smear, and coloured outline even when they touch or overlap the moving body part.
8. **Packing:** name the fixed cell count and gutters only after the source-pixel and motion-envelope gates pass.

## Copyable scaffold

```text
IDENTITY — One complete subject, called SUBJECT throughout. Use the approved canonical runtime pixel Idle plus the matching front/side/back game-quality turnaround as the mandatory identity references. Preserve the Idle's pixels, alpha, visible height, root, baseline, costume, proportions, facing, and palette; use the turnaround only to preserve hidden-side anatomy, hair volume, costume construction, and asymmetry. Do not substitute concept art, smooth illustration, add another person, or redesign any part. No action keyframe board unless the brief explicitly declares a special motion-control need.

CAMERA — Locked sprite-extraction camera. Constant framing, orthographic-like side-view readability, fixed subject scale and ground line. No cuts, pan, tilt, orbit, zoom, focus change, exposure change, or camera/global blur.

RENDERING — Neutral albedo-reference appearance with even illumination, stable exposure, and stable white balance. No directional key light, rim light, volumetric light, environmental colour cast, dramatic highlight, contact shadow, cast shadow, reflection, or baked scene lighting.

ACTION — <ordered observable beats; body part; direction; amplitude; speed; support foot; root path; recovery>.

MOTION TEXTURE — Permit <named body-bound squash/stretch>, including pronounced spring compression, directional extension, overshoot, recoil, and elastic recovery when requested. Preserve one continuous body topology, the real action axis, support-foot/root contract, identity/costume, and exact return to the approved Idle. Default to no trail. If a trail is explicitly authorized, it must be elongated along the measured motion vector, lie behind or between the responsible part's previous and current positions, overlap that silhouette for most of its area, never lead the contact point, remain non-emissive and colour-neutral, and vanish within one or two authored frames as that part settles. Keep the readable contact pose sharp.

BACKGROUND — Perfectly uniform solid KEY_RGB in every pixel outside SUBJECT for chroma extraction. No gradient, texture, floor, horizon, vignette, noise, shadow, reflection, glow, spill, colour drift, exposure pulse, or background animation. KEY_RGB must not appear in SUBJECT.

EXCLUDE — No attack arc, energy, impact ring, hit flash, spark, particle, projectile, smoke, dust, debris, ground effect, screen effect, camera shake, detached afterimage, duplicate, text, logo, or watermark. No fist/foot glow, aura, orb, blob, circular or elliptical blur, halo, pressure puff, impact disc, bloom, luminous smear, or coloured outline, including shapes attached to or overlapping a limb or weapon.
```

## Reference-board rule

The exact-chroma reference board is stronger than a text-only background request on lightweight models. For an established character, composite the approved canonical runtime pixel Idle deterministically over the same `KEY_RGB`, preserving embedded alpha and native foreground pixels at 1:1 by default. Record its native dimensions, canonical canvas, visible height, root, baseline, source/output hashes, key RGB, background coverage, placement, scale, and resize filter. If enlargement is unavoidable, use only a declared integer nearest-neighbour scale; never use LANCZOS, bilinear, bicubic, or a generative redraw for the pixel identity reference.

Do not request a generative redraw merely to change the reference background. If the subject contains the chosen key colour, select a different high-saturation key before generation and declare that semantic colour conflict in the extraction contract.

## Acceptance before keying

Reject the source before expensive cleanup when any of these is visible or measured:

- spatial background gradients, floor/horizon, shadows, reflections, glow, or scenic remnants;
- cross-frame key hue/exposure drift beyond the declared tolerance;
- key-coloured lighting or trails contaminating the subject outline;
- baked character lighting that should belong to runtime;
- detached combat/environment effects;
- circular/elliptical body-attached glows or blobs, or any smear that leads the contact point instead of following measured motion;
- subject touching frame edges/gutters or changing camera scale.

Local keying may solve ordinary mixed edge pixels produced by compositing. It must not be used to disguise a globally non-uniform, animated, or semantically contaminated background.
