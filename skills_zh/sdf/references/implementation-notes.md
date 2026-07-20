# SDF 实现说明

这些说明描述了重写后预期的运行时形态。当实现发生变化时，请保持本文件准确。

## 已实现的行为

SDF 技能应当：

- 仅生成明确的目标；
- 在写入前验证（validation）生成的 XML；
- 保留现有的 `gen_sdf()` 返回兼容性：XML element、XML string 或带 `xml` 的 envelope dict；
- 接受 envelope 的 `assumptions`、`warnings` 和 `metadata` 字段；
- 支持 `--strict` 的"警告视为失败"行为；
- 通过 `--gz-check auto|required|never` 可选地运行 `gz sdf --check`；
- 提供可选的仅依赖 stdlib 的编写辅助工具；
- 从文件或内存中的字符串解析 SDF XML；
- 相对于生成的输出位置解析本地 mesh 文件；
- 接受外部 mesh URI 方案，无需本地文件系统解析；
- 在结构有效时允许纯 world 文件。

## 预期的内置验证（validation）范围

内置验证（validation）器应当检查常见的结构和数值错误：

- root element 和 version；
- 文档形状和纯 world 支持；
- 本地 scope 中必需的名称和重复的名称；
- pose 值数量、rotation 格式、有限值、degrees 使用情况、四元数归一化，以及本地 `relative_to` 解析；
- 命名 frame 的附着引用和环；
- joint 类型集合、parent/child 引用、axis/axis2 值、limits 和 dynamics 数值；
- visual/collision 拥有者名称和 geometry 是否存在；
- 基本几何体尺寸和 mesh URI/scale；
- 本地 mesh 路径是否存在；
- inertial 的 mass 和 inertia tensor 合理性；
- sensor 的 name/type/update-rate 结构；
- plugin 的 name/filename 结构。

## 剩余限制

内置验证（validation）器仍不是完整的 libsdformat 或 simulator 验证（validation）器。它不应声称能够完整验证（validation）：

- 每个版本特定的 SDFormat schema 规则；
- 所有 nested-model 的 frame 语义；
- 变换数学或已解析的 pose；
- mesh 单位约定；
- 任意的 mesh inertia 或 collision 质量；
- simulator 特定的物理设置；
- plugin schema 和运行时可用性；
- sensor 运行时行为；
- 目标 simulator 对每个 element 的支持。

使用设计账本、结构化诊断、`gz sdf --check`、simulator 加载测试，并明确报告跳过的检查。

## 执行安全

当前的启动器在进程内导入 generator 模块。generator 的 Python 文件会执行代码，必须是受信任的项目源码。
