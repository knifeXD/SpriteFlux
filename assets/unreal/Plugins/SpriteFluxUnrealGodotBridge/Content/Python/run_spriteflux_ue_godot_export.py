"""Unreal -ExecutePythonScript entry point for a SpriteFlux export request."""

import os
import sys

from spriteflux_ue_godot.exporter import export_request_file


def _request_path() -> str:
    environment_path = os.environ.get("SPRITEFLUX_UE_GODOT_REQUEST")
    if environment_path:
        return environment_path
    for index, value in enumerate(sys.argv):
        if value == "--request" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        if value.startswith("--request="):
            return value.split("=", 1)[1]
    raise RuntimeError("missing_request_path:set SPRITEFLUX_UE_GODOT_REQUEST")


export_request_file(_request_path())
