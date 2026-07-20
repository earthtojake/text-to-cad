# SDF smoke test

在生成的 SDF 通过内置验证（validation）后使用 smoke test。目标是捕获依赖轻量的 XML 检查无法检测的 simulator 和空间故障。

## 推荐的检查

### 内置验证（validation）

```bash
python scripts/sdf path/to/model.py
python scripts/sdf path/to/model.py --strict
```

内置验证（validation）在显式目标生成期间运行。当警告应阻止交付时使用 `--strict`。

### SDFormat 解析器检查

当安装了 Gazebo 工具时：

```bash
gz sdf --check path/to/model.sdf
```

或通过技能 CLI：

```bash
python scripts/sdf path/to/model.py --gz-check auto
```

尽可能使用将使用该文件的精确 simulator 环境。

### Simulator 加载检查

在目标 simulator 中加载 model 或 world，并检查：

- 没有解析器警告或 plugin 加载错误；
- model 出现在预期的 pose；
- visual 和 collision 资产能够解析；
- collision geometry 没有相对于 visual 明显偏移；
- 动态 model 不会爆炸、穿过地板或产生无效 inertia 警告。

### Joint 运动检查

对于每个非固定 joint：

- 命令一个小的正向运动；
- 确认移动的 child 按预期方向移动；
- 确认 limits 在预期位置停止运动；
- 确认 continuous joint 如果有意为之可以连续旋转。

### CAD Viewer 静态审查

在生成或修改 `.sdf` 之后，当可用时将明确路径交给 `$cad-viewer` 以获取实时查看器链接。

- 确认直接的 model link、joint、frame、visual 和 collision 放置正确；
- 确认 include、plugin、sensor、灯光、nested model 和不支持的 geometry 列为静态元数据；
- 记录 CAD Viewer 无法执行的任何 simulator-only 行为。

### Sensor 和 plugin 检查

对于每个 sensor 或 plugin：

- 确认 plugin 库能加载；
- 确认预期的 topic/service 出现；
- 确认 frame 名称与设计账本匹配；
- 确认 update rate 和 namespace 行为；
- 如果可行，捕获一个样本输出。

### 可视化审查

当通过 `$cad-viewer` 可用 CAD Viewer 或等效查看器时，返回查看器链接。可视化审查是有用但不充分的：它可以发现明显的放置和 mesh 问题，但无法证明 axis frame、inertials、dynamics 或 plugin 行为。

## 报告格式

使用简洁的报告：

```text
Checks run:
- bundled SDF validation: passed
- gz sdf --check: skipped, gz not installed
- simulator load: passed in Gazebo Harmonic
- joint motion: shoulder_pan positive motion verified; gripper joints skipped
- plugin startup: camera plugin unresolved, requires target simulator package

Assumptions:
- Assumed mesh units are meters.
- Assumed lidar frame is coincident with lidar_link.
```

## 何时停止

在以下情况下停止并修复 generator：

- 内置验证（validation）有错误；
- 在必需的外部检查策略下 `gz sdf --check` 失败；
- simulator 报告无效 inertia 或无法解析的必需资产；
- joint 朝与文档记录的正方向相反的方向运动；
- 任务所需的 plugin 启动失败。
