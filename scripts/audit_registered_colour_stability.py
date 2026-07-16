#!/usr/bin/env python3
"""Fail closed on tiny, temporally unsupported near-black islands in registered RGBA loops."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def _components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    seen=np.zeros(mask.shape,dtype=bool); found=[]
    for sy,sx in zip(*np.nonzero(mask & ~seen)):
        queue=deque([(int(sy),int(sx))]); seen[sy,sx]=True; item=[]
        while queue:
            y,x=queue.popleft(); item.append((y,x))
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    ny,nx=y+dy,x+dx
                    if (dy or dx) and 0<=ny<mask.shape[0] and 0<=nx<mask.shape[1] and mask[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx]=True; queue.append((ny,nx))
        found.append(item)
    return found


def audit(report_path: Path,action_id: str,dark_max: int,spatial_delta: int,max_component: int,radius: int,output: Path) -> dict:
    source=json.loads(report_path.read_text(encoding="utf-8")); matches=[a for a in source.get("actions",[]) if a.get("actionId")==action_id]
    if len(matches)!=1: raise ValueError("action id missing or ambiguous")
    items=matches[0].get("runtimeFrames",[]); arrays=[np.asarray(Image.open(i["file"]).convert("RGBA")) for i in items]
    if len(arrays)<3: raise ValueError("cyclic audit requires at least three frames")
    records=[]; total=0
    for index,array in enumerate(arrays):
        rgb=array[:,:,:3].astype(np.int16); alpha=array[:,:,3]>=128; value=rgb.max(axis=2)
        core=alpha.copy(); pad_alpha=np.pad(alpha,1,constant_values=False)
        for y in range(3):
            for x in range(3): core &= pad_alpha[y:y+alpha.shape[0],x:x+alpha.shape[1]]
        pad=np.pad(value,1,mode="edge"); neighbours=np.stack([pad[y:y+value.shape[0],x:x+value.shape[1]] for y in range(3) for x in range(3) if (y,x)!=(1,1)])
        local=np.median(neighbours,axis=0); candidate=core & (value<=dark_max) & (local-value>=spatial_delta)
        temporal=[]
        for other in (arrays[(index-1)%len(arrays)],arrays[(index+1)%len(arrays)]): temporal.append((other[:,:,:3].max(axis=2)<=dark_max)&(other[:,:,3]>=128))
        components=[]
        for component in _components(candidate):
            if len(component)>max_component: continue
            supported=False
            for y,x in component:
                y0,y1=max(0,y-radius),min(alpha.shape[0],y+radius+1); x0,x1=max(0,x-radius),min(alpha.shape[1],x+radius+1)
                if any(np.any(mask[y0:y1,x0:x1]) for mask in temporal): supported=True; break
            if supported: continue
            ys=[p[0] for p in component]; xs=[p[1] for p in component]
            components.append({"pixels":len(component),"bbox":[min(xs),min(ys),max(xs)+1,max(ys)+1],"darkestValue":int(min(value[y,x] for y,x in component))})
        count=sum(c["pixels"] for c in components); total+=count
        records.append({"sourceIndex":items[index]["sourceIndex"],"pts":items[index]["pts"],"unsupportedNearBlackPixels":count,"components":components})
    result={"schemaVersion":1,"registrationReport":str(report_path),"actionId":action_id,"policy":{"cyclic":True,"erodedOpaqueCore":True,"darkMax":dark_max,"spatialDelta":spatial_delta,"maxComponentPixels":max_component,"temporalMotionRadius":radius},"frameCount":len(items),"totalUnsupportedNearBlackPixels":total,"frames":records,"qa":{"status":"pass" if total==0 else "failed_unsupported_near_black_flicker","sourcePixelsChanged":False}}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); frames=[]
        for index in range(3):
            a=np.zeros((24,24,4),dtype=np.uint8); a[3:21,3:21]=(100,80,70,255)
            if index==1:a[12,12,:3]=2
            p=root/f"f{index}.png"; Image.fromarray(a,"RGBA").save(p); frames.append({"file":str(p),"sourceIndex":index,"pts":index*512})
        source=root/"registration.json"; source.write_text(json.dumps({"actions":[{"actionId":"idle","runtimeFrames":frames}]}),encoding="utf-8")
        result=audit(source,"idle",10,30,4,1,root/"audit.json"); assert result["totalUnsupportedNearBlackPixels"]==1
        frames[0]["file"]=frames[1]["file"]; frames[2]["file"]=frames[1]["file"]; source.write_text(json.dumps({"actions":[{"actionId":"idle","runtimeFrames":frames}]}),encoding="utf-8")
        stable=audit(source,"idle",10,30,4,1,root/"stable.json"); assert stable["totalUnsupportedNearBlackPixels"]==0
    print("audit_registered_colour_stability self-test: ok")


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--registration-report",type=Path); p.add_argument("--action-id"); p.add_argument("--dark-max",type=int,default=48); p.add_argument("--spatial-delta",type=int,default=28); p.add_argument("--max-component-pixels",type=int,default=4); p.add_argument("--temporal-motion-radius",type=int,default=2); p.add_argument("--output",type=Path); p.add_argument("--self-test",action="store_true"); a=p.parse_args()
    if a.self_test:self_test();return
    if None in (a.registration_report,a.action_id,a.output):p.error("registration report, action id and output are required")
    result=audit(a.registration_report,a.action_id,a.dark_max,a.spatial_delta,a.max_component_pixels,a.temporal_motion_radius,a.output); print(json.dumps({"ok":result["qa"]["status"]=="pass","status":result["qa"]["status"],"totalUnsupportedNearBlackPixels":result["totalUnsupportedNearBlackPixels"]},indent=2))
    if result["qa"]["status"]!="pass":raise SystemExit(2)


if __name__=="__main__":main()
