# Prompt and batching

## Prompt order

Write constraints in this order:

1. identity and reference roles;
2. camera, framing, scale, baseline, and facing;
3. action plane and force direction;
4. ordered beats with approximate time windows;
5. reset/hold behavior;
6. clean extraction background;
7. exclusions;
8. output packing layout.

For chroma extraction, use the full reusable scaffold in [clean-chroma-prompt-contract.md](clean-chroma-prompt-contract.md). “Green background” by itself is insufficient: the prompt must separately lock neutral subject rendering, stable camera/exposure, exact background field behaviour, and detached-effect exclusions.

Prefer spatial facts over vague animation adjectives. For an overhead strike, say that the weapon head rises above the head, descends on a steep arc, ends below the hands and hips near the ground, and then rebounds. “Powerful attack” alone does not constrain the path.

## Clean motion source and motion-native stylization

Separate animation texture from gameplay or environmental effects in every prompt.

Allowed when the art direction calls for stylized action:

- pose-to-pose squash and stretch;
- pronounced spring/rubber-body timing: deep anticipation compression, long directional extension, overshoot, recoil, and elastic recovery;
- controlled anatomy exaggeration at anticipation, travel, contact, and recovery;
- contour smear that remains visibly derived from the moving limb, hair, cloth, or weapon;
- a short directional trailing texture, only when explicitly requested, that follows the measured motion vector and disappears as the responsible part settles;
- selective action-bound blur inside the moving silhouette while the contact/readability pose remains clear.

Spring/rubber-body exaggeration may temporarily push normal proportions much further than ordinary squash/stretch, but it must preserve one continuous body topology, correct action axis/facing, support-foot/root behavior, identity/costume, and a sharp contact pose before recovering exactly to the approved runtime Idle. Extra limbs, disconnected body pieces, wrong-way stretch, permanent proportion drift, and deformation that obscures the action are failures.

Default to no authored trail. For an explicitly authorized body-bound trail, specify six observable properties: responsible part, measured path/direction, elongated shape, placement behind/between previous and current positions, one-to-two-frame lifetime, and disappearance as that part settles. It must mostly overlap the moving silhouette, remain non-emissive and colour-neutral, and never extend ahead of the contact point. “Attached to the limb” alone is never sufficient.

Forbidden in a clean character-motion source unless separately authorized by name:

- hit sparks, impact flashes, starbursts, shockwaves, explosions, energy slashes, projectiles, or target silhouettes;
- ground cracks, landing dust, footstep clouds, smoke, debris, splashes, environmental displacement, or invented contact surfaces;
- screen flashes, camera shake, global motion blur, detached afterimages, lighting changes, or particles that outlive the responsible motion.
- fist/foot glow, aura, orb, blob, circular or elliptical blur, halo, pressure puff, impact disc, bloom, luminous smear, or coloured outline, even when touching or overlapping the responsible body part.

Also forbid baked character lighting when the sprite will be lit at runtime: no directional key, rim, volumetric light, environmental colour cast, contact/cast shadow, reflection, dramatic highlight, or per-action grade. Keep stable neutral albedo-reference illumination and stable white balance.

Write both sides into the provider prompt: name the permitted motion-native deformation and explicitly exclude both detached VFX and body-attached aura/blob failure shapes. A trail is motion-native only when its origin, measured direction, elongated shape, behind-the-part placement, and short lifetime all pass; otherwise fail closed. If it depicts a hit result or world reaction, it is VFX and belongs in a separate asset pass.

When a user cites an existing game or animation as a quality reference, translate it into observable attributes such as snapped key poses, clear silhouette, held impact pose, controlled smear, foreshortening, and dimensional body rotation. Do not request a direct imitation of that title's characters, rendering, proprietary effects, or exact house style.

## Mandatory action-design preflight

For a roughly 256 px native gameplay character, begin layout selection with one subject at Mini 480p. Choose the fixed aspect ratio only after computing the padded motion envelope; 4:3 is one candidate, not the default for every action. Escalate density, resolution, or model only when this candidate fails pixel, padding, identity, or measured acceptance-yield gates. Estimate the exact planned configuration before each paid request even when a previous request used the same model.

Complete this non-billable stage before every provider call, including retries with a changed prompt or layout:

1. Draft 4–6 schematic key poses per action: canonical idle/loop seam, anticipation, travel/contact/apex, recovery, and canonical idle/loop seam.
2. Mark facing, incoming force, body/weapon reach, support foot, and the root position on every key pose. Use real root translation for displaced actions.
3. Calculate the union of body, weapon, and root path, then add 20–30% safety padding. Report the required final canvas and required source-cell size at the chosen oversampling factor.
4. Render one simple storyboard per action plus a combined envelope report. The diagram may be schematic; its job is to expose wrong direction, missing recovery, clipped weapon arcs, insufficient jump height, and fake in-place motion before money is spent.
5. Test 480p first with the fewest simultaneous subjects. Reject any layout whose source cell cannot contain the padded envelope at the locked character scale. Only then consider 720p.
6. Derive the Seedance ordered beats and exclusions from the accepted storyboard. Save the action plan, storyboard paths, envelope report, and prompt hash beside the redacted dry run.

No storyboard, no paid submission. If the action design changes, regenerate the storyboard and dry run before submitting; do not reuse stale envelope calculations.

Use `scripts/plan_action_storyboard.py` with root offsets in final asset pixels and per-pose reach `[left, up, right, down]`. The tool writes per-action SVG storyboards and a JSON envelope report. Treat its geometry as a conservative planning aid and visually inspect every diagram before provider use.

Minimal plan shape:

```json
{
  "canvas": [128, 128],
  "root": [64, 112],
  "body": {"width": 36, "height": 70},
  "paddingRatio": 0.25,
  "oversample": 3,
  "actions": [{
    "name": "dodge_backward",
    "facing": "right",
    "poses": [
      {"label": "idle", "root": [0, 0], "reach": [24, 70, 28, 0]},
      {"label": "travel left", "root": [-34, -4], "reach": [30, 54, 34, 2]},
      {"label": "recover", "root": [-8, 0], "reach": [24, 70, 28, 0]},
      {"label": "idle", "root": [0, 0], "reach": [24, 70, 28, 0]}
    ]
  }]
}
```

`root` values inside poses are offsets from the canonical root. `reach` is the conservative silhouette/weapon extent around that pose root, not a hitbox. Keep combat hitboxes as separate gameplay data.

## Packing distinct actions in one minimum clip

Use this mode when the user wants the maximum number of unique actions per billable generation or explicitly forbids repeated actions. Pack complete actions sequentially on one subject's timeline; do not create multiple simultaneous clones merely to fill time.

Plan the clip as:

```text
stable start -> idle beat -> walk cycle -> jump and landing -> attack -> stable end
```

### Canonical idle envelope

Unless the action contract declares a special start or terminal state, author every action segment as:

```text
canonical idle -> anticipation -> complete action -> recovery -> identical canonical idle
```

This is the default consistency technique for reusable game actions. In the prompt, explicitly require the same foot placement, facing, body scale, weapon grip, costume, root, ground baseline, and camera at both idle endpoints. Add a short readable idle hold at each boundary when duration allows. The ending idle must be a real recovered pose, not a cross-fade, reverse playback, abrupt snap, or newly invented guard pose.

For packed distinct actions, the recovered idle is also the separator and the next action's start. Detect the actual return-to-idle boundary after download rather than trusting exact timestamps. Store an idle-endpoint similarity check in QA: compare silhouette, root, baseline, scale, facing, weapon state, and identity between the first and last stable frames.

Declare exceptions instead of silently breaking the rule. Common exceptions include looping locomotion, held block/charge/aim, knockdown, death, combo links, ledge states, and actions whose gameplay root intentionally ends at a new position. Even for an exception, name the exact terminal pose and how runtime exits it.

Rules:

- Keep one subject, one identity, one camera, one scale, and one ground line throughout.
- Name actions as ordered `镜头1 / 镜头2 / 镜头3` or ordered action beats. Seedance 2.0's official guide says exact timings such as `0–3 秒` are unstable, so treat any per-action frame schedule as intent, not a guaranteed cut list.
- Describe the transition into and out of every action so motion boundaries remain detectable.
- Do not repeat an action as filler. If the remaining time cannot hold another complete action, request a stable end hold.
- Detect the actual action boundaries from motion energy and visual review after download; never cut solely from requested timestamps.
- For a four-second 24 FPS result, the nominal source contains about 96 frames, but extract by presentation timestamps and retain only coherent action windows.

This mode increases unique-action yield but gives fewer alternate takes. Use repetition instead when take selection is more valuable and the user allows it.

## Resolution break-even for filled two-second actions

For the verified Seedance 2.0 Mini project sample, a 4-second 720p, 4:3, image-reference task used 87,850 output tokens and two matching 480p tasks used 39,891 tokens each. The simple output-pixel-area estimate for 480p was 2.12% low, so use area scaling only for planning and replace it with the receipt.

For a 64–72 px final character with approximately 25–30% large-motion margin:

- a conservative 480p layout holds one large subject, so two complete 2-second actions fit temporally;
- a filled 720p 2×2 layout holds four subjects, each performing two different 2-second actions, for eight actions total;
- with the measured project receipts (about ¥0.9175 for 480p and ¥2.0206 for 720p), the nominal single-subject per-action cost is about ¥0.46 versus ¥0.25;
- 720p beats the single-subject 480p layout once at least five distinct actions survive extraction and QA;
- if compact motions allow two safe 480p subjects, 480p can yield four actions at about ¥0.22 each and becomes slightly cheaper again.

Treat this as a break-even rule, not a provider guarantee. Record actual tokens, accepted actions, and paid retries per clip. Compare `cost / accepted distinct actions`, never requested actions. Do not count duplicate filler or incomplete transitions.

One filled-grid test found that all eight propositions remained visually readable in both tiers, but the strict canonical-idle envelope passed only 5/8 at 480p and 2/8 at 720p. Dense packing can therefore maximize readable motion while reducing immediately reusable action yield. Report both `cost / readable action` and `cost / strict idle-envelope pass`; never treat motion readability alone as acceptance.

The project's visual review judged the 480p and 720p results broadly similar in perceived quality and selected a 480p-first policy. Use 480p whenever the source-pixel and padded-envelope gates pass. Prefer one or two controllable subjects over a denser grid: even when a dense layout looks cheaper on requested-action count, more simultaneous characters increase motion-logic, direction, identity, and idle-reset failure risk. Use a larger 720p cell or lower-density layout only for jumps, lunges, knockbacks, and forward/back dodges whose real root path plus padding would otherwise be clipped or force the character below the size budget.

### Motion-envelope cost selection

For every action, estimate or measure:

```text
motion_envelope = union(character, weapon, root_path) + 20–30% safety padding
candidate_value = expected fully accepted distinct actions / expected task cost
```

Evaluate 480p and 720p candidate layouts with the same visible character height. Reject a layout if any padded envelope crosses its cell, if root travel is compressed into an in-place pose, or if source character pixels fall below budget. Discount expected yield as simultaneous subject count rises; base that discount on prior identity, direction, idle-reset, and full-gameplay acceptance rates rather than assuming every requested cell succeeds. For this project, choose in order: safe 480p with the fewest practical subjects, safe 480p with a second subject when clearly controlled, then 720p at the lowest density needed for the envelope. Replace estimates with receipt cost and fully accepted actions after every run.

Do not upgrade resolution merely to pack more characters. Upgrade only when the larger per-cell spatial budget materially improves final acceptance. If 480p and 720p are both safe and their perceived quality is similar, choose 480p.

### Default side-view direction contract

Unless the user declares another convention, write prompts with all characters facing screen-right and all frontal interactions arriving from screen-right:

- `walk_forward`: seamless loop, body faces right, world root travels right;
- `walk_backward`: seamless backward-walk loop, body still faces right, world root travels left;
- `dodge_forward`: face right, evade right with real positive root displacement, then recover;
- `dodge_backward`: face right, evade left toward the character's back with real negative root displacement, then recover;
- `block`: raise guard toward the right and absorb a hit travelling from right to left;
- `hit_react`: receive the frontal hit from the right and recoil/slide left;
- `jump_land`: preserve authored horizontal travel when requested; allocate vertical and horizontal envelope rather than forcing an in-place hop.

State `facing`, `incoming force`, `world travel`, and `terminal root` separately. A correct silhouette with the wrong force direction is a failed action.

## Repeating a short action in one clip

Use repetition when provider minimum duration is much longer than the action. This improves yield from time already being billed; it does not necessarily reduce the provider's cost per generated second.

Plan each take as:

```text
stable start hold -> complete action -> stable end hold -> reset hold
```

Rules:

- Keep the same camera, character position, scale, direction, and action for every take.
- Leave 0.2–0.5 seconds of stable separation when duration allows.
- Ask for clean complete repeats, not a looping blur.
- Prefer 2–4 repeats. Too many repeats cause timing compression and identity drift.
- Keep a declared take schedule in metadata; detect actual motion boundaries after download.
- Select one complete take. Do not splice best-looking isolated frames from different takes unless identity continuity is revalidated.

Example:

```text
In the 4-second clip, perform the same 0.75-second overhead staff strike three times. Start each take from the identical guard pose at the same ground line. Use 0.3 seconds of complete stillness between takes. No camera movement, cuts, motion blur, afterimages, particles, or lighting changes. After the third take, hold the final guard pose.
```

If the service ignores exact times, preserve the ordered repeat count and stable separators; derive true windows from motion energy rather than assuming prompt timing was obeyed.

## Low-resolution multi-cell batches

Prefer one subject performing distinct actions sequentially. If the user explicitly requires a same-character grid with distinct actions, never pair complementary semantics such as attack+guard, attack+hit, attack+reaction, or reach+counter. Treat the cells as independent animation previews rather than one scene: each subject owns a fixed anchor and inward-facing motion bound, both envelopes remain disjoint, a wide empty isolation corridor remains untouched, and neither subject has a target, opponent, eye contact, contact event, or shared timing cue. Declare `simultaneousSubjects`, `packingMode: independent_grid_distinct_actions`, and a complete `cellIsolation` contract; paid preflight rejects missing isolation evidence. The source is still failed if the provider creates interaction, contact, a shared effect, or corridor crossing.

Use simultaneous grids only when each cell retains enough source pixels. A 2×2 batch is usually the practical upper bound for 720p character work; test before increasing density.

Seedance 2.0's official prompt guide reports reduced stability when more than four reference people are used, and warns that multi-view character boards can trigger duplicate “twin” subjects. For sprite batching, keep the number of simultaneously generated same-character subjects at four or fewer, explicitly bind each subject to its cell, and prefer a clean single-character reference over a turnaround collage when duplicate clones are appearing.

Estimate source character height:

```text
cell_height = output_height / rows
source_character_height = cell_height * vertical_occupancy
required_source_height = target_character_height * oversample
```

Default guidance:

- use `vertical_occupancy` 0.70–0.82;
- require 3×–4× oversampling for hand-painted sprites;
- require at least 2×–3× oversampling for intentionally hard-edged pixel art;
- also require roughly 128–192 source pixels of character height so faces, hands, and weapons remain separable before final pixel reduction.

Reject the grid when `source_character_height < required_source_height`. Reduce rows/columns or use sequential packing.

Grid prompt rules:

- Declare exact rows, columns, cell order, and cell purpose.
- Add high-contrast gutters and one flat background color across all cells.
- Require one complete subject, one weapon, and one action per cell.
- Keep every subject centered on its own fixed baseline and forbid crossing cell boundaries.
- Use different motions in cells only when the model can maintain identity; otherwise repeat variants of the same motion.
- Chroma-key before splitting. Generated subjects may cross nominal dividers even when the grid appears regular.
- Use one continuous backing field across all cells. Do not draw or request divider lines, cell panels, alternating fills, or per-cell exposure. Reject full-height or full-width luminance/chroma bands before keying; they indicate the model rendered separate panels instead of one constant extraction field.
- For a 480p two-column pixel-character batch targeting a 256 px runtime sprite, prefer roughly 300–336 source pixels of canonical-idle visible height when the action envelope still fits. A smaller subject may remain semantically readable but lose stable pixel clusters after extraction and downsampling.

For final low-pixel output, extract at source resolution, register first, then apply nearest-neighbour downsampling and palette quantization. Never use bilinear/bicubic scaling after the final pixel reduction.

## Reference strategy

- For every action of an established game character, use both the approved canonical runtime pixel Idle and an approved front/side/back turnaround as mandatory identity references. The two assets must share the same renderer, native pixel language, palette, proportions, costume, material treatment, and approximate gameplay detail level. Prefer a turnaround authored at the same visible character height and inspected at 1:1 game pixels. Reject concept-art sheets, painterly illustrations, photoreal renders, smooth high-resolution redesigns, or any turnaround whose visual language does not match the runtime Idle.
- Assign reference roles explicitly. The runtime Idle is the canonical pixel/root/baseline/scale and start/end-pose authority. The turnaround supplies identity evidence for front/back/side anatomy, hair volume, costume construction, asymmetry, and details hidden in the gameplay-facing Idle. Neither may silently override the other; resolve discrepancies before a provider call.
- Do not create or request action keyframe boards for ordinary actions. Use text plus the mandatory Idle and turnaround by default. Add an action-specific pose/keyframe reference only for a user-declared special need or after a recorded provider failure proves that the ordinary identity set cannot communicate a required pose/path. Keep that board in the same game-art renderer and label it as motion control, never identity authority.
- Build any chroma upload board at 1:1 native pixels by default. If a provider forces enlargement, use only a declared integer nearest-neighbour scale and record it; never smooth-resample or generatively redraw the runtime pixel Idle.
- Use one compact motion board to communicate path and rhythm; avoid a dense style collage.
- When supported, use first+last frames for endpoint control and a separate reference image for identity.
- When a provider forbids mixing first/last-frame roles with reference media, merge identity and motion constraints into one reference image. If the output must be chroma-keyed, build that merged reference on the exact target key colour; a dark, textured, or scenic reference background can override a text-only request for a flat background, especially on lightweight models.
- For a merged chroma reference board, composite every reference subject onto one perfectly uniform key field. Remove ground shadows, gradients, borders, labels, texture, scene fragments, and unused transparency before upload. State the exact key value in the prompt, but treat the pixels in the reference board as the stronger constraint.
- Remove text from visual references when the provider tends to render labels into the output.
- Use a pure chroma background only when the character palette is sufficiently separated. Otherwise use an alternate key color or background matting workflow.

## Retry policy

Classify failure before retrying:

- **provider-generation failure:** wrong action plane, camera cut, identity/anatomy drift, missing weapon, mixed cells -> one prompt/reference correction and one retry;
- **local import failure:** crop, chroma edge, frame timing, baseline, scale, padding -> fix deterministically without another provider call;
- **asset-contract failure:** insufficient source pixels or clipping caused by layout -> reduce packing density before retrying;

If one isolated prompt/reference correction reproduces the same semantic substitution (for example a bent-joint strike repeatedly becomes a straight-limb strike), stop prompt-only retries for that provider/model. Mark the action unavailable and require a materially different control input, provider capability, or authored fallback. Stronger wording alone is not a new control method. Likewise, when a forbidden detached impact effect reappears after the correction, treat it as provider-generation failure rather than silently accepting the contaminated source because post-processing might hide it.
- **isolated bad take:** choose another repeat from the same clip before generating again.

Default to at most one automatic paid retry per brief unless the user explicitly authorizes a larger budget.
