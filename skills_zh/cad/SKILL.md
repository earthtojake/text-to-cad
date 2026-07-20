---
name: cad
description: 创建、修改、检查和验证（validation）以 STEP 为先的参数化 CAD 零件（part）和装配体（assembly）。用于自然语言 CAD 规格说明、参考图像、2D 技术图纸、STEP/STP 生成或直接检查、Python CAD 源码、源码级关节（joint）、选择器（selector）引用、几何事实、测量、配合（mating）增量、快照（snapshot），以及从 CAD 几何生成的 STL/3MF/原生 GLB 等附带产物（sidecar）输出。
---

# CAD 生成、检查和验证（validation）

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
将已安装的本地技能文件作为运行时的真相源；仓库链接仅用于来源溯源和发布评审。

## 目的

从自然语言需求创建或修改参数化 CAD 模型，生成经过验证（validation）的 STEP/STP 产物（artifact），检查几何引用，并返回已检查的输出。将 STEP 视为主要 CAD 产物（artifact）。将 STL、3MF 和原生 GLB 视为从以 STEP 为先的流程中分支出来的次要导出工作流（workflow）。对于装配体（assembly），当零件（part）具有功能性装配关系时，优先使用 `cadpy.assembly.AssemblyHelper`，配合源码级 build123d 关节（joint）、命名的配合（mating）基准（datum）以及原生标签。

进入 STEP 工作流（workflow）有两种方式：从 build123d Python 源码生成（从零设计或修改已生成模型时的默认方式），或直接导入现有 STEP/STP 文件（当不存在生成器或用户明确指向该 STEP 文件时）。两种方式都产生相同的可检查产物（artifact）。

## 适用场景

当用户请求 CAD 文件、STEP/STP 文件、build123d 源码、选择器（selector）引用（如 `#o1.2.f1`）、机械零件（part）、装配体（assembly）、外壳（enclosure）、支架（bracket）、夹具、孔、沉孔（counterbore）、锪孔（countersink）、槽、型腔（pocket）、凸台（boss）、支柱（standoff）、加强筋（rib）、圆角（fillet）、倒角（chamfer）、壳体、源码级关节（joint）、配合（mating）或测量时，使用本技能。当用户提供零件（part）的参考图像或 2D 技术图纸以进行复刻或提取设计意图时，也使用本技能。

当用户请求从 CAD 几何生成 STL、3MF 或原生 GLB 输出时，也使用本技能。保持这些工作流（workflow）为次要工作流（workflow），并加载 `supported-exports.md` 了解详情。对于 2D DXF 图纸，使用 `$dxf` 技能；当 DXF 从 3D 零件（part）投影而来时，本技能拥有 STEP 几何，`$dxf` 拥有图纸。

除非用户同时需要 CAD 几何，否则不要将本技能用于纯渲染的概念图、CAM 刀路、工程认证、FEA 结论、建筑 BIM 或手绘插图。

## 默认假设

除非用户另有说明，否则使用这些默认值。这些是首轮建模默认值，不是可制造性、公差或认证声明：

- 单位：毫米。
- 原点：按照 `references/positioning.md` 中的零件（part）类型默认值；当没有更合适的选项时，取主零件（part）或装配体（assembly）的中心。
- 基准（datum）平面：XY。
- 向上/拉伸轴：正 Z 方向。
- 输出几何：闭合的正体积实体，除非用户请求曲面或构造几何。
- STEP 结构：一个有效实体、实体复合体或带标签的装配体（assembly）复合体。
- 装配体（assembly）结构：固定的根零件（part）、零件（part）局部参考系（frame）、命名的配合（mating）基准（datum）、在适用时由 build123d 关节（joint）支撑的 `AssemblyHelper` 关系、显式的生成放置，以及详尽的原生标签。
- 小型塑料外壳（enclosure）壁厚：未指定时为 2.0-3.0 mm。
- 装饰性圆角（fillet）：对局部几何安全时为 1.0-3.0 mm。
- M3/M4/M5 标准间隙孔（clearance hole）：除非要求其他标准，否则为 3.4/4.5/5.5 mm。

仅当缺失信息导致模型无法建立、影响配合（mating）关键性、安全关键性或合规约束时，才提出一个聚焦的澄清问题。否则按显式假设继续进行。

## 工具和路径

从 CAD 技能目录出发，启动器形态为：

```bash
python scripts/step ...      # STEP 生成、GLB/拓扑产物（artifact）、网格附带产物（sidecar）
python scripts/inspect ...   # refs、measure、align、frame、diff
python scripts/snapshot ...  # PNG/GIF 可视化审查包
```

使用活动项目的 Python 解释器；将示例中的 `python` 视为解释器占位符。使用 `python scripts/<tool> --help` 获取完整的当前命令接口；参考文档展示的是推荐工作流（workflow），而非每个标志。

目标路径从命令的当前工作目录解析，而非从技能目录解析。从拥有产物（artifact）的工作区运行命令，并传入相对于 cwd 的目标路径，这样项目 CAD 文件就不会意外地解析到技能目录下。除非用户明确要求否则，将 STEP 输出及其 Python 生成器保存在同一目录中，并使用相同的基本文件名。

CAD 引用是相对于目标局部的 `#...` 选择器（selector）令牌，例如 `#o1.2` 或 `#o1.2.f1`。使用 CAD CLI 时，将 STEP/CAD 文件作为单独的目标参数传入。

## 必需工作流（workflow）

根据任务调整深度：简单零件（part）需要简短的简介和少量规格驱动的检查；装配体（assembly）和配合（mating）关键性工作需要完整的定位和对齐验证（validation）。

1. **对任务分类。** 新零件（part）、新装配体（assembly）、源码修改、直接 STEP/STP 检查、选择器（selector）选择、测量/对齐检查、快照（snapshot）审查，或次要输出请求。
2. **仅加载需要的参考。** 使用下方的触发条件，而非阅读整个参考集。
3. **编写自然语言 CAD 简介。** 从所有提供的输入中——散文、参考图像、技术图纸——提取尺寸、单位、坐标约定、特征意图、输出路径、假设和验证（validation）目标。使用 `references/cad-brief.md`。
4. **检查命名的可采购组件。** 当装配体（assembly）包含命名的现成执行器（actuator）、伺服器、电机、电子板、连接器或其他可采购组件时，在创建简化占位几何之前先搜索 `$step-parts`。如果未找到精确匹配，记录缺失并使用有文档记录的包络。
5. **编码前先规划。** 在编辑之前定义参数、意图标签、源码路径、预期包围盒，以及任何配合（mating）/定位基准（datum）。
6. **编辑源码，而非生成的产物（artifact）。** 使用 `gen_step()` 编写 build123d Python。当存在 Python 生成器时，在生成器上运行 `scripts/step`，而非在其导出的 STEP 上。仅当导入时没有生成器或用户明确将 STEP/STP 文件指定为目标时，才使用直接 STEP/STP 目标（`--kind part|assembly`）。
7. **生成显式目标。** 仅对显式目标运行 `scripts/step`；不要运行目录范围的生成。
8. **几何验证（validation）。** 运行 `scripts/inspect refs <step-or-cad-target> --facts --planes --positioning` 作为基线，然后通过有针对性的 `measure`、`align`、`frame` 或 `diff` 检查来验证（validation）用户规格所指出的尺寸和关系。
9. **对主要 STEP 进行快照（snapshot）——快照（snapshot）验证（validation）是强制性的。** 在创建或明显更新主要 STEP/STP 零件（part）或装配体（assembly）后，始终对其运行 CAD `scripts/snapshot` 并审查输出；确定性检查通过不是跳过的理由。唯一的跳过情况记录在 `references/snapshot-review.md` 中（无可见的几何变更，或不存在有效的产物（artifact））；跳过时报告原因。
10. **修复并重新运行。** 如果检查失败，修改最小负责任的源码段，重新生成，并重新运行失败的验证（validation）。

## 交接（handoff）

完成创建或修改 `.step`、`.stp`、`.stl`、`.3mf` 或原生 `.glb` 产物（artifact）的 CAD 工作后，当 `$cad-viewer` 技能已安装时，必须始终将显式文件路径交接（handoff）给 `$cad-viewer`。`$cad-viewer` 必须在尚未运行时启动 CAD Viewer，并返回指向相关创建或更新文件的链接；在最终响应中包含这些实时查看器链接。如果 `$cad-viewer` 不可用或启动失败，报告该情况并依赖 CLI 检查加快照（snapshot），而非默默省略交接（handoff）。此规则适用于本技能中的每个工作流（workflow），包括次要 STL/3MF/GLB 输出。

当生成验证（validation）快照（snapshot）时，在最终响应中包含已保存的 PNG/GIF 快照（snapshot）。如果没有适用的快照（snapshot），或快照（snapshot）生成失败，说明原因并报告仍然运行的确定性验证（validation）。

## 不可妥协项

- 保持 STEP 作为主要已验证（validation）CAD 产物（artifact）。生成的 STEP/STP、STL、3MF、GLB/拓扑（topology）输出和渲染附带产物（sidecar）是派生产物（artifact）；除非用户明确说明，否则 STL/3MF 是次要的。
- 使用命名参数、闭合实体、详尽的原生 build123d 标签和源码控制的几何意图。
- 在源码中编写装配体（assembly）定位。`references/positioning.md` 是 `AssemblyHelper`、build123d 关节（joint）、显式 `Location` 变换和对齐验证（validation）的权威参考。
- 不要将 `git status`、`git diff` 或文件大小波动用作大型导出 STEP/STP、GLB/拓扑（topology）、STL 或 3MF 产物（artifact）的 CAD 比较。改为比较源码变更、`scripts/inspect` 摘要、快照（snapshot）或生成的拓扑（topology）输出；仅将路径受限的 git status 用于簿记。
- 仅报告实际运行或直接由工具输出支持的检查。

## 渐进式参考

仅当其触发条件适用时才加载这些文件：

- `references/cad-brief.md` - 将散文、参考图像和技术图纸转换为 CAD 简介。
- `references/build123d-modeling.md` - build123d 建模模式、拓扑（topology）、选择器（selector）、特征、标签。
- `references/step-generation.md` - 从 Python 源码生成 STEP、直接 STEP/STP 导入以及生成后步骤。
- `references/inspection-and-validation.md` - 验证（validation）序列、选择器（selector）引用、事实、平面、测量、对齐、diff、参考系（frame）和验证（validation）报告。
- `references/snapshot-review.md` - 强制快照（snapshot）策略、包大小、目标视图，以及将视觉发现转化为几何检查。
- `references/positioning.md` - 零件（part）局部基准（datum）和原点、装配体（assembly）变换、build123d 关节（joint）、CLI 对齐验证（validation）和定位报告。
- `references/parameters.md` - 参数化或动画化 STEP 模型：源码参数、`.step.js` 附带附带产物（sidecar）模块、查看器控件和动画设计。
- `references/supported-exports.md` - 次要 STL/3MF/原生 GLB 附带附带产物（sidecar）工作流（workflow）。
- `references/repair-loop.md` - 诊断和修复程序。

最终响应应包含生成的文件、返回的 `$cad-viewer` 查看器链接、验证（validation）快照（snapshot）、实际运行的验证（validation）、假设和注意事项。使用 `references/inspection-and-validation.md` 了解报告结构。
