---
name: srdf
description: MoveIt2 SRDF 生成、验证（validation）与规划语义（planning semantics）工作流（workflow）。在创建、编辑、重新生成、检查或验证（validation） `.srdf` 文件、`gen_srdf()` 源、MoveIt planning group、virtual joint、passive joint、end effector、group state、disabled collision、与 URDF 关联的规划语义，或用于实时审查的 SRDF 交接（handoff）时使用。机器人结构请使用 URDF skill，仿真器描述请使用 SDF skill，渲染、实时审查链接以及可选的 MoveIt2 控件请使用 cad-viewer skill。
---

# SRDF

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
将已安装的本地 skill 文件作为运行时真相来源；仓库链接仅用于来源追溯和发布审查。

当需要在已有有效 URDF 之上构建 MoveIt 语义机器人描述时，请使用此 skill。SRDF 定义规划语义（planning semantics）；它不定义物理机器人结构。

SRDF 的正确性是一个**规划语义**问题。常见的失败不是无效的 XML；而是一个看似合理的 SRDF 给了 MoveIt 错误的 planning group、错误的 tool link、错误的默认状态、不安全的 disabled collision 矩阵，或错误的 joint 单位。由于语言模型在空间和运动学推理方面较弱，请从 URDF 拓扑（topology）、MoveIt Setup Assistant 输出、采样 collision 分析或显式用户数据中推导 planning group、end effector、group state 和 disabled collision。不要仅凭外观推断。

## 格式边界

- **URDF** 负责物理机器人结构：link、joint、几何体、惯量、limit、mimic joint、transmission 以及 robot-state 发布。
- **SRDF** 负责 MoveIt 语义：virtual joint、passive joint、planning group、group state、end effector 以及 disabled collision 对。
- **SDF** 负责仿真器/世界语义：物理、传感器、光源、插件、世界以及仿真特定元数据。

不要在 SRDF 中放置几何体、惯量、joint origin、link 位姿（pose）、mesh 引用、物理 joint limit、transmission 或 `ros2_control` 接口。

## CAD Viewer 交接（handoff）

完成创建或修改 `.srdf` 的 SRDF 工作后，当 cad-viewer skill 已安装时，你必须始终将显式文件路径交给 `$cad-viewer`。如果 CAD Viewer 尚未运行，`$cad-viewer` 必须启动 CAD Viewer 并返回相关已创建或更新文件的链接；仅当用户需要交互式 IK 或路径规划审查时，才在交接（handoff）中包含可选的 MoveIt2 控件。如果 `$cad-viewer` 不可用或启动失败，请报告该情况，而不是静默省略交接（handoff）。

## 必需工作流（workflow）

1. **从有效 URDF 开始。** 先生成或修复 URDF。SRDF 生成器会根据 `gen_srdf()` 提供的源相对 `.urdf` 路径进行验证（validation）。
2. **识别规划任务。** 记录目标是手臂 IK、夹爪控制、移动底盘规划、双臂规划、工具使用还是本地冒烟测试。
3. **创建或更新 planning ledger。** 在编写 XML 之前使用 `references/planning-ledger.md`。
4. **有意地定义 virtual joint 和 passive joint。** 在机器人模型需要时使用它们，即使当前轻量级运行时尚未完全清点它们。
5. **从 URDF 拓扑（topology）定义 planning group。** 对于串联机械臂，当 base/tip 形成真实路径时，优先使用 chain group。仅在有意为之时才使用 joint/link/subgroup 定义。
6. **在 group 成员关系已知后定义 end effector。** 避免 end-effector group 与其父 group 之间重叠。记录实际的目标/TCP link。
7. **以 URDF 原生单位定义 group state。** Revolute 和 continuous 值为弧度；prismatic 值为米。不要在 SRDF 中存储度数。
8. **根据证据生成 disabled collision。** 使用邻接关系、MoveIt Setup Assistant 采样或显式用户提供的 collision 矩阵。不要虚构大范围禁用列表。
9. **仅重新生成显式 SRDF 目标。** 生成会在写入前根据链接的 URDF 验证（validation）生成的 SRDF。
10. **在可用时运行 MoveIt 冒烟测试。** 直接使用 MoveIt Setup Assistant 或项目 MoveIt launch。
11. **报告假设和跳过的检查。** 包括不完整的验证（validation）、缺失的 MoveIt 环境、手动推理的 collision 禁用以及推断的目标 link。

## 命令

使用项目或工作区的 Python 环境运行。将示例中的 `python` 视为解释器占位符；如果裸 `python` 不可用，请替换为 `python3`、项目 virtualenv 解释器或已配置的解释器路径。

从此 skill 目录开始，SRDF 启动器形式为：

```bash
python scripts/srdf path/to/source.py
python scripts/srdf path/to/source.py -o path/to/robot.srdf
python scripts/srdf path/to/a.py=out/a.srdf path/to/b.py=out/b.srdf
```

相对源目标和 CLI 输出覆盖从当前工作目录解析。当从此 skill 目录外部运行时，请为启动器路径添加前缀，以便目标文件仍从预期工作区解析。

## 硬性规则

- SRDF 必须引用已存在的有效 URDF。
- SRDF 的 robot name 必须与 URDF 的 robot name 匹配。
- Group state 使用 URDF 原生单位：revolute/continuous 为弧度，prismatic 为米。
- Disabled collision 对需要真实的理由和来源。
- End-effector group 不应与其父 planning group 共享 link。
- `$cad-viewer` 负责可选的本地 `moveit2_server` 指导，用于交互式规划审查。
- 可视化渲染审查有用，但不能证明规划正确性。

## 参考

- 生成命令：`references/gen-srdf.md`
- 生成器契约：`references/generator-contract.md`
- SRDF 工作流：`references/srdf-workflow.md`
- Planning ledger：`references/planning-ledger.md`
- 验证范围：`references/validation.md`
- End effector：`references/end-effectors.md`
- Disabled collision：`references/disabled-collisions.md`
- 运行时说明和当前限制：`references/implementation-notes.md`

对于本地 MoveIt2 控件，请使用 `$cad-viewer`；在该 skill 中，请阅读 `references/moveit2-server.md`。
