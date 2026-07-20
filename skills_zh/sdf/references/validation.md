# SDF 验证（validation）

生成过程在写入前验证（validation）每个 `gen_sdf()` 结果。此验证（validation）是依赖轻量的，旨在捕获常见的结构错误。它不能替代 libsdformat、Gazebo 或目标 simulator 的验证（validation）。

## 验证（validation）模型

验证（validation）器应当生成带有严重级别的结构化诊断：

- `error`：无效或不安全到足以阻止写入输出；
- `warning`：可能的问题或未验证（validation）的 simulator 行为；除非使用 `--strict`，否则可以写入输出；
- `info`：假设、跳过的检查或有用的上下文。

`--strict` 将警告视为失败。

## 内置检查

### Root 和文档形状

运行时应当检查：

- root element 是 `<sdf>`；
- root 具有非空的 `version` 属性；
- version 看起来像 `major.minor`；
- 文档包含有意义的 SDF 内容，如 model、world、actor、light、include 或 plugin；
- 即使不包含内联 model，结构有效的纯 world 文件也被接受。

### 名称和 scope

运行时应当检查：

- world 名称非空且在 root scope 中唯一；
- root model 名称非空且唯一；
- model 的 link、joint、frame、sensor、visual 和 collision 名称在需要时非空，且在其拥有者 scope 中唯一；
- 重复的名称附带路径和 scope 报告。

### Pose

运行时应当检查所有 `<pose>` element：

- 默认 `rotation_format="euler_rpy"` 恰好有六个有限值；
- `rotation_format="quat_xyzw"` 恰好有七个有限值；
- 不支持的 `rotation_format` 是错误；
- 四元数值近似归一化；
- 除非启用了 strict 模式，否则 `degrees="true"` 是警告；
- 非平凡的省略 `relative_to` 是警告；
- `relative_to` 尽可能在本地 scope 内解析；
- nested `::` 引用具有有效语法，并在本地树可用时解析。

### Frame

运行时应当检查：

- `<frame name="...">` 在其 scope 中具有非空唯一名称；
- `attached_to` 存在时，尽可能在本地解析；
- frame 附着链不形成环；
- 当本地验证（validation）无法证明其无效时，未解析的 nested 或外部 frame 引用作为警告报告。

### Joint

已知的 SDF 1.12 joint 类型：

```text
continuous, revolute, gearbox, revolute2, prismatic, ball, screw, universal, fixed
```

运行时应当检查：

- joint 类型非空且已知；
- `<parent>` 和 `<child>` 文本存在；
- `world` 允许作为 parent 但不允许作为 child；
- 未限定 scope 的 parent/child 引用在同一 model 中存在；
- `axis` 和 `axis2` 向量是有限的、非零的且归一化的；
- `axis2` 仅在 joint 类型支持第二个 axis 时使用；
- `expressed_in` 在本地解析可能时解析；
- limit 和 dynamics 值是有限的或 SDFormat 允许的已记录无穷大；
- 有限的 lower limit 不超过有限的 upper limit；
- 带有虚假有限位置 limit 的 continuous joint 产生警告。

### Geometry 和 mesh URI

运行时应当检查：

- 每个 visual/collision 拥有者有一个 geometry element；
- 每个 geometry 尽可能只有一个已知的基本几何体或 mesh child；
- box size 有 3 个正有限值；
- cylinder radius 和 length 是正且有限的；
- sphere radius 是正且有限的；
- plane size 有 2 个正有限值；
- mesh URI 值非空；
- mesh scale 存在时有 3 个正有限值；
- 本地 mesh 引用相对于生成的 `.sdf` 位置解析；
- 已知的外部 URI 方案如 `model://`、`package://`、`fuel://`、`http://` 和 `https://` 无需本地文件系统解析即可接受。

### Inertials

运行时应当检查：

- mass 是正且有限的；
- inertial pose 存在时有效；
- inertia tensor 分量是有限的；
- inertia matrix 在容差范围内是半正定的；
- 动态物理 link 上缺失 inertial 数据至少是警告；
- 类 frame 或静态 link 在有文档记录时可以省略 inertials。

### Sensor 和 plugin

运行时应当检查：

- sensor 名称非空且在拥有者 scope 中唯一；
- sensor `type` 非空；
- sensor `update_rate` 存在时是有限且非负的；
- sensor pose 有效；
- plugin 文件名非空；
- plugin name 存在时非空；
- 验证（validation）器不虚构任意的 simulator 特定 plugin schema。

Plugin 文件名和参数可以通过内置验证（validation），但仍可能在目标 simulator 中失败。使用 smoke test。

### CAD Viewer 审查

CAD Viewer 将 SDF plugin、sensor、灯光、include 和 nested model 视为静态元数据。内置验证（validation）器仅检查通用结构；它不验证（validation） Explorer-only 的 motion contract 或执行 simulator plugin。

在生成 `.sdf` 文件创建或修改后，当可用时将明确路径交给 `$cad-viewer` 以获取实时查看器链接。

此 plugin 用于 CAD Viewer 可视化和审查。它不是 Gazebo 物理/控制器 plugin，不应表示为 simulator 运行时行为。

## 外部检查

当 Gazebo 工具可用时，运行：

```bash
gz sdf --check path/to/file.sdf
```

CLI 选项应当是：

```bash
python scripts/sdf path/to/source.py --gz-check auto
```

外部检查应当记录在诊断报告中。跳过的可选检查不是内置验证（validation）失败，除非用户请求了 `--gz-check required`。

## SDF 有效性 vs 项目策略

区分以下类别：

| 类别 | 示例 |
|---|---|
| SDF 结构有效性 | root `<sdf>`、version、合法 element 形状、非空名称、引用 |
| 数值合理性 | 有限 pose、正尺寸、正 mass、归一化 axis、PSD inertia |
| Simulator 兼容性 | libsdformat 版本、支持的 joint 类型、plugin 可用性、sensor 支持 |
| 项目策略 | mesh 位置、首选 URI 风格、STL/DAE 偏好、collision 简化、无未解析的外部 URI |

不要仅仅因为 SDF 违反了项目策略就拒绝有效的 SDF，除非任务或仓库要求该策略。优先使用警告和 strict 模式控制。
