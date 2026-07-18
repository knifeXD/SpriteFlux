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
- material preview: export the Skeletal Mesh or use a separately labelled combined Preview Mesh candidate. This is diagnostic and does not replace the canonical DCC model.

## Required downstream gates

The generated `spriteflux-ue-godot-export.json` records engine version, profile, hashes and GLB inventory. A game project must still verify:

- model/skeleton version matches its canonical manifest;
- meter-scale height, ground, forward and all wrapper scales;
- bone count, hierarchy and rest hash;
- animation ID, duration, tracks and real playback;
- material slots, embedded images, Base Color/Normal/PBR bindings and real rendering;
- no main-world reference before explicit acceptance.

Material acceptance and animation acceptance are independent. Preserve a known animation defect when the user explicitly requests material-only review, but never label that animation runtime-ready.

## Validated baseline

The bundled bridge was smoke-tested with Unreal Engine 5.8.0 using `UnrealEditor-Cmd -unattended -RenderOffScreen` and the `SIMPLE` profile. The generated Skeletal Mesh GLB contained 57 nodes, one mesh, one skin, one material, three textures and three embedded images, and the bridge wrote its SHA-256 inventory without opening an interactive editor. This validates installation and material export responsibilities only; each new project's model identity and animation playback still require their own gates.
