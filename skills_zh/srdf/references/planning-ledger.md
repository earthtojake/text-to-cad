# SRDF planning ledger

在编写 SRDF XML 之前创建或更新此 ledger。Ledger 使规划假设显式化，有助于防止看似合理但不正确的 MoveIt 配置。

## URDF 依赖

| 字段 | 值 |
|---|---|
| URDF 路径 | |
| SRDF 输出路径 | |
| Robot name | |
| URDF 已验证（validation）？ | 是/否；工具/检查 |
| Root link | |
| 主动 joint | |
| 固定 joint | |
| Mimic joint | |
| Passive joint | |
| 用于 collision 检查的 link | |
| 已知 URDF 限制 | |

## 规划任务

| 字段 | 值 |
|---|---|
| 主要任务 | IK / plan-to-pose / 夹爪 / 移动底盘 / 双臂 / 其他 |
| 主要 planning group | |
| 预期 end-effector 或 TCP | |
| 所需求解器或规划器 | |
| 仅位置 IK？ | 是/否；原因 |
| 姿态约束？ | 是/否；表示方式 |

## Virtual joint

| 名称 | 类型 | 父 frame | 子 link | 是否必需？ | 理由 |
|---|---|---|---|---|---|
| | fixed / planar / floating | | | | |

Virtual joint 描述机器人 root 相对外部 frame 的位姿（pose）。对于固定基座机械臂，当规划设置需要 world 附着时使用 fixed；仅当机器人模型需要该规划自由度时才使用 planar/floating。

## Passive joint

| Joint | URDF 类型 | passive 原因 | 受影响的 group | 备注 |
|---|---|---|---|---|
| | | | | |

Passive joint 是未驱动的。它们不应被视为可控规划变量。

## Planning group

| Group | 表示方式 | 成员 | Base link | Tip link | 主动 joint | 排除的 joint | 用途 | 求解器预期 |
|---|---|---|---|---|---|---|---|---|
| | joint / link / chain / subgroup | | | | | | | |

对于串联臂，仅当 URDF 图中存在从 base link 到 tip link 的真实路径时才优先使用 chain。对于 subgroup group，请检查循环和重复语义。

## End effector

| 名称 | End-effector group | 父 group | 父 link | 目标/TCP link | 已检查重叠？ | 是否邻接？ | 备注 |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

End-effector group 通常不应与其父 group 共享 link。当目标/TCP link 与推断的 group tip 不同时，应显式指定。

## Group state

| 状态 | Group | Joint 值 | 单位检查 | Limit 检查 | 用途 |
|---|---|---|---|---|---|
| | | revolute/continuous 弧度；prismatic 米 | | | |

不要在 SRDF group state 中存储度数。不要在 group state 中设置 fixed 或 mimic joint。

## Disabled collision

| Link 1 | Link 2 | 理由 | 来源 | 证据 | 风险说明 |
|---|---|---|---|---|---|
| | | Adjacent / Never / Always / Default / Manual | Setup Assistant / 采样 / 邻接 / 用户 | | |

不要从视觉印象推断 disabled collision。每个对都需要理由和来源。

## MoveIt 冒烟测试

| 测试 | Group | 目标 link | 目标 pose/state | 预期结果 | 实际结果 | 备注 |
|---|---|---|---|---|---|---|
| IK 求解 | | | | | | |
| Plan-to-pose | | | | | | |
| 命名状态 | | | | | | |
| Collision 检查 | | | | | | |

## 需报告的假设

列出每个猜测或推断的值：

- planning group 成员关系；
- chain base/tip；
- 目标/TCP link；
- virtual joint 附着；
- passive joint 分类；
- group-state 值；
- disabled collision 对；
- 求解器或规划器设置；
- 姿态/仅位置 IK 假设；
- 跳过的 MoveIt 验证（validation）。
