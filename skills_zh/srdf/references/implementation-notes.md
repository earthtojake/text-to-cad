# SRDF 实现说明

这些说明描述了当前运行时的形态，以便文档不会夸大代码所强制执行的内容。

## 当前代码中已实现

- `scripts/srdf` 仅生成显式目标。
- `gen_srdf()` 必须返回包含 `xml` 和 `urdf` 的信封。
- 生成的 SRDF 在写入前会根据链接的 URDF 进行验证（validation）。
- CLI 注入或更新本地 `tcad:urdf` 元数据。
- Group state 使用 `joint_values_by_name` / `jointValuesByName`，单位为 URDF 原生单位。
- 已弃用的 `joint_values_by_name_rad` / `jointValuesByNameRad` 别名保留以兼容。
- Group-state 值会检查 group 成员关系、有限值、fixed/mimic 状态以及（可用时）URDF limit。
- End-effector 重叠和邻接检查已实现。
- Disabled-collision 理由是必需的，并分类为宽泛的来源类别。
- 可选的 CAD Viewer MoveIt2 控件使用 `protocolVersion: 1`。
- Pose target 支持 `quat_xyzw` 和 `rpy`。
- 仅位置 IK 在请求设置中是显式的，默认值基于是否提供了姿态。
- 遗留度数字段按 joint 类型转换，因此 prismatic 值保持线性。
- 错误响应会清理绝对路径，除非启用了调试错误。

## 代码中尚未完全实现

以下内容仍为流程要求和未来代码改进目标：

- 与 URDF skill 共享的完整 URDF 结构验证（validation）；
- virtual joint 解析和验证（validation）；
- passive joint 解析以及从主动规划变量中排除；
- 在所有情况下对断开连接的 chain base/tip 定义的硬失败；
- subgroup 环检测作为一等验证（validation）错误；
- 类型化 SRDF 生成辅助工具；
- 结构化假设/警告信封字段；
- 采样自碰撞（collision）矩阵生成；
- 完整 MoveIt 配置包生成；
- 在子进程中更安全地执行生成器。

在这些实现之前，请依赖 planning ledger、MoveIt Setup Assistant、可用时 `$cad-viewer` 交接（handoff）进行可视化/MoveIt 冒烟测试，以及显式报告跳过的检查。
