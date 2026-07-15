#!/usr/bin/env python3
"""Render a standalone HTML dashboard from an action envelope report and optional cost data."""

from __future__ import annotations

import argparse
import html
import json
import tempfile
from pathlib import Path


def render(report: dict, costs: dict | None = None) -> str:
    actions = report.get("actions", [])
    canvas = report.get("canvas", [128, 128])
    rows = []
    diagrams = []
    for action in actions:
        name = str(action.get("name", "unnamed"))
        required = action.get("requiredFinalCanvas", [0, 0])
        source = action.get("requiredSourceCell", [0, 0])
        fits = bool(action.get("fitsCanonicalCanvas", False))
        roots = action.get("roots", [])
        status = "适配" if fits else "需要扩画布"
        rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{required[0]}×{required[1]}</td>"
            f"<td>{source[0]}×{source[1]}</td><td><span class='pill {'ok' if fits else 'warn'}'>{status}</span></td>"
            f"<td>{'循环' if action.get('loop') else 'Idle→动作→Idle'}</td></tr>"
        )
        if roots:
            xs = [float(p[0]) for p in roots]
            ys = [float(p[1]) for p in roots]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            span_x = max(1.0, max_x - min_x)
            span_y = max(1.0, max_y - min_y)
            points = " ".join(
                f"{20 + (x-min_x)/span_x*240:.1f},{75 + (y-min_y)/span_y*70:.1f}" for x, y in zip(xs, ys)
            )
            circles = "".join(
                f"<circle cx='{20 + (x-min_x)/span_x*240:.1f}' cy='{75 + (y-min_y)/span_y*70:.1f}' r='4'/>"
                for x, y in zip(xs, ys)
            )
        else:
            points, circles = "20,110 260,110", ""
        diagrams.append(
            f"<article><h3>{html.escape(name)}</h3><svg viewBox='0 0 280 170'>"
            f"<rect x='10' y='16' width='260' height='140'/><line x1='10' y1='145' x2='270' y2='145'/>"
            f"<polyline points='{points}'/>{circles}</svg>"
            f"<p>画布 {required[0]}×{required[1]} · 源格 {source[0]}×{source[1]}</p></article>"
        )
    cost_cards = ""
    if costs:
        qualities = costs.get("qualities", costs)
        cards = []
        for name, value in qualities.items():
            if not isinstance(value, dict):
                continue
            tokens = value.get("tokens", value.get("totalTokens", "–"))
            rmb = value.get("rmb", value.get("estimatedRmb", "–"))
            accepted = value.get("readableDistinctActions", value.get("acceptedActions", "–"))
            unit = value.get("rmbPerReadableAction", "–")
            cards.append(
                f"<div class='cost'><b>{html.escape(str(name))}</b><span>{tokens} tokens</span>"
                f"<span>¥{rmb}</span><span>{accepted} 可读动作</span><span>¥{unit}/动作</span></div>"
            )
        cost_cards = "<section class='costs'>" + "".join(cards) + "</section>"
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>动作生成规划仪表板</title>
<style>
:root{{--bg:#0b1220;--panel:#121d30;--line:#2b4263;--text:#edf4ff;--muted:#9cb0c9;--cyan:#58ddd1;--gold:#ffc857;--red:#ff7b72}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:32px}}h1{{margin:0}}.meta{{color:var(--muted);margin:6px 0 24px}}
.costs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0}}
.cost,article{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}}.cost span{{display:block;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border-radius:12px;overflow:hidden}}th,td{{padding:11px;border-bottom:1px solid var(--line);text-align:left}}
.pill{{padding:3px 8px;border-radius:999px}}.ok{{background:#153d3a;color:var(--cyan)}}.warn{{background:#4c3218;color:var(--gold)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:20px}}article h3,article p{{margin:0}}svg{{width:100%;margin-top:8px}}
svg rect{{fill:#0d1727;stroke:var(--line)}}svg line{{stroke:#60799b}}svg polyline{{fill:none;stroke:var(--cyan);stroke-width:3}}svg circle{{fill:var(--gold)}}
</style></head><body><main><h1>动作生成规划仪表板</h1><p class='meta'>目标画布 {canvas[0]}×{canvas[1]} · {len(actions)} 个动作 · 离线报告，不含密钥或付费调用</p>
{cost_cards}<table><thead><tr><th>动作</th><th>所需画布</th><th>所需源格</th><th>画布结论</th><th>端点规范</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<section class='grid'>{''.join(diagrams)}</section></main></body></html>"""


def self_test() -> None:
    report = {"canvas": [128, 128], "actions": [{"name": "dodge_forward", "requiredFinalCanvas": [160, 128], "requiredSourceCell": [480, 384], "fitsCanonicalCanvas": False, "roots": [[64, 112], [100, 108], [64, 112]]}]}
    page = render(report, {"qualities": {"480p": {"tokens": 100, "rmb": 0.1, "readableDistinctActions": 1, "rmbPerReadableAction": 0.1}}})
    assert "dodge_forward" in page and "需要扩画布" in page and "100 tokens" in page
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "report.html"
        path.write_text(page, encoding="utf-8")
        assert path.stat().st_size > 1000
    print("visualize_motion_plan self-test: ok")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an offline action-envelope and cost dashboard")
    parser.add_argument("report", nargs="?", type=Path)
    parser.add_argument("--costs", type=Path)
    parser.add_argument("--output", type=Path, default=Path("motion-plan.html"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.report is None:
        parser.error("envelope report JSON is required unless --self-test is used")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    costs = json.loads(args.costs.read_text(encoding="utf-8")) if args.costs else None
    args.output.write_text(render(report, costs), encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()

