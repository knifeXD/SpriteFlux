#!/usr/bin/env python3
"""Audit keyed RGBA topology, temporal alpha stability, and cyclic seam candidates."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def _components(mask: np.ndarray) -> list[int]:
    visited = np.zeros(mask.shape, dtype=bool); sizes: list[int] = []
    height, width = mask.shape
    for sy, sx in np.argwhere(mask & ~visited):
        if visited[sy, sx]: continue
        queue = deque([(int(sy), int(sx))]); visited[sy, sx] = True; size = 0
        while queue:
            y, x = queue.popleft(); size += 1
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    if not (dy or dx): continue
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny,nx] and not visited[ny,nx]:
                        visited[ny,nx] = True; queue.append((ny,nx))
        sizes.append(size)
    return sorted(sizes, reverse=True)


def _border_connected(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape; connected = np.zeros(mask.shape, dtype=bool); queue = deque()
    for y, x in [(0,x) for x in range(width)] + [(height-1,x) for x in range(width)] + [(y,0) for y in range(height)] + [(y,width-1) for y in range(height)]:
        if mask[y,x] and not connected[y,x]: connected[y,x] = True; queue.append((y,x))
    while queue:
        y,x=queue.popleft()
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                if not (dy or dx): continue
                ny,nx=y+dy,x+dx
                if 0<=ny<height and 0<=nx<width and mask[ny,nx] and not connected[ny,nx]:
                    connected[ny,nx]=True; queue.append((ny,nx))
    return connected


def _pair(a: np.ndarray, b: np.ndarray) -> dict:
    am=a[:,:,3]>=128; bm=b[:,:,3]>=128; union=am|bm; intersection=am&bm
    union_count=int(union.sum()); iou=float(intersection.sum()/union_count) if union_count else 1.0
    xor_ratio=float((am^bm).sum()/union_count) if union_count else 0.0
    ap=a.astype(np.float32); bp=b.astype(np.float32)
    ap[:,:,:3] *= ap[:,:,3:4]/255.0; bp[:,:,:3] *= bp[:,:,3:4]/255.0
    rgba_mae=float(np.abs(ap-bp)[union].mean()/255.0) if union_count else 0.0
    return {"alphaIou":round(iou,6),"alphaXorRatio":round(xor_ratio,6),"premultipliedRgbaMae":round(rgba_mae,6),
            "seamScore":round((1.0-iou)*0.65+rgba_mae*0.35,6)}


def audit(key_report: dict, min_loop_frames: int, max_area_delta_ratio: float, min_adjacent_iou: float,
          min_largest_component_ratio: float) -> dict:
    items=key_report.get("frames",[])
    if len(items)<min_loop_frames: raise ValueError("not enough keyed frames for declared minimum loop")
    arrays=[]; frames=[]; areas=[]
    for item in items:
        path=Path(item["file"])
        if not path.is_file(): raise ValueError(f"keyed frame missing: {path}")
        rgba=np.asarray(Image.open(path).convert("RGBA")); arrays.append(rgba); mask=rgba[:,:,3]>=128
        area=int(mask.sum()); areas.append(area); comps=_components(mask); transparent=~mask
        holes=int(np.count_nonzero(transparent & ~_border_connected(transparent)))
        frames.append({"sourceIndex":item["sourceIndex"],"pts":item["pts"],"sourceTime":item["sourceTime"],
                       "foregroundArea":area,"componentCount":len(comps),"largestComponentPixels":comps[0] if comps else 0,
                       "largestComponentRatio":round((comps[0]/area) if area else 0.0,6),
                       "smallComponentsAtMost4Pixels":sum(1 for size in comps[1:] if size<=4),
                       "enclosedTransparentPixels":holes})
    adjacent=[dict({"fromSourceIndex":items[i-1]["sourceIndex"],"toSourceIndex":items[i]["sourceIndex"]},**_pair(arrays[i-1],arrays[i])) for i in range(1,len(items))]
    area_deltas=[abs(b-a)/max(a,b) for a,b in zip(areas,areas[1:])]
    candidates=[]
    for start in range(len(items)):
        for end in range(start+min_loop_frames-1,len(items)):
            pair=_pair(arrays[end],arrays[start]); motion=float(np.mean([x["alphaXorRatio"] for x in adjacent[start:end]])) if end>start else 0.0
            candidates.append(dict({"startSourceIndex":items[start]["sourceIndex"],"endSourceIndexInclusive":items[end]["sourceIndex"],
                                    "frameCount":end-start+1,"startTime":items[start]["sourceTime"],"endTime":items[end]["sourceTime"],
                                    "meanInternalAlphaMotion":round(motion,6)},**pair))
    candidates.sort(key=lambda value:(value["seamScore"],-value["meanInternalAlphaMotion"],-value["frameCount"]))
    errors=[]
    if max(area_deltas,default=0)>max_area_delta_ratio: errors.append("adjacent_foreground_area_delta_exceeds_limit")
    if min((x["alphaIou"] for x in adjacent),default=1)<min_adjacent_iou: errors.append("adjacent_alpha_iou_below_limit")
    if min((x["largestComponentRatio"] for x in frames),default=1)<min_largest_component_ratio: errors.append("largest_component_ratio_below_limit")
    if any(x["enclosedTransparentPixels"] for x in frames): errors.append("enclosed_transparent_pixels_present")
    best=candidates[0]
    return {"schemaVersion":1,"sourceKeyReport":key_report.get("source",{}),"frameCount":len(items),
            "thresholds":{"maxAdjacentAreaDeltaRatio":max_area_delta_ratio,"minAdjacentAlphaIou":min_adjacent_iou,
                          "minLargestComponentRatio":min_largest_component_ratio,"minLoopFrames":min_loop_frames},
            "summary":{"foregroundAreaMin":min(areas),"foregroundAreaMax":max(areas),"foregroundAreaMedian":float(np.median(areas)),
                       "maxAdjacentAreaDeltaRatio":round(max(area_deltas,default=0),6),
                       "minAdjacentAlphaIou":min((x["alphaIou"] for x in adjacent),default=1.0),
                       "minLargestComponentRatio":min(x["largestComponentRatio"] for x in frames),
                       "totalEnclosedTransparentPixels":sum(x["enclosedTransparentPixels"] for x in frames)},
            "recommendedLoop":best,"loopCandidates":candidates[:10],"frames":frames,"adjacentPairs":adjacent,
            "qa":{"ok":not errors,"errors":errors,"status":"temporal_matte_pass_loop_pending_visual_qa" if not errors else "rejected"}}


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); items=[]
        for index in range(8):
            image=np.zeros((32,32,4),dtype=np.uint8); image[8:26,10+(index%2):22+(index%2),:3]=(120,60,40); image[8:26,10+(index%2):22+(index%2),3]=255
            path=root/f"f{index}.png"; Image.fromarray(image,"RGBA").save(path)
            items.append({"file":str(path),"sourceIndex":index,"pts":index*512,"sourceTime":index/24})
        result=audit({"frames":items},4,0.2,0.75,0.9)
        assert result["qa"]["ok"] and result["recommendedLoop"]["frameCount"]>=4
        diagonal=np.zeros((5,5),dtype=bool); diagonal[0,0]=True; diagonal[1,1]=True; diagonal[2,2]=True
        assert _border_connected(diagonal)[2,2]
    print("audit_keyed_sequence self-test: ok")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--key-report",type=Path); parser.add_argument("--output",type=Path)
    parser.add_argument("--min-loop-frames",type=int,default=12); parser.add_argument("--max-area-delta-ratio",type=float,default=0.08)
    parser.add_argument("--min-adjacent-iou",type=float,default=0.90); parser.add_argument("--min-largest-component-ratio",type=float,default=0.90)
    parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test: self_test(); return
    if args.key_report is None or args.output is None: parser.error("key-report and output are required")
    result=audit(json.loads(args.key_report.read_text(encoding="utf-8")),args.min_loop_frames,args.max_area_delta_ratio,
                 args.min_adjacent_iou,args.min_largest_component_ratio)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"ok":result["qa"]["ok"],"summary":result["summary"],"recommendedLoop":result["recommendedLoop"],"errors":result["qa"]["errors"]},ensure_ascii=False,indent=2))
    raise SystemExit(0 if result["qa"]["ok"] else 2)


if __name__=="__main__": main()
