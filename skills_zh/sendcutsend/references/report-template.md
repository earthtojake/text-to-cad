# SendCutSend 验证（validation）报告模板

当用户要求审查、验证（validation）、预检或制造就绪报告时，使用此结构。

## 上下文

- 文件：`<path>`
- 假定服务：`DXF laser sheet cutting` 或 `STEP CNC routing`
- 订单上下文：材料、厚度、主要工艺、表面处理、数量、二级操作
- 检查日期：`<YYYY-MM-DD>`

## 已检查来源

以 Markdown 链接列出用于检查的官方 SendCutSend URL。仅包含实际查阅的来源。如有，包含访问日期和 JSON `_meta.generated_at` 值。发现表格还必须为每行链接具体规则来源，因此本节是文献目录，不能替代行级引用。

## 几何事实

总结来自 `$cad` 检查（如有）和针对性 `build123d`/`ezdxf` 检查代码的事实：文件类型、单位、范围/边界框、实体/体计数、图层、不受支持的实体、明显的开放/重复几何，以及解析限制。

如果审查的上传文件在本工作流（workflow）中生成或更新，如有则包含 `$cad-viewer` 查看器链接。

对于折弯 2D 文件，包含来自导出文件的折弯几何事实：折弯线计数和图层、各折弯线长度、每条折弯线最近的非折弯切割几何、局部法兰（flange）深度、折弯线跨度覆盖、折弯相邻切割几何、接触/支撑不足观察，以及任何分割/打断/共轴折弯观察。使用这些事实与当前材料/厚度服务页进行比较。

对于折弯 STEP/STP 文件，包含测量的板材厚度（如有）和提取的折弯半径集。仅当订单上下文已知时，才将折弯半径与所选材料/SKU 比较。

## 发现

每个问题一行。在 `Rule source` 中，链接定义所检查要求的具体官方页面或 JSON 文件，源为 JSON 时包含字段路径。示例：`[sendcutsend-specs.json](https://cdn.sendcutsend.com/specs/sendcutsend-specs.json) materials[sku=ALU-063].cutting_specs.min_hole_size`。优先使用精确 SKU 专属来源而非通用指南文本。如无外部规则适用，写 `Direct file inspection`。

| 状态 | 检查 | 证据 | 规则来源 | 建议 |
| --- | --- | --- | --- | --- |
| ✅ pass / ❌ fail / ❓ need more info | 要求名称 | 文件事实 | 指向具体规则文档/表格的 Markdown 链接，或 `Direct file inspection` | 具体的后续行动 |

## 结论

使用有限的结论：

- `Ready to upload for this assumed context`
- `Needs edits before upload`
- `Insufficient context to validate`

如果任何要求的当前官方要求检查标记为 `❌ fail` 或 `❓ need more info`，绝不使用就绪结论。仅当每个要求的引用检查都有足够的订单上下文、源证据、测量文件事实并通过或明确不在所选服务范围内时，才使用 `Ready to upload for this assumed context`。在显式 SendCutSend UI 分类模型被有意添加之前，将测量的上传风险和可制造性问题视为 `❌ fail`。
