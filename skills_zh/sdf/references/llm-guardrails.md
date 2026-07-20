# LLM 约束规则（guardrails）用于 SDF 编写

本技能假设 agent 在构建 SDFormat 文档结构方面是有用的，但在静默推导精确的空间、物理和 simulator 特定值方面是薄弱的。工作流（workflow）应当将这些弱点引导到明确的账本、常量、辅助工具、验证（validation）器和 smoke test 中。

## agent 通常能做得好的事

- 将 SDF model 或 world 组织为 link、joint、frame、visual、collision、sensor、plugin 和 include；
- 将用户意图转换为合理的文档结构；
- 当名称明确时保持命名一致性；
- 编写小型 Python generator 和 ElementTree 变换；
- 解释假设并创建检查清单（manifest）；
- 当示例在附近时保持现有模式。

## 不应信任 agent 静默推导的内容

- 精确的 link pose、frame 变换或 joint 原点；
- 从外观推断的 joint-axis 正方向；
- mesh 单位、mesh scale 或坐标系约定；
- 仅从渲染形状推断的质心或 inertia tensor；
- plugin 文件名、参数、topic、namespace 或 sensor schema；
- 某个 plugin 是 simulator 运行时 plugin 还是仅用于 CAD Viewer 可视化的扩展；
- 目标 simulator 对给定 SDFormat 版本或扩展的支持；
- collision geometry 对物理是否稳定；
- 外部 URI 在部署环境中是否能解析。

## 必需的缓解模式

对于每个空间、物理或 simulator 特定的值，使用以下来源之一：

1. 用户提供的需求；
2. 上游 geometry、robot-description、planning-metadata、mesh 清单（manifest）或 model 包源；
3. 目标 simulator 文档；
4. 声明方法的测量或计算值；
5. 记录在 generator envelope、设计账本或最终报告中的明确假设。

不要将猜测的值隐藏在原始 XML 中。

## 占位符策略

仅当用户要求 scaffold、草稿或最小示例时才允许使用占位符。将它们标记为占位符，并保持易于替换。

可接受的占位符示例：

```python
return {
    "xml": sdf,
    "assumptions": [
        {
            "code": "placeholder_inertial",
            "message": "Inertial tensor uses a primitive approximation pending measured mass properties.",
        }
    ],
}
```

不可接受的占位符示例：

- 虚构的 plugin 文件名；
- 向 SDF 文件添加仅用于 CAD Viewer 的 motion plugin；
- 在没有警告的情况下对动态机器人使用任意 inertia 值；
- 猜测的 mesh scale 使外观看起来合理；
- 静默翻转 joint axis 以匹配预期的截图。

## 空间推理检查清单（manifest）

在生成或修改 SDF 之前，在账本或最终报告中回答这些问题：

| 问题 | 必需的证据 |
|---|---|
| 每个 pose 是在哪个 frame 中表达的？ | `relative_to`、源文件或已记录的默认值 |
| 每个 joint axis 是在哪个 frame 中表达的？ | `expressed_in` 或已记录的默认值 |
| 每个非固定 joint 的正向运动是什么？ | 命令/测试期望或上游源 |
| mesh 单位和 scale 是否已知？ | 清单（manifest）、CAD 导出配置或明确假设 |
| visual 和 collision 的 pose 是否有意不同？ | 仿真原因或源 geometry |
| inertials 是测量的、计算的、近似的还是省略的？ | 方法和置信度 |
| plugin 和 sensor 参数是否从目标文档复制？ | 目标 simulator/版本和来源 |

## 代码生成风格

推荐此模式：

```python
BASE_TO_CAMERA_XYZ_M = (0.18, 0.0, 0.12)
BASE_TO_CAMERA_RPY_RAD = (0.0, -0.2, 0.0)
CAMERA_FRAME = "camera_frame"

# 来源：项目 CAD frame 导出 2026-05-12。RPY 弧度。
pose(camera_frame, BASE_TO_CAMERA_XYZ_M, BASE_TO_CAMERA_RPY_RAD, relative_to="base_link")
```

避免此模式：

```python
ET.SubElement(camera, "pose").text = "0.18 0 .12 0 -11.5 0"
```

第二个版本隐藏了单位，使用了未声明的 degrees，并且使变换的来源无法审计。

## 验证（validation）期望

验证（validation）器应当捕获低成本的确定性错误，但它无法证明设计在物理上或 simulator 上是正确的。在内置验证（validation）之后，当任务依赖于 simulator 行为时，使用可选的外部检查和 simulator smoke test。

明确报告跳过的检查。跳过的检查不自动视为失败，但它是相关的风险信息。

## agent 的响应行为

完成 SDF 任务时，说明：

- 源 generator 路径和生成的目标路径；
- 运行的检查及其结果；
- 跳过的检查及原因；
- 假设和占位符；
- 需要 simulator 验证（validation）的风险。

不要简单地说文件是有效的。说明哪个验证（validation）器或 smoke test 通过了。
