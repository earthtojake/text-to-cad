# SDF 互操作性说明

当 SDF 工作涉及上游 geometry、robot-description 数据、Gazebo/libsdformat、model 包或 CAD Viewer 时，请使用本参考。

## 几何资产

SDF 应当引用 geometry 和 mesh 资产，而不应重新生成它们。

当 SDF 引用生成的 mesh 时，记录：

- 源 geometry 文件；
- 导出的 mesh 路径；
- mesh 单位约定；
- mesh 原点约定；
- visual scale；
- collision 简化决策。

如果 geometry 发生变化，在重新生成 SDF 之前，先用拥有这些资产的工作流（workflow）重新生成 geometry 和 mesh 产物（artifact）。

## 机器人描述

当存在上游 robot-description 源时，保持 simulator 文档与之一致。

上游 robot-description 数据通常拥有：

- robot-state 发布使用的 link 和 joint 结构；
- 物理 joint limits；
- 当该源为权威源时的 inertials 和 visual/collision geometry；
- 与控制相关的结构和运行时接口。

将 SDF 用于 simulator/world 相关事项：

- simulator plugin；
- 需要 simulator 特定 XML 的 sensor；
- surfaces/contact/friction；
- 灯光、地形、物理和 world；
- nested model 和 include；
- simulator 特定的元数据。

不要用 SDF 掩盖错误的上游 frame 树，除非任务明确针对 simulator-only model。

## 规划元数据

SDF 不应定义规划组、end-effector、组状态或 disabled-collision 矩阵。如果任务变为 IK 或路径规划工作，请使用拥有这些语义的 planning metadata 工作流（workflow）。

## CAD Viewer

CAD Viewer 可以通过 `$cad-viewer` 可视化地审查 `.sdf` 文件，并帮助发现明显的放置或资源问题。它无法证明 simulator 动力学、inertial 有效性、plugin 加载、sensor topic 或 joint-axis 语义。

只要 `$cad-viewer` 可用，就将明确生成或修改的 `.sdf` 路径传递给它，并返回它打印的实时查看器链接。

CAD Viewer 将 SDF 渲染为静态结构并提供直接检查控件。它将 plugin、sensor、灯光、include 和 nested model 列为元数据，但不执行 plugin 或使用文件编写的 motion contract。

## Gazebo / libsdformat

内置验证（validation）器是轻量级的预检。当兼容性很重要时，请使用目标 simulator 的解析器和加载器。

良好的检查包括：

```bash
gz sdf --check path/to/model.sdf
```

以及在目标环境中进行真正的 simulator 加载。

## Model 包和 URI

SDF 资源解析依赖于环境。记录目标消费者可以解析哪些 URI 形式：

- 从生成的 `.sdf` 位置开始的相对路径；
- simulator model 路径下的 `model://` 路径；
- ROS/package 解析下的 `package://` 路径；
- `fuel://` 资源；
- 如果允许外部获取，则包括 `http://` 或 `https://` 资产。

内置验证（validation）器可以确认本地相对路径，但除非目标环境可用，否则无法证明外部 simulator 资源路径有效。
