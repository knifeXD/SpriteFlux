"""Deterministic UE 5.x glTF/GLB export using public Unreal Python APIs only."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any

import unreal


SCHEMA_VERSION = 1
SUPPORTED_BAKE_MODES = {
    "DISABLED": unreal.GLTFMaterialBakeMode.DISABLED,
    "SIMPLE": unreal.GLTFMaterialBakeMode.SIMPLE,
    "USE_MESH_DATA": unreal.GLTFMaterialBakeMode.USE_MESH_DATA,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _asset_kind(asset: Any) -> str:
    if isinstance(asset, unreal.AnimSequence):
        return "animation"
    if isinstance(asset, unreal.SkeletalMesh):
        return "skeletal_mesh"
    if isinstance(asset, unreal.StaticMesh):
        return "static_mesh"
    raise TypeError(f"unsupported_asset_type:{asset.get_class().get_name()}")


def _options(profile: dict[str, Any], asset_kind: str) -> unreal.GLTFExportOptions:
    bake_mode_name = str(profile.get("materialBakeMode", "SIMPLE")).upper()
    if bake_mode_name not in SUPPORTED_BAKE_MODES:
        raise ValueError(f"unsupported_material_bake_mode:{bake_mode_name}")

    options = unreal.GLTFExportOptions()
    options.export_uniform_scale = float(profile.get("exportUniformScale", 0.01))
    options.adjust_normalmaps = bool(profile.get("adjustNormalMaps", True))
    options.export_vertex_skin_weights = True
    options.make_skinned_meshes_root = True
    options.bake_material_inputs = SUPPORTED_BAKE_MODES[bake_mode_name]
    options.texture_image_format = unreal.GLTFTextureImageFormat.PNG
    options.export_preview_mesh = bool(profile.get("includePreviewMesh", False)) if asset_kind == "animation" else True
    options.export_unlit_materials = True
    options.export_clear_coat_materials = True
    options.export_texture_transforms = True
    options.export_emissive_strength = True
    options.export_vertex_colors = bool(profile.get("exportVertexColors", False))
    options.default_level_of_detail = int(profile.get("lod", 0))
    options.export_cameras = False
    options.export_lights = False
    options.export_hidden_in_game = False
    return options


def _read_glb_inventory(path: Path) -> dict[str, int]:
    if path.suffix.lower() != ".glb":
        return {}
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("invalid_glb_header")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A:
        raise ValueError("glb_first_chunk_not_json")
    document = json.loads(raw[20 : 20 + json_length].decode("utf-8").rstrip(" \t\r\n\0"))
    return {
        "nodes": len(document.get("nodes", [])),
        "meshes": len(document.get("meshes", [])),
        "skins": len(document.get("skins", [])),
        "animations": len(document.get("animations", [])),
        "materials": len(document.get("materials", [])),
        "textures": len(document.get("textures", [])),
        "images": len(document.get("images", [])),
    }


def _export_messages(messages: Any) -> list[str]:
    if messages is None:
        return []
    result = []
    for property_name, label in (("suggestions", "Info"), ("warnings", "Warning"), ("errors", "Error")):
        try:
            for message in messages.get_editor_property(property_name) or []:
                result.append(f"[{label}] {message}")
        except Exception:
            continue
    return result


def export_request(request: dict[str, Any]) -> dict[str, Any]:
    """Export declared UE assets and return a machine-readable report."""
    output_directory = Path(request["outputDirectory"]).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    overwrite = bool(request.get("overwrite", False))
    extension = str(request.get("format", "glb")).lower()
    if extension not in {"glb", "gltf"}:
        raise ValueError(f"unsupported_format:{extension}")

    results = []
    for item in request.get("assets", []):
        asset_path = str(item["assetPath"])
        asset = unreal.load_asset(asset_path)
        if asset is None:
            raise RuntimeError(f"asset_not_found:{asset_path}")
        kind = _asset_kind(asset)
        stable_id = str(item.get("stableId") or asset.get_name())
        destination = output_directory / f"{stable_id}.{extension}"
        if destination.exists() and not overwrite:
            raise FileExistsError(f"output_exists:{destination}")

        messages = unreal.GLTFExporter.export_to_gltf(
            asset,
            str(destination),
            _options(item, kind),
            set(),
        )
        if not destination.is_file():
            raise RuntimeError(f"export_output_missing:{destination}")
        results.append(
            {
                "stableId": stable_id,
                "assetPath": asset_path,
                "assetKind": kind,
                "relativePath": destination.relative_to(output_directory).as_posix(),
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "inventory": _read_glb_inventory(destination),
                "messages": _export_messages(messages),
                "profile": {
                    "exportUniformScale": float(item.get("exportUniformScale", 0.01)),
                    "includePreviewMesh": bool(item.get("includePreviewMesh", False)),
                    "materialBakeMode": str(item.get("materialBakeMode", "SIMPLE")).upper(),
                    "adjustNormalMaps": bool(item.get("adjustNormalMaps", True)),
                },
            }
        )

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "status": "pass",
        "exporter": "SpriteFluxUnrealGodotBridge",
        "exporterVersion": "1.0.0",
        "engineVersion": unreal.SystemLibrary.get_engine_version(),
        "renderOffscreenRequiredForMaterialBake": True,
        "outputDirectory": str(output_directory),
        "assets": results,
    }
    report_path = output_directory / "spriteflux-ue-godot-export.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    unreal.log(f"SPRITEFLUX_UE_GODOT_REPORT={report_path}")
    return report


def export_request_file(request_path: str | os.PathLike[str]) -> dict[str, Any]:
    path = Path(request_path).resolve()
    request = json.loads(path.read_text(encoding="utf-8"))
    return export_request(request)
