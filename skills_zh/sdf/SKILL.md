---
name: sdf
description: SDFormat/SDF 模型（model）与世界（world）生成、校验及仿真器（simulator）交付。用于 `.sdf` 文件、SDFormat XML、Python `gen_sdf()` 源文件、模型（model）、世界（world）、连杆（link）、关节（joint）、位姿（pose）、参考系（frame）、惯性（inertial）、visual/collision 几何（geometry）、mesh URI、传感器（sensor）、光源（light）、物理（physics）、插件（plugin）、include、Gazebo、静态 SDF 审查或仿真器特定的元数据。不用于 signed-distance-field 几何。
---

# SDF

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
将已安装的本地技能文件作为运行时的事实来源（source of truth）；仓库链接仅用于溯源和发布审查。

当交付物是 SDFormat 文档或 Python `gen_sdf()` 源文件时使用本技能。SDFormat 描述仿真器与世界（world）行为：模型（model）、世界（world）、参考系（frame）、位姿（pose）、连杆（link）、关节（joint）、惯性（inertial）、visual、collision、传感器（sensor）、光源（light）、物理（physics）、插件（plugin）、include 以及仿真器元数据。

本技能用于 **SDFormat**，而非 signed-distance-field 几何。

## 核心规则（Core rules）

1. 将定义 `gen_sdf()` 的 Python 文件视为事实来源（source of truth）。将已配置的 `.sdf` 文件视为生成产物（artifact），除非用户明确要求直接编辑 XML。
2. 在编辑前确认目标消费者（target consumer）：Gazebo/libsdformat 版本、其他仿真器（simulator）、仅可视化工具、模型（model）包，或世界（world）交付。
3. 确定文档类型：模型级（model-level）SDF、世界级（world-level）SDF，或世界中的模型（model-in-world）。对于可复用的机器人/物体导出，优先使用模型级 SDF。
4. 除非目标明确要求其他单位，否则使用 SI 单位：米、千克、秒、弧度。
5. 除非目标消费者对版本有约束，否则新输出优先使用 `version="1.12"`。
6. 在编写位姿（pose）、参考系（frame）、关节（joint）轴、mesh 缩放、惯性（inertial）、传感器（sensor）或插件（plugin）之前，先建立设计台账（design ledger）。使用 `references/design-ledger.md` 和 `references/llm-guardrails.md`。
7. 不要仅凭视觉印象推断空间变换（transform）。位姿（pose）、轴、缩放、质量、惯性（inertia）和参考系（frame）名称应从上游源数据、图纸、仿真器文档、测量值或明确假设中推导。
8. 优先使用辅助函数和命名常量，而非大型 XML 字符串字面量。隐藏的数值是 SDF 常见的失败模式。
9. 仅使用 `scripts/sdf` 或仓库现有的 SDF 启动器生成显式目标。不要执行目录范围的生成。
10. 在重新生成引用它们的 SDF 之前，先使用其所属工作流（workflow）重新生成上游几何（geometry）、mesh、robot-description、渲染、拓扑（topology）或包资产。
11. 生成后运行可用检查：内置校验、可选的 `gz sdf --check`、仿真器加载、关节（joint）运动以及插件（plugin）/传感器（sensor）启动。
12. 报告假设、跳过的检查、未解决的资源路径以及目标特定的兼容性风险。

## 范围（Scope）

本技能用于 SDFormat 输出和生成器。不用于 signed-distance-field 建模、原始几何（geometry）生成、规划语义，也不用于掩盖错误的上游机器人/源数据，除非任务明确仅针对仿真器。

## CAD Viewer 交付

完成创建或修改 `.sdf` 的 SDF 工作后，当 `$cad-viewer` 技能已安装时，必须始终将显式文件路径交给 `$cad-viewer`。`$cad-viewer` 必须在尚未运行时启动 CAD Viewer，并返回相关已创建或更新文件的链接；如果 `$cad-viewer` 不可用或启动失败，应报告该情况，而不是静默省略交付。

## 工作流（Workflow）

1. 定位 `gen_sdf()` 源文件和预期的 `.sdf` 输出。
2. 读取或创建设计台账（design ledger）。
3. 在编辑任何 `<pose>`、`<frame>`、关节（joint）轴、`relative_to`、`expressed_in`、嵌套作用域、传感器（sensor）参考系（frame）或插件（plugin）参考系（frame）之前，先阅读 `references/frame-semantics.md`。
4. 编辑生成器源文件，而非生成的 XML。
5. 当辅助函数能让生成结构更清晰时可选使用；仍允许使用原始 ElementTree。
6. 重新生成显式目标。
7. 将内置校验视为护栏，而非仿真器证明。
8. 在可用时运行目标消费者冒烟测试。
9. 报告已运行检查、跳过检查和假设。静态渲染不会执行 SDF 插件（plugin）或读取文件编写的运动元数据。

## 命令（Commands）

使用项目或工作区 Python 环境运行。将示例中的 `python` 视为解释器占位符；如果裸 `python` 不可用，替换为 `python3`、项目 virtualenv 解释器或配置的解释器路径。

```bash
python scripts/sdf path/to/source.py
python scripts/sdf path/to/source.py -o path/to/output.sdf
python scripts/sdf path/to/a.py=out/a.sdf path/to/b.py=out/b.sdf
```

普通 Python 目标在其源文件旁写入同级 `.sdf` 文件。`-o` / `--output` 仅对单个普通目标有效。`SOURCE.py=OUTPUT.sdf` 支持自定义多目标输出位置。

如果运行时支持可选外部检查：

```bash
python scripts/sdf path/to/source.py --gz-check auto
python scripts/sdf path/to/source.py --gz-check required
python scripts/sdf path/to/source.py --gz-check never
```

`gz sdf --check` 是可选的目标消费者校验。在不可用时应报告为跳过，除非明确要求。

## 必需的报告格式

完成 SDF 任务时，包含一份简洁报告：

```text
Generated: path/to/model.sdf from path/to/model.py
Checks run:
- bundled SDF validation: passed
- gz sdf --check: skipped, gz not installed
- simulator load: skipped, target simulator unavailable
- viewer handoff: `$cad-viewer` link returned
Assumptions:
- Assumed mesh units are meters.
- Assumed lidar frame is coincident with lidar_link.
Risks:
- Camera plugin filename was not verified in the target simulator environment.
```

## 参考（References）

- 生成命令：`references/gen-sdf.md`
- 生成器契约：`references/generator-contract.md`
- SDF 工作流：`references/sdf-workflow.md`
- 构建辅助函数：`references/builder-helpers.md`
- LLM 护栏：`references/llm-guardrails.md`
- 设计台账：`references/design-ledger.md`
- 参考系（frame）语义：`references/frame-semantics.md`
- 校验范围：`references/validation.md`
- 冒烟测试：`references/smoke-tests.md`
- 互操作性说明：`references/interoperability.md`
- 示例：`references/examples.md`
- 运行时说明与当前限制：`references/implementation-notes.md`
