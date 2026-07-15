# Seedance Mini 像素动作实测记录

本记录是 2026-07-15 项目样本，不是长期报价。模型、价格、最低时长和 token 计算可能变化；每次执行前仍需查官方文档。原始 task ID、签名下载地址、API Key 和付费视频不进入公开 Skill 仓库。

## 固定条件

- 模型：`doubao-seedance-2-0-mini-260615`
- 画幅：4:3
- 时长：4 秒
- 视频 FPS：模型固定 24 FPS
- 关闭音频与水印
- 一张角色参考图，统一绿幕、侧视、朝右、固定身份/服装/武器/比例
- 八个相同动作命题：idle、walk、jump/land、slash、forward dodge、back dodge、block、hit react
- 当时无视频输入官方单价依据：¥23 / 百万 tokens

## 批次设计

| 档位 | 付费调用 | 同屏主体 | 每主体时间线 | 请求动作 |
|---|---:|---:|---|---:|
| 480P | 2 | 每条 2 个 | 每主体两个约 2 秒的不同动作 | 8 |
| 720P | 1 | 2×2，共 4 个 | 每主体两个约 2 秒的不同动作 | 8 |

所有动作使用相同命题。密集 720P 格子并没有自动带来更好的方向和 idle 恢复控制。

## 实际 usage 与成本

| 档位 | 实际 tokens | 实际人民币 | 可读动作 | 严格合格动作 | 每可读动作 | 每严格合格动作 |
|---|---:|---:|---:|---:|---:|---:|
| 480P 两条合计 | 79,782 | ¥1.834986 | 8 | 5 | ¥0.229373 | ¥0.366997 |
| 720P 一条 | 87,850 | ¥2.020550 | 8 | 2 | ¥0.252569 | ¥1.010275 |
| 全实验 | 167,632 | ¥3.855536 | — | — | — | — |

480P 单条实际为 39,891 tokens、¥0.917493。这里的“严格合格”要求 canonical idle 端点、方向、尺寸、root/baseline 和动作连续性通过；“可读”只表示动作能被辨认，不能直接等同于游戏可交付。

## 可复用结论

- 本样本中 480P 与 720P 的主观视觉质量接近，不能仅凭输出分辨率判断动作价值。
- 同屏主体越少，动作逻辑、方向和身份通常更可控。默认优先能通过源像素与大动作包络检查的 480P 少主体布局。
- 跳跃、前后闪避、突进和击退必须为真实位移留画布；如果 480P 单格无法容纳，降低密度或升级分辨率。
- 比较 `总成本 / 严格合格的不同动作`，不要只比较每条视频价格或请求动作数。
- 一条 4 秒视频是否能放两个“2 秒动作”，取决于每个动作是否真的包含稳定开始和恢复；下载后必须重新检测边界。

## 脱敏成本数据示例

下面的数据结构可直接传给 `visualize_motion_plan.py --costs`：

```json
{
  "priceBasis": "2026-07-15 sample; verify current official price",
  "qualities": {
    "480p": {
      "tokens": 79782,
      "rmb": 1.834986,
      "requestedDistinctActions": 8,
      "readableDistinctActions": 8,
      "acceptedActions": 5,
      "rmbPerReadableAction": 0.22937325,
      "rmbPerAcceptedAction": 0.3669972
    },
    "720p": {
      "tokens": 87850,
      "rmb": 2.02055,
      "requestedDistinctActions": 8,
      "readableDistinctActions": 8,
      "acceptedActions": 2,
      "rmbPerReadableAction": 0.25256875,
      "rmbPerAcceptedAction": 1.010275
    }
  }
}
```

