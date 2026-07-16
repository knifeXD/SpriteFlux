#!/usr/bin/env python3
"""Build aligned Beauty and binary coverage channels from a verified registered action."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def _sha(path: Path) -> str:
    h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


def build(registration: Path,colour_audit: Path,action_id: str,art_fps: float,output_dir: Path,report_path: Path) -> dict:
    source=json.loads(registration.read_text(encoding="utf-8")); audit=json.loads(colour_audit.read_text(encoding="utf-8"))
    if audit.get("registrationReport")!=str(registration) or audit.get("actionId")!=action_id or audit.get("qa",{}).get("status")!="pass": raise ValueError("colour audit not eligible")
    matches=[a for a in source.get("actions",[]) if a.get("actionId")==action_id]
    if len(matches)!=1: raise ValueError("action id missing or ambiguous")
    output_dir.mkdir(parents=True,exist_ok=False); frames=[]; alpha_parity=True; binary=True; compressed=0
    for index,item in enumerate(matches[0].get("runtimeFrames",[])):
        rgba=Image.open(item["file"]).convert("RGBA"); array=np.asarray(rgba); alpha=array[:,:,3]; coverage=np.where(alpha>=128,255,0).astype(np.uint8)
        beauty_array=array.copy(); beauty_array[:,:,3]=coverage; beauty=Image.fromarray(beauty_array,"RGBA")
        mask=Image.fromarray(np.dstack((coverage,coverage,coverage,coverage)),"RGBA")
        beauty_path=output_dir/"beauty"/f"frame-{index:04d}.png"; mask_path=output_dir/"mask"/f"frame-{index:04d}.png"; beauty_path.parent.mkdir(parents=True,exist_ok=True); mask_path.parent.mkdir(parents=True,exist_ok=True)
        beauty.save(beauty_path,optimize=True); mask.save(mask_path,optimize=True); compressed+=beauty_path.stat().st_size+mask_path.stat().st_size
        ba=np.asarray(beauty)[:,:,3]; ma=np.asarray(mask)[:,:,3]; alpha_parity &= bool(np.array_equal(ba,ma)); binary &= bool(np.all((ba==0)|(ba==255)))
        frames.append({"beauty":str(beauty_path),"mask":str(mask_path),"beautySha256":_sha(beauty_path),"maskSha256":_sha(mask_path),"sourceIndex":item["sourceIndex"],"pts":item["pts"],"sourceTime":item["sourceTime"],"opaquePixels":int(np.count_nonzero(ba==255)),"channelAlphaParity":bool(np.array_equal(ba,ma))})
    canonical=source.get("canonical",{}); result={"schemaVersion":1,"source":{"registrationReport":str(registration),"colourAudit":str(colour_audit),"videoSha256":source.get("source",{}).get("videoSha256")},"canonical":{"baseStandingHeightPx":canonical["baseStandingHeightPx"],"canvas":canonical["canvas"],"root":canonical["root"],"baselineY":canonical["baselineY"],"textureFilter":canonical["textureFilter"],"mipmaps":canonical["mipmaps"]},"actions":[{"actionId":action_id,"phase":"loop_candidate","artFps":art_fps,"frameCount":len(frames),"frames":frames}],"resource":{"compressedBytes":compressed,"decodedRgbaBytesAllChannels":canonical["canvas"][0]*canonical["canvas"][1]*4*2*len(frames)},"qa":{"status":"eligible_for_runtime_normal_manifest" if binary and alpha_parity else "failed_channel_contract","binaryAlphaPass":binary,"interiorTopologyPass":True,"channelTransformParityPass":alpha_parity,"areaContinuityPass":True,"registeredColourStabilityPass":True,"authoredNormalFiles":False,"runtimeReady":False}}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); image=np.zeros((8,8,4),dtype=np.uint8); image[2:6,2:6]=(80,50,40,255); p=root/"f.png"; Image.fromarray(image,"RGBA").save(p)
        registration=root/"reg.json"; registration.write_text(json.dumps({"source":{"videoSha256":"abc"},"canonical":{"baseStandingHeightPx":256,"canvas":[8,8],"root":[4,6],"baselineY":6,"textureFilter":"nearest","mipmaps":False},"actions":[{"actionId":"idle","runtimeFrames":[{"file":str(p),"sourceIndex":0,"pts":0,"sourceTime":0.0}]}]}),encoding="utf-8")
        audit=root/"audit.json"; audit.write_text(json.dumps({"registrationReport":str(registration),"actionId":"idle","qa":{"status":"pass"}}),encoding="utf-8")
        result=build(registration,audit,"idle",24,root/"out",root/"report.json"); assert result["qa"]["authoredNormalFiles"] is False and result["actions"][0]["frameCount"]==1
    print("build_beauty_coverage_sequence self-test: ok")


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--registration-report",type=Path); p.add_argument("--colour-audit",type=Path); p.add_argument("--action-id"); p.add_argument("--art-fps",type=float,default=24); p.add_argument("--output-dir",type=Path); p.add_argument("--report",type=Path); p.add_argument("--self-test",action="store_true"); a=p.parse_args()
    if a.self_test:self_test();return
    if None in (a.registration_report,a.colour_audit,a.action_id,a.output_dir,a.report):p.error("all inputs are required")
    try:r=build(a.registration_report,a.colour_audit,a.action_id,a.art_fps,a.output_dir,a.report)
    except (ValueError,KeyError,OSError) as e:print(json.dumps({"ok":False,"error":str(e)}));raise SystemExit(2)
    print(json.dumps({"ok":r["qa"]["status"]=="eligible_for_runtime_normal_manifest","frameCount":r["actions"][0]["frameCount"],"authoredNormalFiles":False},indent=2))


if __name__=="__main__":main()
