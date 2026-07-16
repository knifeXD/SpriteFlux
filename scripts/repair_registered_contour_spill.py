#!/usr/bin/env python3
"""Audit and repair registered narrow-band chroma spill without changing alpha."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _sha(path: Path) -> str:
    h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


def _core(mask: np.ndarray) -> np.ndarray:
    result=mask.copy(); padded=np.pad(mask,1,constant_values=False)
    for y in range(3):
        for x in range(3): result &= padded[y:y+mask.shape[0],x:x+mask.shape[1]]
    return result


def _recover(array: np.ndarray,limit: int,radius: int) -> tuple[np.ndarray,list[dict]]:
    result=array.copy(); mask=array[:,:,3]>=128; core=_core(mask); band=mask & ~core
    rgb=array[:,:,:3].astype(np.int16); excess=rgb[:,:,1]-np.maximum(rgb[:,:,0],rgb[:,:,2]); candidates=band & (excess>limit); repairs=[]
    for y,x in zip(*np.nonzero(candidates)):
        source_excess=int(excess[y,x])
        before=result[y,x,:3].copy()
        # Small positive green bias is the common post-registration fringe.  A
        # channel-only cap preserves the authored red/blue/value much better
        # than borrowing a potentially unrelated nearby costume colour.
        if source_excess <= 12:
            result[y,x,1]=np.uint8(max(int(result[y,x,0]),int(result[y,x,2]))+limit)
            repairs.append({"x":int(x),"y":int(y),"before":[int(v) for v in before],"after":[int(v) for v in result[y,x,:3]],"method":"channel_cap"})
            continue
        y0,y1=max(0,y-radius),min(mask.shape[0],y+radius+1); x0,x1=max(0,x-radius),min(mask.shape[1],x+radius+1)
        local_rgb=rgb[y0:y1,x0:x1]; local_core=core[y0:y1,x0:x1]; local_excess=local_rgb[:,:,1]-np.maximum(local_rgb[:,:,0],local_rgb[:,:,2]); valid=local_core & (local_excess<=limit)
        samples=local_rgb[valid]
        if samples.shape[0]<3:
            result[y,x,1]=np.uint8(max(int(result[y,x,0]),int(result[y,x,2]))+limit)
            repairs.append({"x":int(x),"y":int(y),"before":[int(v) for v in before],"after":[int(v) for v in result[y,x,:3]],"method":"channel_cap_fallback"})
            continue
        chroma=np.median(samples.astype(np.float32)/(np.maximum(samples.max(axis=1,keepdims=True),1)),axis=0)
        source_value=max(int(rgb[y,x].max()),1); recovered=np.rint(np.clip(chroma*source_value,0,255)).astype(np.uint8)
        if int(recovered[1])-max(int(recovered[0]),int(recovered[2]))>limit: recovered[1]=np.uint8(min(255,max(int(recovered[0]),int(recovered[2]))+limit))
        result[y,x,:3]=recovered; repairs.append({"x":int(x),"y":int(y),"before":[int(v) for v in before],"after":[int(v) for v in recovered],"method":"local_core_chroma"})
    return result,repairs


def run(registration: Path,action_id: str,output_dir: Path,report_path: Path,qa_sheet: Path,limit: int,radius: int,no_green: bool) -> dict:
    if not no_green: raise ValueError("intentional green material must be excluded semantically or use another key colour")
    source=json.loads(registration.read_text(encoding="utf-8")); matches=[a for a in source.get("actions",[]) if a.get("actionId")==action_id]
    if len(matches)!=1: raise ValueError("action id missing or ambiguous")
    output_dir.mkdir(parents=True,exist_ok=False); frames=[]; total_before=0; total_after=0; total_changed=0; alpha_changed=0; previews=[]
    for index,item in enumerate(matches[0].get("runtimeFrames",[])):
        image=Image.open(item["file"]).convert("RGBA"); array=np.asarray(image).copy(); original_alpha=array[:,:,3].copy(); mask=original_alpha>=128; band=mask & ~_core(mask); rgb=array[:,:,:3].astype(np.int16); before=int(np.count_nonzero(band & ((rgb[:,:,1]-np.maximum(rgb[:,:,0],rgb[:,:,2]))>limit)))
        repaired,changes=_recover(array,limit,radius); rr=repaired[:,:,:3].astype(np.int16); after=int(np.count_nonzero(band & ((rr[:,:,1]-np.maximum(rr[:,:,0],rr[:,:,2]))>limit)))
        output=output_dir/f"frame-{index:04d}.png"; Image.fromarray(repaired,"RGBA").save(output,optimize=True)
        alpha_delta=int(np.count_nonzero(repaired[:,:,3]!=original_alpha)); alpha_changed+=alpha_delta; total_before+=before; total_after+=after; total_changed+=len(changes)
        frames.append({**item,"file":str(output),"sha256":_sha(output),"contourGreenExcessPixelsBefore":before,"contourGreenExcessPixelsAfter":after,"repairedContourPixels":len(changes),"alphaPixelsChanged":alpha_delta})
        if index in (0,len(matches[0]["runtimeFrames"])//2,len(matches[0]["runtimeFrames"])-1): previews.append(Image.fromarray(repaired,"RGBA"))
    width,height=previews[0].size; sheet=Image.new("RGBA",(width*3,height+24),(28,29,33,255)); draw=ImageDraw.Draw(sheet)
    for i,image in enumerate(previews): sheet.alpha_composite(image,(i*width,24)); draw.text((i*width+6,6),f"sample {i+1}",fill="white")
    qa_sheet.parent.mkdir(parents=True,exist_ok=True); sheet.convert("RGB").save(qa_sheet,optimize=True)
    result={"schemaVersion":1,"source":{"registrationReport":str(registration),"videoSha256":source.get("source",{}).get("videoSha256")},"canonical":source.get("canonical",{}),"policy":{"contourBandNativePixels":1,"greenExcessLimit":limit,"interiorSearchRadius":radius,"requiresNoIntentionalGreenMaterial":True,"recovery":"small fringe uses green-channel cap; strong spill uses nearby clean eroded-core median chroma; missing local support falls back to channel cap","alphaPreserved":True},"actions":[{"actionId":action_id,"phase":matches[0].get("phase"),"sharedTransform":matches[0].get("sharedTransform"),"runtimeFrames":frames}],"summary":{"greenExcessPixelsBefore":total_before,"greenExcessPixelsAfter":total_after,"repairedContourPixels":total_changed,"alphaPixelsChanged":alpha_changed},"qa":{"status":"pass" if total_after==0 and alpha_changed==0 else "failed_contour_spill","sourceSilhouetteChanged":alpha_changed>0},"qaSheet":str(qa_sheet)}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); a=np.zeros((16,16,4),dtype=np.uint8); a[3:13,3:13]=(90,70,80,255); a[3,8,:3]=(20,120,30)
        p=root/"f.png"; Image.fromarray(a,"RGBA").save(p); canonical={"canvas":[16,16],"root":[8,13],"baselineY":13}
        registration=root/"reg.json"; registration.write_text(json.dumps({"source":{"videoSha256":"abc"},"canonical":canonical,"actions":[{"actionId":"idle","phase":"loop","sharedTransform":{"requestedScale":1},"runtimeFrames":[{"file":str(p),"sourceIndex":0,"pts":0,"sourceTime":0.0}]}]}),encoding="utf-8")
        result=run(registration,"idle",root/"out",root/"report.json",root/"qa.png",6,4,True); assert result["summary"]=={"greenExcessPixelsBefore":1,"greenExcessPixelsAfter":0,"repairedContourPixels":1,"alphaPixelsChanged":0}
    print("repair_registered_contour_spill self-test: ok")


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--registration-report",type=Path); p.add_argument("--action-id"); p.add_argument("--output-dir",type=Path); p.add_argument("--report",type=Path); p.add_argument("--qa-sheet",type=Path); p.add_argument("--green-excess-limit",type=int,default=6); p.add_argument("--interior-search-radius",type=int,default=4); p.add_argument("--no-intentional-green-material",action="store_true"); p.add_argument("--self-test",action="store_true"); a=p.parse_args()
    if a.self_test:self_test();return
    if None in (a.registration_report,a.action_id,a.output_dir,a.report,a.qa_sheet):p.error("all paths and action id are required")
    try:r=run(a.registration_report,a.action_id,a.output_dir,a.report,a.qa_sheet,a.green_excess_limit,a.interior_search_radius,a.no_intentional_green_material)
    except (ValueError,KeyError,OSError) as e:print(json.dumps({"ok":False,"error":str(e)}));raise SystemExit(2)
    print(json.dumps({"ok":r["qa"]["status"]=="pass",**r["summary"]},indent=2)); raise SystemExit(0 if r["qa"]["status"]=="pass" else 2)


if __name__=="__main__":main()
