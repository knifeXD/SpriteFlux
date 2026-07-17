# Tripo 通用游戏建模与 Godot DCC Bridge 交接契约

状态：官方文档研究完成；尚未执行 Tripo 生成、下载或 Godot Bridge 实操  
官方资料核对日期：2026-07-17  
适用范围：角色、静态关卡物件、模块化建筑、地编装饰、遮挡物，以及最终以低分辨率或像素化方式渲染的 3D 游戏资产。

## 核心结论

Tripo 的完成状态只代表生成任务结束，不代表游戏资产通过。所有资产先走同一条公共前半段：输入与权利确认、付费预检、不可变原始输出、身份与尺寸检查、拓扑/UV/材质审计、稳定 ID 与版本化清单。然后按资产类型分流：

| 资产类型 | 必需质量门 | 明确跳过 |
| --- | --- | --- |
| `character_skinned` | 身份、拓扑、UV/材质、骨架、权重、形变、动作交换、引擎实拍 | 无 |
| `environment_static` | 剪影/尺寸、拓扑/法线、UV/材质、pivot/落地、模块拼接、碰撞数据、LOD/性能、引擎实拍 | 骨架、蒙皮、动作 |
| `environment_articulated` | 静态门，加已声明运动部件的层级、pivot 与必要动画 | 未声明的全身骨架与多余动作 |

静态物件不因“以后可能动”而默认绑骨。门、拉杆、机械件等只有在运动需求被明确声明后才进入 `environment_articulated`；简单刚体开合优先使用节点层级和正确 pivot，不把骨架当默认答案。

## 像素 3D 的定义

“像素建模”不是在高频网格上覆盖整屏马赛克。候选在目标像素高度就必须成立：

- 主轮廓、负空间、薄片和凸出部位在目标正交/透视镜头可读；
- 几何密度服务轮廓、关节或模块接缝，不保存最终画面无法表达的噪声；
- 材质使用受控的大色区、有限层级和可追踪的 UV/texel density，或明确声明的 vertex-colour 路线；
- 贴图、法线和粗糙度不能在低分辨率下产生闪烁、花纹噪声或错误高光；
- Godot 的低分辨率 SubViewport、Nearest、色阶/调色板、实时光影是表现配置，不修改源模型的比例、碰撞或资产真相。

必须在目标屏幕尺寸、真实灯光、阴影和景深条件下验收；过小预览、模糊、过暗或景深不能用来隐藏几何与材质问题。

## 公共获取流程

1. 定义用途、资产类型、目标尺寸/像素高度、观察方向、可见面、模块接口、材质与碰撞需求。
2. 固定输入参考与使用权。角色优先一致多视图；关卡物件优先正交多视图、尺寸图或同风格资产板。AI 补出的背面只是一项候选推断。
3. 在任何付费任务前核对当前模型、参数、套餐/下载权、商业条款、预计 credits、重试上限和输出生命周期，并取得有范围授权。通用 Skill 不保存某个项目的累计费用。
4. 生成后立即保存原始输出、公开安全的模型/版本元数据、私密任务回执和输出哈希。临时 URL 不得成为运行时依赖。
5. 先审计原始候选，再生成新的标准化派生版；不得覆盖原件，也不得用引擎节点缩放、相机或后处理掩盖单位、pivot 或几何错误。
6. 写入版本化 manifest，只有通过目标分支全部质量门的派生版才能进入 accepted/runtime 库。

## 静态关卡物件与地编门

### 几何与模块化

- 记录源/运行时单位、up/forward、AABB、实际尺寸、pivot 与落地点；Center Bottom 只能作为导入默认值，不能代替测量。
- 检查非流形、自交、内部壳、重复面、反法线、远端散点、薄片厚度和不可见高密度区域。
- 模块化墙体、地板、门框、管线等必须有声明的网格步长、连接面、边界尺寸和接缝截图；拼接缝、漏光和纹理断裂 fail closed。
- 静态包应无 Armature、skin weights 和 Action。若 provider 输出夹带它们，清理为新的派生包并记录，不在运行时静默忽略。

### UV、材质与贴图

- UV 非空且策略明确：唯一展开、镜像、叠片或平铺均需声明；检查拉伸、灾难性重叠、接缝与统一 texel density。
- 材质槽与 draw call 数量受控；基础色、normal、roughness、metallic、AO、emission 和 alpha 语义明确。
- 核对 normal 方向、sRGB/linear、透明模式、双面需求和纹理尺寸。生成器预览正确不代表 Godot 材质正确。
- 保留贴图来源、许可证/商业权利快照和哈希；不得把浏览器缓存或临时签名 URL 当源资产。

### 碰撞、地编与性能

- 碰撞是独立数据，不从视觉 alpha 或高模网格盲目生成。记录 collision shape、layer/mask、导航/阻挡语义和可交互元数据。
- 地编实例使用稳定 ID、版本、放置规则、随机化范围、遮挡/阴影标志与场景包装器；不得引用 provider 绝对路径。
- 测量三角面、顶点、材质槽、draw call、纹理内存、LOD、阴影和遮挡成本。预算由消费项目定义，未批准值保持 Proposed/TBD。
- 前景遮挡、深度排序、灯光、投射阴影和远景 LOD 必须在真实目标场景中检查。

## Tripo → Godot DCC Bridge

官方当前把 DCC Bridge 描述为 Godot 编辑器插件。核对日的边界如下：

- 需要 Godot 4.6+、受支持桌面系统和 Chromium 116+ 浏览器；执行时必须重新核对版本。
- 插件放入项目 `addons` 并在 Project Settings → Plugins 启用；安装或升级引擎/插件需要用户授权。
- Bridge 服务运行时只识别第一个 Godot 实例；只支持 Editor mode 传输，不支持 Play mode，也不能成为发布运行时依赖。
- 默认可使用 Center Bottom pivot、当前最大纹理分辨率、自动材质与自动放置；这些是传输设置，不是质量证明。
- 动画只有在 Tripo 侧先生成并在导出时选择才会传输；`environment_static` 不应选择动画。

推荐交接：

1. 在兼容的隔离 Godot 项目/分支启用 Bridge，记录插件与编辑器版本。
2. 传输前保存可独立下载的版本化 GLB/源输出及哈希，避免 Bridge 成为唯一副本。
3. 传输时记录 Tripo 稳定模型 ID、资产类型、格式、pivot 选项、纹理档位和目标目录；不记录凭据或签名 URL。
4. 把导入场景视作只读 source。项目侧用 inherited scene、外部资源或包装场景添加碰撞、脚本、LOD、放置和元数据，避免刷新/重导入覆盖项目修改。
5. 完成 import report、材质抽取/覆盖、单位与 AABB、pivot/落地、碰撞、性能和真实画面 QA 后才晋级。

若目标 Godot 版本不受支持，不得为了省一步传输擅自升级。改用版本化 GLB 手动导入，并执行完全相同的 manifest 与验收门；Bridge 和 GLB 是两种 transport，不是两套质量标准。

## 最小 manifest

```json
{
  "assetId": "environment.prop.example.v001",
  "assetClass": "environment_static",
  "provider": "tripo",
  "providerModelVersion": "verified-at-execution",
  "sourceHash": "sha256:...",
  "rightsSnapshot": "private-record-reference",
  "transport": "godot_dcc_bridge",
  "transportVersion": "verified-at-execution",
  "engineVersion": "verified-at-execution",
  "units": "meter",
  "upAxis": "+Y",
  "forwardAxis": "project-contract",
  "pivot": "measured-center-bottom",
  "bounds": [0, 0, 0, 1, 1, 1],
  "materials": [],
  "textures": [],
  "collisionRef": "separate-project-data",
  "qaState": "candidate"
}
```

字段值必须来自实际导入测量；示例不是默认尺寸或轴向。公开 SpriteFlux 只保存 schema 与合成测试，不保存私有模型、参考图、任务 ID、费用账本、凭据或项目输出。

## 晋级条件

只有以下证据齐全才能称为 accepted：

- 原始输出、标准化派生版、manifest、权利/条款记录和哈希可追溯；
- 对应资产类型的几何、UV/材质、pivot/尺寸、碰撞/层级和性能门通过；
- Bridge 或 GLB 重导入可重复，不覆盖项目侧包装数据；
- 在目标 Godot 版本与真实场景中完成正常材质、低分辨率/像素化、灯光、阴影、深度和目标尺寸截图；
- 无未解释错误、隐藏依赖、临时路径或多余角色骨架/动画数据。

## 官方资料

- Tripo DCC Bridge for Godot: <https://www.tripo3d.ai/blog/tripo-dcc-bridge-for-godot>
- Tripo AI 3D Models in Godot workflow: <https://www.tripo3d.ai/blog/how-to-use-ai-3d-models-in-godot>
- Tripo pricing/plans: <https://www.tripo3d.ai/pricing>
- Tripo developer documentation index: <https://developers.tripo3d.ai/llms.txt>

执行任务前重新核对官方页面；支持版本、导出权限、套餐、credits、模型 ID 和下载限制均可能变化。
