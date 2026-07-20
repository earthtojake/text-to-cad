# SRDF end effector

在创建或编辑 `<end_effector>` 条目或为 `$cad-viewer` 准备 MoveIt2 pose-target 交接（handoff）时使用此参考。

## 概念

End effector 是对工具、夹爪、传感器头部或其他终端 group 的语义指定。它通常通过固定 joint 或附着 link 连接到父 planning group。

典型形式：

```xml
<group name="gripper">
  <joint name="finger_joint"/>
</group>

<end_effector
  name="gripper_eef"
  parent_link="tool0"
  group="gripper"
  parent_group="manipulator"/>
```

## 必需的 ledger 字段

记录：

- end-effector 名称；
- end-effector group；
- 父 planning group；
- end effector 附着的父 link；
- 用于 IK 和规划的目标/TCP link；
- end-effector group 是否与父 group 重叠；
- 父 link 在 URDF 图中是否与 end-effector group 邻接。

## 检查

生成前：

- end-effector group 存在。
- 指定时父 group 存在。
- 父 link 存在于 URDF 中。
- end-effector group 和父 group 不共享 link。
- 父 link 在父 group 中或与 end-effector group 邻接。
- 当目标/TCP link 与推断的 group tip 不同时，应显式指定。

当前运行时强制执行其中若干检查，但目标/TCP 选择仍是语义决策。在规划到工具中心点（tool center point）时不要依赖推断。

## CAD Viewer MoveIt2 目标 link

当将 SRDF 交给 `$cad-viewer` 进行可选的 MoveIt2 控件时，尽可能使预期目标 link 显式：

```json
{
  "protocolVersion": 1,
  "type": "srdf.solvePose",
  "payload": {
    "file": "robot.srdf",
    "target": {
      "endEffector": "gripper_eef",
      "targetLink": "tool0",
      "frame": "base_link",
      "xyz": [0.4, 0.0, 0.2],
      "quat_xyzw": [0, 0, 0, 1]
    },
    "moveit2": {
      "planningGroup": "manipulator",
      "targetLink": "tool0"
    }
  }
}
```

仅当有意不约束姿态时才使用仅位置 IK。CAD Viewer 负责本地 MoveIt2 服务器启动和协议细节。
