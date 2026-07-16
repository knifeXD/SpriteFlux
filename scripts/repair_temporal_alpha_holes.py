#!/usr/bin/env python3
"""Repair tiny enclosed one-frame alpha holes only with bidirectional temporal support."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def _border_connected(mask: np.ndarray) -> np.ndarray:
    height,width=mask.shape; connected=np.zeros(mask.shape,dtype=bool); queue=deque()
    border=[(0,x) for x in range(width)]+[(height-1,x) for x in range(width)]+[(y,0) for y in range(height)]+[(y,width-1) for y in range(height)]
    for y,x in border:
        if mask[y,x] and not connected[y,x]: connected[y,x]=True; queue.append((y,x))
    while queue:
        y,x=queue.popleft()
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                if not (dy or dx): continue
                ny,nx=y+dy,x+dx
                if 0<=ny<height and 0<=nx<width and mask[ny,nx] and not connected[ny,nx]:
                    connected[ny,nx]=True; queue.append((ny,nx))
    return connected


def _components(mask: np.ndarray) -> list[list[tuple[int,int]]]:
    height,width=mask.shape; seen=np.zeros(mask.shape,dtype=bool); result=[]
    for sy,sx in np.argwhere(mask & ~seen):
        if seen[sy,sx]: continue
        comp=[]; queue=deque([(int(sy),int(sx))]); seen[sy,sx]=True
        while queue:
            y,x=queue.popleft(); comp.append((y,x))
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    if not (dy or dx): continue
                    ny,nx=y+dy,x+dx
                    if 0<=ny<height and 0<=nx<width and mask[ny,nx] and not seen[ny,nx]:
                        seen[ny,nx]=True; queue.append((ny,nx))
        result.append(comp)
    return result


def repair_frame(previous: np.ndarray, current: np.ndarray, following: np.ndarray, max_pixels: int) -> tuple[np.ndarray,list[dict]]:
    transparent=current[:,:,3]<128; enclosed=transparent & ~_border_connected(transparent); result=current.copy(); repairs=[]
    for component in _components(enclosed):
        if len(component)>max_pixels: continue
        ys=np.array([p[0] for p in component]); xs=np.array([p[1] for p in component])
        if not (np.all(previous[ys,xs,3]>=128) and np.all(following[ys,xs,3]>=128)): continue
        prev=previous[ys,xs].astype(np.float32); foll=following[ys,xs].astype(np.float32)
        prev_rgb=prev[:,:3]*(prev[:,3:4]/255.0); foll_rgb=foll[:,:3]*(foll[:,3:4]/255.0)
        alpha=np.minimum(prev[:,3],foll[:,3]); premul=(prev_rgb+foll_rgb)*0.5
        rgb=np.where(alpha[:,None]>0,premul/np.maximum(alpha[:,None]/255.0,1e-6),0)
        result[ys,xs,:3]=np.clip(np.rint(rgb),0,255).astype(np.uint8); result[ys,xs,3]=np.clip(np.rint(alpha),128,255).astype(np.uint8)
        repairs.append({"pixels":len(component),"bbox":[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]})
    return result,repairs


def run(key_report: Path, output_dir: Path, report_path: Path, max_pixels: int) -> dict:
    source=json.loads(key_report.read_text(encoding="utf-8")); items=source.get("frames",[])
    if len(items)<3: raise ValueError("at least three keyed frames are required")
    arrays=[np.asarray(Image.open(item["file"]).convert("RGBA")) for item in items]; output_dir.mkdir(parents=True,exist_ok=True)
    outputs=[]; total=0
    for index,(item,array) in enumerate(zip(items,arrays)):
        repaired=array.copy(); repairs=[]
        if 0<index<len(items)-1: repaired,repairs=repair_frame(arrays[index-1],array,arrays[index+1],max_pixels)
        output=output_dir/f"frame-{index+1:06d}.png"; Image.fromarray(repaired,"RGBA").save(output,optimize=True)
        changed=int(np.count_nonzero(np.any(repaired!=array,axis=2))); expected=sum(entry["pixels"] for entry in repairs)
        if changed!=expected: raise ValueError("repair changed pixels outside declared components")
        total+=changed; outputs.append({"file":str(output),"sha256":_sha(output),"sourceIndex":item["sourceIndex"],"pts":item["pts"],"sourceTime":item["sourceTime"],"changedPixels":changed,"repairs":repairs})
    report={"schemaVersion":1,"sourceKeyReport":str(key_report),"source":source.get("source"),"policy":{"maxComponentPixels":max_pixels,"requiresPreviousOpaque":True,"requiresFollowingOpaque":True,"connectivity":8,"colourRecovery":"mean bidirectional premultiplied RGBA"},"frameCount":len(outputs),"totalChangedPixels":total,"frames":outputs,"qa":{"status":"repaired_pending_full_temporal_reaudit","changesLimitedToDeclaredComponents":True}}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return report


def self_test() -> None:
    base=np.zeros((16,16,4),dtype=np.uint8); base[3:13,4:12]=(120,60,40,255); current=base.copy(); current[7:9,7:9]=0
    repaired,items=repair_frame(base,current,base,4); assert len(items)==1 and items[0]["pixels"]==4 and np.all(repaired[7:9,7:9,3]==255)
    unsupported=current.copy(); previous=base.copy(); previous[7,7]=0
    repaired2,items2=repair_frame(previous,unsupported,base,4); assert items2==[] and repaired2[7,7,3]==0
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); frames=[]
        for index,image in enumerate((base,current,base)):
            path=root/f"f{index}.png"; Image.fromarray(image,"RGBA").save(path)
            frames.append({"file":str(path),"sourceIndex":index,"pts":index*512,"sourceTime":index/24})
        key_report=root/"key.json"; provenance={"videoSha256":"abc123","video":"source.mp4"}
        key_report.write_text(json.dumps({"source":provenance,"frames":frames}),encoding="utf-8")
        report=run(key_report,root/"out",root/"report.json",4)
        assert report["source"]==provenance and report["totalChangedPixels"]==4
    print("repair_temporal_alpha_holes self-test: ok")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--key-report",type=Path); parser.add_argument("--output-dir",type=Path); parser.add_argument("--report",type=Path); parser.add_argument("--max-component-pixels",type=int,default=24); parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test:self_test();return
    if None in (args.key_report,args.output_dir,args.report):parser.error("key-report, output-dir and report are required")
    result=run(args.key_report,args.output_dir,args.report,args.max_component_pixels); print(json.dumps({"ok":True,"frameCount":result["frameCount"],"totalChangedPixels":result["totalChangedPixels"]},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
