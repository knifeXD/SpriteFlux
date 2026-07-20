# Portable Unreal-to-Godot bridge

Use this reference when a new project must reproduce the accepted UE-to-Godot model/material/animation handoff without downloading a third-party exporter.

## Install

From the SpriteFlux checkout:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_unreal_godot_bridge.ps1 -UnrealProjectDirectory D:\Path\To\Project
```

Enable `SpriteFlux Unreal Godot Bridge`; its descriptor enables Python Script Plugin, Editor Scripting Utilities and GLTF Exporter. Pin Unreal Engine and Godot versions in the project manifest before generating assets.

## Request

Create a project-private JSON file. Do not commit private asset paths to public SpriteFlux.

```json
{
  "outputDirectory": "D:/Project/Saved/Exchange/character-v001",
  "format": "glb",
  "overwrite": false,
  "assets": [
    {
      "stableId": "character-version-material-preview",
      "assetPath": "/Game/Characters/CharacterV001/SK_CharacterV001",
      "materialBakeMode": "SIMPLE",
      "exportUniformScale": 0.01
    },
    {
      "stableId": "attack-version",
      "assetPath": "/Game/Characters/CharacterV001/Animations/AttackV001",
      "includePreviewMesh": false,
      "materialBakeMode": "SIMPLE",
      "exportUniformScale": 0.01
    }
  ]
}
```

Run material export with `UnrealEditor-Cmd -unattended -RenderOffScreen`, set `SPRITEFLUX_UE_GODOT_REQUEST` to the request path, and execute the plugin's `run_spriteflux_ue_godot_export.py`. Do not use `-NullRHI` for material delivery.

## Profiles

- `SIMPLE`: default material delivery; require Base Color, Normal and declared Metallic/Roughness bindings in the GLB audit.
- `USE_MESH_DATA`: use only for material graphs that genuinely require mesh data.
- `DISABLED`: expression-only control; not a complete material profile when packed PBR inputs require baking.
- animation-only: set `includePreviewMesh=false`; zero materials is correct.
- material/mesh export: for `blender_canonical` or `vrm_canonical`, label the Skeletal Mesh/combined Preview Mesh output diagnostic. For `ue_native`, the same output may become the accepted runtime model only after provenance, export-rights, structure, material and playback gates all pass.

## Required downstream gates

The generated `spriteflux-ue-godot-export.json` records engine version, profile, hashes and GLB inventory. A game project must still verify:

- `sourceRoute` is one of `ue_native`, `vrm_canonical` or `blender_canonical`, and the manifest names one authoritative source;
- source provenance and licence permit the intended export and non-UE runtime use;
- model/skeleton/material/animation versions match the canonical manifest and exact UE asset paths;
- meter-scale height, ground, forward and all wrapper scales;
- bone count, hierarchy and rest hash;
- animation ID, duration, sample times, tracks, root semantics and complete playback at start/middle/end plus contact windows;
- material slots, embedded images, Base Color/Normal/PBR bindings and real rendering;
- no non-finite transforms, visible limb separation, bone explosion, foot sliding or phase mismatch against the same UE source action;
- no main-world reference before explicit acceptance.

Material acceptance and animation acceptance are independent. Preserve a known animation defect when the user explicitly requests material-only review, but never label that animation runtime-ready. If animation export fails while a UE-native model/material export passes, retain the accepted model route and repair or replace only the animation transport; do not force the model through Blender without a model-side defect.

## Validated baseline

The bundled bridge was smoke-tested with Unreal Engine 5.8.0 using `UnrealEditor-Cmd -unattended -RenderOffScreen` and the `SIMPLE` profile. The generated Skeletal Mesh GLB contained 57 nodes, one mesh, one skin, one material, three textures and three embedded images, and the bridge wrote its SHA-256 inventory without opening an interactive editor. This validates installation and material export responsibilities only; each new project's model identity and animation playback still require their own gates.
