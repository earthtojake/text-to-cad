# 官方 SendCutSend 来源映射

将这些来源视为实时证据，而非稳定 API。字段覆盖、值类型和 `N/A` 用法可能变化。在做出通过/失败声明前，引用确切的源 URL，对于 JSON 事实，引用使用的字段路径。

## 核心入口

- 下单指南：https://cdn.sendcutsend.com/specs/sendcutsend-ordering-guide.md
- 目录 JSON：https://cdn.sendcutsend.com/specs/sendcutsend-catalog.json
- 工程规格 JSON：https://cdn.sendcutsend.com/specs/sendcutsend-specs.json

每次审查前直接获取这些 URL。使用当前响应体作为材料/服务检查的证据，并在报告中引用 URL 和访问日期。

## 来源角色

- 下单指南：用于下单流程、接受的文件格式、通俗语言设计规则和通用服务说明。
- 目录 JSON：用于可订购性事实，如材料 SKU、材料名称、厚度、库存状态、切割工艺、最小/最大零件（part）尺寸、可用服务、硬件项和表面处理选项。
- 工程规格 JSON：用于以 SKU 为键的设计验证（validation）事实，如公差、最小孔/桥接/边缘值、折弯参数、攻丝、锪孔（countersink）、硬件压装、冲压成型、表面处理限制和材料属性。

## 需捕获的溯源信息

- 源 URL
- 访问日期
- JSON `_meta.schema_version`
- JSON `_meta.generated_at`
- JSON `_meta.source_data_generated_at`（如有）
- 行级引用的字段路径，如 `sendcutsend-specs.json materials[sku=ALU-063].cutting_specs.min_hole_size`

## 冲突处理

优先使用目录和规格间的精确 SKU 关联。如果源事实冲突或某字段缺失、无法解析或为 `N/A`，报告不确定性并将依赖行标记为 `❓ need more info`，除非另一个更具体、已引用的源解决了它。

对源事实使用以下优先级：

1. 材料/厚度/服务专属配置器或当前报价/上传结果
2. 工程规格 JSON 中的精确 SKU 条目
3. 目录 JSON 中的精确 SKU 条目
4. 下单指南
5. 更广泛的官方 SendCutSend 人类可读页面，仅当三个源文件不足时

记录冲突及所依赖的页面。
