# MoveIt2 服务器

仅当用户明确需要 CAD Viewer 可选的 SRDF IK 或路径规划控件时加载本文件。普通 SRDF 评审和正常 Viewer 链接不需要 MoveIt2。

## 启动

在 `cad-viewer` 技能目录下运行：

```bash
npm --prefix scripts/viewer run moveit2:setup
npm --prefix scripts/viewer run moveit2:check
npm --prefix scripts/viewer run moveit2:serve
```

服务器默认地址为 `ws://127.0.0.1:8765/ws`。当 `VIEWER_MOVEIT2_WS_URL` 或浏览器 `?moveit2Ws=` 查询参数指向该地址时，CAD Viewer 会连接到该 URL。

使用已配置的 ROS 2 / MoveIt2 环境。不要将 ROS 2 或 MoveIt2 软件包安装到仓库的 CAD `.venv` 中。

## Viewer 控件

打开 `.srdf` 文件，展开右侧 `MoveIt2` 面板，并使用：

- Status：关联的 SRDF 与 MoveIt2 服务器状态。
- Target：规划组、末端执行器（actuator）、目标参考系（frame）以及 X/Y/Z 目标坐标。
- Solver：IK 超时、尝试次数和容差。
- Planning：规划流水线、规划器 ID、规划时间、速度缩放和加速度缩放。
- Actions：从模型选择位姿（pose）、重置到当前位姿（pose）、求解位姿（pose）或规划到位姿（pose）。

报告环境检查是否通过、位姿（pose）求解/规划是否成功，以及任何 viewer/服务器错误文本。
