# Indexed export backends

Read this reference when a project wants true Indexed PNG, an editable `.aseprite` sequence, or Aseprite sprite-sheet export after SpriteFlux processing.

Use `export_indexed_png_sequence.py` as the default dependency-free SpriteFlux backend. It encodes the approved shared-palette RGBA sequence as true Indexed PNG, reserves index 0 for transparency, and requires an exact RGBA round-trip.

Use `export_aseprite_indexed_sequence.py` only when a user-provided local Aseprite is available and the project also needs `.aseprite` authoring or Aseprite sheet/tag tooling. Both backends must consume the same passing build/audit reports and render identical RGBA pixels.

## Responsibility boundary

Aseprite is an optional local export backend, not a video-matting system. Complete these stages in SpriteFlux first:

1. extract source frames by PTS;
2. key the full constant-chroma frame with border-connected background and temporal topology protection;
3. apply one shared canvas/root/baseline registration;
4. perform premultiplied alpha-aware reduction to a fixed virtual pixel grid;
5. recover residual chroma only in the narrow contour band when the character contract excludes intentional key-coloured material;
6. build and audit one non-dithered shared palette for the complete action.

Only then use Aseprite to encode the already-approved RGBA colours as Indexed pixels. Do not let Aseprite independently quantize contaminated chroma edges: palette clustering can turn a small colour bias into a stable visible fringe.

## Installation and licensing

Do not bundle, download automatically, or redistribute Aseprite source or binaries. Accept a user-provided executable through `--aseprite`, `ASEPRITE_EXE`, or `PATH`. Record executable hash/version in the export report.

Aseprite source and binaries use the [Aseprite EULA](https://github.com/aseprite/aseprite/blob/main/EULA.txt). A locally compiled copy may be used for the user's permitted personal purpose, but must not be committed to SpriteFlux or distributed with a game/tool package. SpriteFlux scripts and Lua adapters are independently authored and contain no Aseprite source.

## Native SpriteFlux export

```text
python scripts/export_indexed_png_sequence.py \
  --build-report pixel-build.json \
  --audit-report pixel-audit.json \
  --output-dir indexed-output \
  --report indexed-output-report.json
```

This backend is distributable with SpriteFlux and requires no Aseprite installation.

## Optional Aseprite export

Require a passing `audit_shared_palette_pixel_sequence.py` report, then run:

```text
python scripts/export_aseprite_indexed_sequence.py \
  --build-report pixel-build.json \
  --audit-report pixel-audit.json \
  --aseprite /path/to/aseprite \
  --output-dir indexed-output \
  --report indexed-output-report.json \
  --art-fps 24
```

The adapter writes:

- `beauty/frame-####.png`: true Indexed PNGs;
- `sequence.aseprite`: editable animation with the same shared palette;
- `shared-palette.gpl`: fixed palette with transparent index 0;
- a report proving frame count, canvas, palette equality, exact alpha, exact RGBA round-trip, compressed bytes, decoded memory, Aseprite version/hash, and licensing boundary.

Fail closed if Aseprite is missing, the source audit failed, any PNG is not Indexed, index 0 is not transparent, palettes differ by frame, alpha changes, or the Indexed round-trip changes approved RGBA pixels. Never silently use a different backend while labelling the output Aseprite.

Godot may decode Indexed PNG into GPU RGBA textures; Indexed encoding reduces disk/package size and improves authoring discipline, not decoded texture memory.
