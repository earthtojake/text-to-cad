# SRDF 工作流（workflow）

SRDF 是 URDF 的 MoveIt 语义伴侣。将物理机器人结构、link、joint、几何体、惯量、mesh 引用和 limit 保留在 URDF 中。将规划语义保留在 SRDF 中。

## 编辑循环

1. 从有效 URDF 开始。SRDF 无法修复错误的 link frame、joint origin、limit 或几何体。
2. 找到定义 `gen_srdf()` 的 Python 源。
3. 将该源视为权威。不要手动编辑生成的 `.srdf` 输出。
4. 填写或更新 planning ledger。
5. 当机器人 root 需要 planning/world 附着时定义 virtual joint。
6. 为未驱动的 joint 定义 passive joint。
7. 从 URDF 拓扑（topology）定义 planning group。
8. 仅在 group 成员关系已知后定义 end effector。
9. 以 URDF 原生单位定义 group state，并根据 URDF limit 检查它们。
10. 仅从邻接关系、采样、Setup Assistant 输出或显式用户证据定义 disabled collision。
11. 仅使用 `scripts/srdf` 重新生成显式 SRDF 目标。
12. 在可用时将生成或修改的 `.srdf` 文件交给 `$cad-viewer` 以获取实时查看器链接。
13. 在可用时运行 MoveIt 冒烟测试。使用 `$cad-viewer` 进行本地基于查看器的 IK 或路径规划控件。
14. 报告假设和跳过的检查。

## 典型 SRDF 内容

- 用于 root/world 附着的 `<virtual_joint>` 条目。
- 用于未驱动 joint 的 `<passive_joint>` 条目。
- `<group>` planning group，通常按 joint 列表或 chain。
- 将 tool group 连接到父 planning group 的 `<end_effector>` 条目。
- `<group_state>` 命名 joint 状态，如 `home`。
- 用于邻接、采样安全或有意忽略 collision 的 `<disable_collisions>` 对。

## Planning group

MoveIt 作用于选定的 planning group。其他 joint 保持静止，除非它们属于选定 group 或由规划管道另行管理。

一个 group 可以表示为：

- joint 的集合；
- link 的集合；
- 从 base link 到 tip link 的串联 chain；
- subgroup 的集合。

对于串联 chain，base link 是 chain 中第一个 joint 的父 link，tip link 是最后一个 joint 的子 link。验证（validation） URDF 图实际包含该路径。

## Group state

`<group_state>` 值以 URDF 原生单位存储：

- revolute 和 continuous joint：弧度；
- prismatic joint：米。

当前运行时会根据 group 成员关系、fixed/mimic 状态、有限数值以及（limit 可用时）URDF limit 验证（validation） group-state 值。

## End effector

End effector 通常是连接到父 planning group 的独立工具或夹爪 group。避免 end-effector group 与父 group 之间重叠。当目标/TCP link 与推断的 group tip 不同时，请在 planning ledger 和 MoveIt2 请求设置中记录目标/TCP link。

## Disabled collision

`<disable_collisions>` 对影响规划安全。使用真实的理由：

- `Adjacent`；
- `Never`；
- `Always`；
- `Default`；
- `Setup Assistant sampled`；
- 显式手动理由。

不要从文字描述或外观生成大范围的 disabled collision 列表。

## CAD Viewer 交接（handoff）和 MoveIt2 控件

在创建或修改生成的 `.srdf` 文件后，当该 skill 可用时，将显式输出路径交给 `$cad-viewer` 以获取实时查看器链接。SRDF 不负责查看器启动。

当用户需要本地 IK 或路径规划控件时，请在 `$cad-viewer` 交接（handoff）中包含该需求。CAD Viewer 负责本地 `moveit2_server`，包括设置、环境检查、WebSocket URL 接线和协议细节。提供 SRDF 路径以及任何已知的 planning group、目标/TCP link、目标 frame、pose、起始状态和跳过的假设。

本地服务器是冒烟测试辅助工具，不能替代完整的 MoveIt 配置包。
