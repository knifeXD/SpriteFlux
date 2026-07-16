#!/usr/bin/env python3
"""Render an unmodified RGBA loop window as checker GIF plus seam evidence."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw


def _checker(size: tuple[int,int], tile: int=16) -> Image.Image:
    width,height=size; array=np.empty((height,width,3),dtype=np.uint8)
    yy,xx=np.indices((height,width)); select=((xx//tile+yy//tile)%2)==0
    array[select]=(72,74,78); array[~select]=(132,134,138)
    return Image.fromarray(array,"RGB")


def _composite(rgba: Image.Image) -> Image.Image:
    return Image.alpha_composite(_checker(rgba.size).convert("RGBA"),rgba).convert("RGB")


def _pair(a: Image.Image,b: Image.Image) -> dict:
    aa=np.asarray(a.convert("RGBA")); bb=np.asarray(b.convert("RGBA")); am=aa[:,:,3]>=128; bm=bb[:,:,3]>=128
    union=am|bm; count=int(union.sum()); iou=float((am&bm).sum()/count) if count else 1.0
    ap=aa.astype(np.float32); bp=bb.astype(np.float32); ap[:,:,:3]*=ap[:,:,3:4]/255; bp[:,:,:3]*=bp[:,:,3:4]/255
    mae=float(np.abs(ap-bp)[union].mean()/255) if count else 0.0
    return {"alphaIou":round(iou,6),"premultipliedRgbaMae":round(mae,6)}


def render(frame_report: Path,start: int,end: int,fps: float,gif: Path,seam: Path,report: Path,action_id: str|None=None) -> dict:
    source=json.loads(frame_report.read_text(encoding="utf-8")); items=source.get("frames",[])
    if action_id is not None:
        matches=[action for action in source.get("actions",[]) if action.get("actionId")==action_id]
        if len(matches)!=1: raise ValueError("action id missing or ambiguous in registration report")
        items=matches[0].get("runtimeFrames",[])
    items=[item for item in items if start<=int(item["sourceIndex"])<=end]
    if [int(item["sourceIndex"]) for item in items] != list(range(start,end+1)): raise ValueError("loop indices missing, duplicated, or unordered")
    if fps<=0: raise ValueError("fps must be positive")
    rgba=[Image.open(item["file"]).convert("RGBA") for item in items]
    if len({image.size for image in rgba})!=1: raise ValueError("loop frames do not share one canvas")
    previews=[_composite(image) for image in rgba]; duration=max(1,round(1000/fps)); gif.parent.mkdir(parents=True,exist_ok=True)
    previews[0].save(gif,save_all=True,append_images=previews[1:],duration=duration,loop=0,optimize=False,disposal=2)
    first,last=previews[0],previews[-1]; diff=ImageChops.difference(first,last); width,height=first.size
    sheet=Image.new("RGB",(width*3,height+28),(24,25,28)); sheet.paste(first,(0,28)); sheet.paste(last,(width,28)); sheet.paste(diff,(width*2,28))
    draw=ImageDraw.Draw(sheet); draw.text((8,8),f"first source {start}",fill="white"); draw.text((width+8,8),f"last source {end}",fill="white"); draw.text((width*2+8,8),"absolute RGB difference",fill="white")
    seam.parent.mkdir(parents=True,exist_ok=True); sheet.save(seam,optimize=True)
    metric=_pair(rgba[-1],rgba[0]); result={"schemaVersion":1,"sourceFrameReport":str(frame_report),"actionId":action_id,"loop":{"startSourceIndex":start,"endSourceIndexInclusive":end,"frameCount":len(items),"fps":fps,"frameDurationMs":duration,"cycleDurationSeconds":round(len(items)/fps,6),"indices":[int(item["sourceIndex"]) for item in items],"pts":[int(item["pts"]) for item in items]},"seam":metric,"artifacts":{"checkerGif":str(gif),"seamSheet":str(seam)},"qa":{"status":"preview_rendered_pending_visual_rhythm_review","sourcePixelsChanged":False,"resamplingUsed":False}}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root=Path(raw); items=[]
        for index in range(4):
            image=np.zeros((24,24,4),dtype=np.uint8); image[6:20,8+(index%2):16+(index%2)]=(130,70,40,255)
            path=root/f"f{index}.png"; Image.fromarray(image,"RGBA").save(path); items.append({"file":str(path),"sourceIndex":index,"pts":index*512})
        frame_report=root/"frames.json"; frame_report.write_text(json.dumps({"frames":items}),encoding="utf-8")
        result=render(frame_report,0,3,12,root/"loop.gif",root/"seam.png",root/"report.json")
        assert result["loop"]["frameCount"]==4 and (root/"loop.gif").is_file() and (root/"seam.png").is_file()
        registration=root/"registration.json"; registration.write_text(json.dumps({"actions":[{"actionId":"idle","runtimeFrames":items}]}),encoding="utf-8")
        registered=render(registration,0,3,12,root/"loop2.gif",root/"seam2.png",root/"report2.json","idle")
        assert registered["actionId"]=="idle" and registered["loop"]["frameCount"]==4
    print("render_loop_preview self-test: ok")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--frame-report",type=Path); parser.add_argument("--action-id"); parser.add_argument("--start-source-index",type=int); parser.add_argument("--end-source-index-inclusive",type=int); parser.add_argument("--fps",type=float,default=24); parser.add_argument("--gif",type=Path); parser.add_argument("--seam-sheet",type=Path); parser.add_argument("--report",type=Path); parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test:self_test();return
    if None in (args.frame_report,args.start_source_index,args.end_source_index_inclusive,args.gif,args.seam_sheet,args.report): parser.error("frame report, loop window, gif, seam sheet and report are required")
    result=render(args.frame_report,args.start_source_index,args.end_source_index_inclusive,args.fps,args.gif,args.seam_sheet,args.report,args.action_id); print(json.dumps({"ok":True,"loop":result["loop"],"seam":result["seam"],"artifacts":result["artifacts"]},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
