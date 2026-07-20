# SDF 工作流（workflow）

当编辑 SDF 机器人 model 结构、world 结构、mesh 引用、simulator 元数据或生成的 SDF 输出时，请使用本参考。

## 编辑循环

1. 找到定义 `gen_sdf()` 的 Python 源码。
2. 将该源码视为权威。除非明确指示，否则不要手动编辑生成的 `.sdf` 输出。
3. 确定目标消费者和所需的 SDFormat 版本。
4. 决定输出是 model 级别、world 级别还是 model-in-world。
5. 在编写 XML 之前填写或更新设计账本。
6. 对于每个 pose 和 axis，说明它所表达的 frame。在仍有歧义的地方使用 `relative_to` / `expressed_in`。
7. 编辑 generator 源码。
8. 仅重新生成明确的目标。
9. 将内置验证（validation）错误视为结构性约束规则（guardrails），而非详尽的 simulator 证明。
10. 当可用时，将生成或修改的 `.sdf` 文件交给 `$cad-viewer` 以获取实时查看器链接。
11. 运行可用的 smoke test。
12. 报告假设和跳过的检查。

## Model 与 world

当导出一个可被其他 world include 的可重用机器人或对象 model 时，使用 **model-level SDF**。

当任务包括以下内容时，使用 **world-level SDF**：

- 物理引擎设置；
- 灯光或场景设置；
- 地形或地面平面；
- 多个初始 model 放置；
- world plugin；
- 外部 model 包的 include；
- simulator 场景设置。

当任务明确需要内联 model 和 world 特定上下文时，使用 **model-in-world SDF**。

轻量级验证（validation）器应当允许纯 world 文档。带有灯光、物理、actor 或 include 的纯 world 文档即使不包含内联 `<model>`，也可以是有效的 SDFormat。

## Mesh 引用

SDF mesh URI 应当从生成的 `.sdf` 文件的角度保持稳定，或使用消费者理解的 simulator/package URI 约定。

良好的 URI 选择包括：

- 当 model 是自包含时，使用生成 SDF 旁边的相对路径；
- 用于 simulator model 包的 `model://...`；
- 当 simulator 环境解析 package 根目录时的 `package://...`；
- 仅当预期消费者会获取外部资产时才使用 `fuel://...`、`http://...` 或 `https://...`。

不要将生成的 SDF XML 作为 mesh 放置的事实来源。优先从拥有 mesh 实例放置的相同源数据派生 visual 和 collision mesh 引用。

## Inertials 和物理

对于动态 model，inertial 数据对仿真至关重要。如果 inertials 是估计的，记录近似方法。除非物理上合理，否则不要将 visual 原点复制到 inertial 原点。

应当为稳定且快速的物理选择 collision geometry，而非视觉保真度。尽可能使用基本几何体或简化的 collision geometry。

## Plugin 和 sensor

对于 plugin 和 sensor，记录：

- plugin 文件名或 sensor 类型；
- 预期的 simulator 发行版/版本；
- topic、frame、update rate、namespace；
- 参数来源；
- 启动 smoke test 结果。

不要虚构 plugin 参数。不正确的 plugin XML 可以通过轻量级验证（validation），但仍可能在 simulator 加载时失败。

CAD Viewer 通过 `$cad-viewer` 链接将 SDF 文件作为静态 model/world 结构进行审查。不要添加 Explorer-only 的 motion plugin；对于 simulator 行为，使用 simulator 原生的控制器、plugin 或测试工具。

## 现有 SDF 检查

在检查现有 `.sdf` 文件时，区分三个问题：

1. XML 是否足够结构化有效以通过内置验证（validation）器？
2. 它是否与目标 SDFormat/libsdformat/simulator 版本兼容？
3. 它是否满足本项目的打包、mesh 和工作流（workflow）策略？

不要仅仅因为 SDF 违反了项目偏好就拒绝有效的 SDF，除非任务或仓库策略要求该偏好。
