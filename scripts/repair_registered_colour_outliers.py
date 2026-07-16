#!/usr/bin/env python3
"""Repair only fail-closed registered colour outliers listed by the audit report."""

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


def repair(registration: Path,audit_path: Path,action_id: str,output_dir: Path,report_path: Path) -> dict:
    source=json.loads(registration.read_text(encoding="utf-8")); audit=json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("registrationReport")!=str(registration) or audit.get("actionId")!=action_id: raise ValueError("audit provenance mismatch")
    matches=[a for a in source.get("actions",[]) if a.get("actionId")==action_id]
    if len(matches)!=1: raise ValueError("action id missing or ambiguous")
    flagged={int(f["sourceIndex"]):f.get("components",[]) for f in audit.get("frames",[]) if f.get("unsupportedNearBlackPixels",0)>0}
    frames=[]; total=0; alpha_changed=0; output_dir.mkdir(parents=True,exist_ok=False)
    for item in matches[0].get("runtimeFrames",[]):
        image=Image.open(item["file"]).convert("RGBA"); array=np.asarray(image).copy(); original_alpha=array[:,:,3].copy(); changes=[]
        for component in flagged.get(int(item["sourceIndex"]),[]):
            x0,y0,x1,y1=component["bbox"]
            for y in range(y0,y1):
                for x in range(x0,x1):
                    neighbours=[]
                    for dy in (-1,0,1):
                        for dx in (-1,0,1):
                            ny,nx=y+dy,x+dx
                            if (dy or dx) and 0<=ny<array.shape[0] and 0<=nx<array.shape[1] and array[ny,nx,3]>=128: neighbours.append(array[ny,nx,:3])
                    if len(neighbours)<4: raise ValueError("insufficient opaque spatial support")
                    replacement=np.median(np.stack(neighbours),axis=0).astype(np.uint8); before=array[y,x,:3].copy(); array[y,x,:3]=replacement
                    changes.append({"x":x,"y":y,"before":[int(v) for v in before],"after":[int(v) for v in replacement]})
        alpha_changed+=int(np.count_nonzero(array[:,:,3]!=original_alpha)); total+=len(changes)
        output=output_dir/f"frame-{len(frames):04d}.png"; Image.fromarray(array,"RGBA").save(output,optimize=True)
        frames.append({**item,"file":str(output),"sha256":_sha(output),"repairedColourPixels":len(changes),"repairs":changes})
    result={"schemaVersion":1,"source":{"registrationReport":str(registration),"auditReport":str(audit_path),"videoSha256":source.get("source",{}).get("videoSha256")},"canonical":source.get("canonical",{}),"actions":[{"actionId":action_id,"phase":matches[0].get("phase"),"sharedTransform":matches[0].get("sharedTransform"),"runtimeFrames":frames}],"totalRepairedColourPixels":total,"alphaPixelsChanged":alpha_changed,"policy":{"auditListedPixelsOnly":True,"replacement":"median of opaque 8-neighbour RGB","alphaPreserved":True},"qa":{"status":"repaired_pending_reaudit","sourceSilhouetteChanged":False}}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); a=np.zeros((16,16,4),dtype=np.uint8); a[2:14,2:14]=(100,80,60,255); a[8,8,:3]=2
        image=root/"f.png"; Image.fromarray(a,"RGBA").save(image)
        canonical={"canvas":[16,16],"root":[8,14],"baselineY":14}; registration=root/"registration.json"; registration.write_text(json.dumps({"source":{"videoSha256":"abc"},"canonical":canonical,"actions":[{"actionId":"idle","phase":"loop","sharedTransform":{"requestedScale":1.0},"runtimeFrames":[{"file":str(image),"sourceIndex":0,"pts":0}]}]}),encoding="utf-8")
        audit=root/"audit.json"; audit.write_text(json.dumps({"registrationReport":str(registration),"actionId":"idle","frames":[{"sourceIndex":0,"unsupportedNearBlackPixels":1,"components":[{"pixels":1,"bbox":[8,8,9,9]}]}]}),encoding="utf-8")
        result=repair(registration,audit,"idle",root/"out",root/"report.json"); assert result["totalRepairedColourPixels"]==1 and result["alphaPixelsChanged"]==0 and result["canonical"]==canonical
    print("repair_registered_colour_outliers self-test: ok")


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--registration-report",type=Path); p.add_argument("--audit-report",type=Path); p.add_argument("--action-id"); p.add_argument("--output-dir",type=Path); p.add_argument("--report",type=Path); p.add_argument("--self-test",action="store_true"); a=p.parse_args()
    if a.self_test:self_test();return
    if None in (a.registration_report,a.audit_report,a.action_id,a.output_dir,a.report):p.error("all inputs are required")
    result=repair(a.registration_report,a.audit_report,a.action_id,a.output_dir,a.report); print(json.dumps({"ok":True,"totalRepairedColourPixels":result["totalRepairedColourPixels"],"alphaPixelsChanged":result["alphaPixelsChanged"]},indent=2))


if __name__=="__main__":main()
