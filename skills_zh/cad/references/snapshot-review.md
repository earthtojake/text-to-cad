# Snapshot 审查

当为主要 STEP/STP artifact 选择保存的 CAD `scripts/snapshot` 输出时，请阅读此文件。

## 策略

Snapshot validation 是强制的。每个创建或明显更新的主要 STEP/STP part 或 assembly 至少获得一个已审查的 PNG snapshot；确定性检查通过不是跳过的理由。使用 CAD `scripts/snapshot` 而非手动打开查看器或使用 Playwright；snapshot 更快、更轻、更精确、更 agent 友好。对静态审查使用 PNG，对运动/动画审查使用 GIF，包括 STEP-module 参数动画。

仅当未创建或更新可见几何体，或不存在有效 artifact 时，才跳过保存的 snapshot：

- 几何体未更改的纯格式/导出请求
- 不改变可见几何体的源码更改
- 不创建或更新任何内容的仅检查任务（例如直接测量问题）
- 在有效 artifact 存在之前的失败 Python 或 STEP 生成

跳过时，报告原因和仍运行的确定性证据。

不要在 snapshot 上循环。仅当源码修复改变了可见几何体或特定视觉发现需要确认时才重新渲染。

## 数据包大小

一个 PNG 对于简单静态 part 足够。当从形状复杂度或 prompt intent 可能出现语义错误时，使用小型多视图数据包：

- assembly 或多个实体/part
- 多个面或多个轴上的孔
- shell、内部型腔（pocket）、孔、通道、开放 enclosure 或截面关键特征
- rib、gusset、boss、standoff、slot、cutout、lightening hole、fin、blade 或重复阵列
- 几何体、布尔、selector 或特征失败后的源码修复
- "看起来像请求的对象"是任务一部分的 prompt
- 确定性检查通过但可见语义仍不确定

## 小型数据包

优先使用带有这些输出的单个 `view` JSON 作业：

```json
{
  "input": "models/part.step",
  "mode": "view",
  "outputs": [
    { "path": "/tmp/render/iso.png", "camera": "iso" },
    { "path": "/tmp/render/iso_opposite.png", "camera": { "direction": [-1, 1, -0.8] } },
    { "path": "/tmp/render/top_ortho.png", "camera": "top" },
    { "path": "/tmp/render/front_ortho.png", "camera": "front" }
  ],
  "render": { "viewLabels": true, "padding": 0.12, "sizeProfile": "diagnostic" }
}
```

两个相对的等轴测视图保证每个面至少出现在一张图像中——后面、左侧和底部特征默认覆盖，而非出于怀疑。顶部正交是主要的阵列/对称检查，前部正交是轮廓检查。

将 `input` 设置为使用相对或绝对路径的主要 STEP/STP artifact。snapshot CLI 从该输入路径派生其内部渲染根。它默认为 `appearance: "workbench"` 和 `display.mode: "solid"`，与 CAD Viewer 匹配；标记/截面视图在省略尺寸时默认为 1600x1200。对需要 1800x1200 或 1920x1440 的复杂 assembly 使用 `render.sizeProfile: "assembly"` 或 `"assembly-large"`。对于 CAD 审查数据包，使用静态图像渲染模式 `view` 和 `section`；当视觉检查受益于显式 CAD 线条时，将 `display.mode` 设置为 `solid`、`transparent`、`hidden_edges`、`hidden_lines_removed` 或 `wireframe`。

使用 `--focus '#o1.2' ...` 仅渲染特定 part 或子 assembly 实例 ref，或 `--hide '#o1.2' ...` 省略它们。不要在同一 snapshot 命令或作业中组合 focus 和 hide。这些筛选器仅接受实例 ref，不接受面、边、顶点或形状 selector。

snapshot CLI 在保存数据包时在每个输出文件扩展名前附加一个共享的 UTC 秒时间戳，因此可读路径如 `iso_solid.png` 变为 `iso_solid_20260527T163012Z.png` 等名称。

## 针对性添加

仅当简报或失败模式需要时添加视图：

- 参考图像再现：从参考图像视角的一张 snapshot，用于并排比较
- `section`：shell、孔、内部型腔（pocket）、通道、blind hole、enclosure 或壁/底关系
- `display.mode: "solid"`：带有显式边线条的着色 CAD 视图
- `display.mode: "rendered"`：无边线覆盖的着色材质视图
- `display.mode: "transparent"`：当透明度增加信息且 wireframe 太嘈杂时，用于重叠、碰撞（collision）、enclosure 可读性或隐藏接触检查
- `display.mode: "hidden_edges"`：不透明着色上下文，其中隐藏/遮挡的 CAD 边通过实体可见
- `display.mode: "hidden_lines_removed"`：应抑制隐藏/遮挡边的以线条为重点的审查
- `display.mode: "wireframe"`：当完整三角线框有用时，用于内部重叠、隐藏干涉或 assembly 碰撞（collision）怀疑
- 标记或注释审查：使用支持的 CAD Viewer ref、选择、截图或 GUI 审查链接

分解或标记审查是一个 intent，而非渲染模式。通过支持的 CAD Viewer 机制、支持的 JSON 作业设置或 GUI 链接来满足它。

## 诊断审查

视觉审查是诊断性的，而非权威性的。在将每个视觉问题用作 validation 声明之前，将其转换为后续几何检查：

- 孔阵列看起来不对称 -> 测量孔中心并比较 offset
- lid、子 part 或实例看起来 offset -> 检查 frame 和 mating delta
- gusset、boss、standoff、rib 或板可能浮动 -> 检查实体计数、标签、连通性、接触或相关距离
- 型腔（pocket）、孔或 blind hole 看起来错误 -> 运行截面审查，然后测量壁厚、深度或贯穿条件
- 重复阵列看起来不均匀 -> 测量阵列中心、角度间距或实例 frame

最终报告应包括生成的 snapshot PNG/GIF 或已记录的跳过原因，并说明哪些确定性检查支持任何视觉发现。
