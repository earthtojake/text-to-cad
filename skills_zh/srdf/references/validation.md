# SRDF 验证（validation）

生成会在写入前根据其链接的 URDF 验证（validation）每个 `gen_srdf()` 结果。这能捕获许多规划语义错误，但不能替代 MoveIt Setup Assistant、MoveIt 运行时测试或 collision 矩阵采样。

生成或修改的 `.srdf` 文件在可用时应交给 `$cad-viewer` 以获取实时查看器链接。

## 当前生成时检查

当前运行时检查：

- `gen_srdf()` 返回信封字典；
- 信封字段恰好为 `xml` 和 `urdf`；
- URDF 路径相对于生成器源，使用 POSIX 分隔符，以 `.urdf` 结尾，且存在；
- SRDF XML 可解析且根为 `<robot name="...">`；
- SRDF robot name 与 URDF robot name 匹配；
- 本地 `tcad:urdf` 元数据已注入或更新，且匹配相对于生成 SRDF 的链接 URDF 路径；遗留 `explorer:urdf` 元数据仍可读；
- 至少存在一个 planning group；
- planning group 已命名且唯一；
- 每个 planning group 定义了 joint、link、chain 或 subgroup；
- group joint 名称、link 名称和 subgroup 名称存在；
- chain base/tip link 存在；
- end effector 引用已存在的父 link 和 group；
- 当提供父 group 时，end-effector group 不与其父 group 重叠；
- end-effector 父 link 在父 group 中或与 end-effector group 邻接；
- group state 引用已存在的 group；
- group-state joint 存在且在 group 展开后属于选定 group；
- group-state 值为有限值；
- group state 不设置 fixed 或 mimic joint；
- 当 limit 可用时，revolute/prismatic group-state 值在 URDF limit 内；
- disabled collision 对具有不同的 link、有效的 link 引用、非空理由，且无反向重复；
- 大量手动推理的 disabled collision 对会触发警告。

## 可选的 CAD Viewer MoveIt2 检查

当 `$cad-viewer` 为 SRDF 审查启动其本地 MoveIt2 服务器时，服务器额外检查：

- 请求 `protocolVersion`；
- 请求类型；
- 相对于仓库的 SRDF 路径和遍历安全性；
- 从 `tcad:urdf` 元数据获取的链接 URDF 路径；
- planning group 选择；
- 目标 frame 和目标 link 存在性；
- 目标姿态形状和四元数归一化；
- 仅位置 IK 一致性；
- 原生 joint 值解析；
- 遗留度数字段按 joint 类型转换；
- 规划器和 IK 设置的基本数值有效性。

## 重要的当前限制

不要将通过验证（validation）视为规划正确性的证明。当前轻量级运行时未完全验证（validation）：

- 完整的 URDF 图一致性；重复的 URDF link 或 joint 可能被浅层清点解析折叠；
- 生成时的 chain base/tip 连通性，除非 group-state 展开暴露了该问题；
- 在所有路径中将 subgroup 循环作为硬错误；
- `<virtual_joint>` 清点和验证（validation）；
- `<passive_joint>` 清点以及从所有主动 group 中排除；
- 通过采样自碰撞分析的 collision 矩阵正确性；
- 每个 group 的实际 IK 求解器可用性；
- 目标 MoveIt 环境中的实际规划成功；
- 控制器配置；
- 请求归一化之外的完整姿态约束行为。

使用 MoveIt Setup Assistant 或 MoveIt 运行时冒烟测试进行这些检查。

## 手动规划检查

生成后，验证（validation）：

### URDF 依赖

- URDF 已通过 URDF 工作流（workflow）检查。
- URDF collision 几何体适合 MoveIt collision 检查。
- 已理解主动、固定、mimic 和 passive joint。

### Planning group

- 每个 chain 具有从 base 到 tip 的真实 URDF 路径。
- 每个 group 包含预期的主动 joint，且无意外的 fixed/mimic/passive joint。
- Subgroup 不会创建模糊或循环的 group 定义。
- 选定的规划器/IK 求解器支持该 group。

### End effector

- End-effector group 和父 group 不共享 link。
- 父 link 是真实的附着点。
- 对于 pose 请求，目标/TCP link 是显式的。

### Group state

- 值使用弧度/米，而非度数。
- 值在 URDF limit 内。
- 命名状态在预期时无 collision。

### Disabled collision

- 对来自邻接关系、采样、Setup Assistant 输出或显式用户证据。
- 模型未虚构大范围禁用列表。
- 手动对已经过安全审查。

## 验证（validation）报告格式

使用紧凑报告：

```text
Checks run:
- SRDF generation validation: passed
- linked URDF validation: previously passed with URDF skill
- CAD Viewer link: returned
- MoveIt Setup Assistant review: skipped, unavailable
- CAD Viewer MoveIt2 IK smoke test: passed for manipulator/tool0
- collision matrix sampling: skipped, no MoveIt environment

Assumptions:
- Assumed tool0 is the desired TCP.
- Disabled collisions are adjacency-only.
```
