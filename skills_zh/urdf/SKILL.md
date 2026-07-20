---
name: urdf
description: URDF 机器人描述生成及默认生成时验证（validation）。在创建、编辑、重新生成、检查或调试 `.urdf` 文件、Python `gen_urdf()` 源码、机器人连杆（link）、关节（joint）、限位、惯性参数（inertial）、视觉/碰撞（collision）几何、网格（mesh）引用、参考系（frame）约定或生成的机器人描述产物（artifact）时使用。SRDF 技能用于 MoveIt2 语义组和 IK/路径规划语义；cad-viewer 技能用于本地 MoveIt2 服务器控制；CAD 技能用于 STEP/STL/3MF/DXF/GLB 输出。
---

# URDF

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
将已安装的本地技能文件作为运行时源真相；仓库链接仅用于来源说明和发布评审。

本技能用于 URDF 机器人描述输出。应将 URDF 工作视为受约束的运动学建模，而不仅仅是 XML 编写。主要的正确性风险在于参考系（frame）放置、关节（joint）轴语义、单位一致性、网格（mesh）缩放、惯性参数（inertial）数据以及生成产物（artifact）漂移。

## 核心规则

1. 将定义 `gen_urdf()` 的 Python 源码视为源真相。将配置的 `.urdf` 文件视为生成产物（artifact）。
2. 仅生成显式的 URDF 目标。不要从本技能重新生成无关的 CAD、网格（mesh）、渲染、SRDF、SDF 或仿真器产物（artifact）。
3. `scripts/urdf` 生成器默认对生成的 URDF 进行验证（validation）。不要使用或记录单独的 `validate` 命令。
4. 在编写或修改 URDF XML 之前，先建立机器人的参考系（frame）、关节（joint）、几何、单位和假设清册（ledger）。参见 `references/design-ledger.md`。
5. 严格遵循 URDF 参考系（frame）语义。关节（joint）原点、连杆（link）参考系（frame）、关节（joint）轴以及视觉/碰撞（collision）/惯性参数（inertial）原点使用不同的参考系（frame）。参见 `references/frame-semantics.md`。
6. 不要从模糊的叙述推断空间变换、网格（mesh）单位、手性、轴向或关节（joint）符号。使用 CAD 变换、标注尺寸的图纸、测量值、现有源数据或明确的已记录假设。
7. 优先选择简单、可审计的生成器代码，而非巧妙的 XML 构造。保持常量按物理意义命名，而非任意数字。
8. 对于物理连杆（link），当目标消费者需要时，应分别建模 `inertial`、`visual` 和 `collision`。仅参考系（frame）连杆（link）可以有意识地省略质量和几何。

## CAD Viewer 交接（handoff）

完成创建或修改 `.urdf` 的 URDF 工作后，当 `$cad-viewer` 技能已安装时，必须始终将显式文件路径交接（handoff）给 `$cad-viewer`。如果 CAD Viewer 尚未运行，`$cad-viewer` 必须启动 CAD Viewer，并返回相关已创建或更新文件的链接；如果 `$cad-viewer` 不可用或启动失败，应报告该情况，而不是静默省略交接（handoff）。

## 工作流（workflow）

1. 确定 `gen_urdf()` Python 源码和目标 `.urdf` 输出。
2. 确定目标消费者：RViz、robot_state_publisher、Gazebo/Ignition、MoveIt、真实机器人驱动器或其他仿真器。
3. 在编辑参考系（frame）、原点、轴、网格（mesh）缩放、限位或惯性参数（inertial）之前，先读取或创建设计清册（ledger）。
4. 编辑生成器源码，而非生成的 URDF XML。
5. 仅使用 `scripts/urdf` 重新生成显式目标。
6. 让生成时验证（validation）在 XML、图、关节（joint）、几何、网格（mesh）引用和惯性参数（inertial）问题上快速失败。
7. 当几何或网格（mesh）引用依赖于已更改的 CAD 或导出网格（mesh）输出时，先用所属的 CAD 或网格（mesh）工作流（workflow）重新生成那些显式产物（artifact），再重新生成受影响的 URDF 目标。
8. 当可用时，运行适合目标的消费者冒烟测试：RViz 显示、robot_state_publisher 树、Gazebo/Ignition 加载或 MoveIt 模型加载。
9. 报告剩余假设、未检查的空间数据以及验证（validation）/冒烟测试缺口。

## 命令

使用项目或工作区的 Python 环境运行。将示例中的 `python` 视为解释器占位符；如果裸 `python` 不可用，请替换为 `python3`、项目 virtualenv 解释器或已配置的解释器路径。URDF 生成器和轻量级验证（validation）器仅使用 Python 标准库；RViz、Gazebo 或 MoveIt 等下游消费者可能需要各自运行时包。

在本技能目录下，启动器形式为：

```bash
python scripts/urdf path/to/source.py
python scripts/urdf path/to/source.py -o path/to/robot.urdf
python scripts/urdf path/to/a.py=out/a.urdf path/to/b.py=out/b.urdf
```

纯 Python 目标会在源文件旁写入同级 `.urdf`。`-o`/`--output` 仅对单个纯目标有效。使用 `SOURCE.py=OUTPUT.urdf` 对来自定义多目标输出位置。

相对源目标和 CLI 输出覆盖从当前工作目录解析。当从本技能目录之外运行时，请为启动器路径添加前缀，以确保目标文件仍从预期工作区解析。

启动器仅执行 `gen_urdf()` 并验证生成的 URDF 输出。它不提供单独的仅验证（validation）命令。

## 参考

- 设计清册（ledger）：`references/design-ledger.md`
- 参考系（frame）语义：`references/frame-semantics.md`
- URDF 生成器契约：`references/generator-contract.md`
- URDF 生成命令：`references/gen-urdf.md`
- URDF 编辑工作流（workflow）：`references/urdf-workflow.md`
- 生成时验证（validation）期望：`references/validation.md`
