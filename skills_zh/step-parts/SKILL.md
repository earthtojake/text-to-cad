---
name: step-parts
description: 从 step.parts 查找、评估并下载常见可采购 CAD 零件（part），包括具名的现货执行器（actuator）、舵机（servo）、电机、电子板、连接器、螺丝、螺栓、螺母、垫圈、轴承（bearing）、支柱（standoff）以及其他目录元件。当 Codex 需要在创建简化的占位几何体之前搜索托管的 step.parts 目录、解析模糊的零件（part）名称/标准/别名/尺寸、选择匹配的零件、获取规范的 .step 文件、校验校验和，或使用 step.parts API/OpenAPI/目录端点进行标准零件（part）发现时使用本技能。
---

# CAD 零件（part）

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
使用已安装的本地技能文件作为运行时真相来源；仓库链接仅用于溯源与发布审查。

## 概述

使用托管的 step.parts 机器端点，而不是抓取 HTML 或依赖本地仓库文件。除非用户提供不同的托管镜像，否则将 `https://api.step.parts` 视为规范的 API 源，将 `https://www.step.parts` 视为站点/静态资源源。网络/DNS 故障不具有结论性：如果无法从沙箱访问 `api.step.parts`，在报告未命中或使用占位几何体之前，先在网络权限下重试一次。除非 API 可访问且未返回相关候选结果，否则不要将零件（part）描述为不可用。

当 CAD 装配体（assembly）包含具名的现货执行器（actuator）、舵机（servo）、电机、电子板、连接器或其他可采购元件时，在创建简化的占位几何体之前先搜索 step.parts。对于具名的舵机（servo）、电机和执行器（actuator），在放弃之前应同时搜索精确型号字符串和常见别名/厂商拼写。例如，`STS3215` 也可能以 `ST3215`、`3215`、`Waveshare Feetech ST3215` 出现，或位于 `family=feetech` 之下。如果 API 可访问但没有精确或近似匹配的结果，则记录该搜索未命中，然后使用文档化的包络或简化的替代件。

## 快速工作流（workflow）

1. 将请求的零件（part）解释为搜索词和可选的分面（facet）：
   - `q` 用于模糊词元、标准、别名、尺寸、来源/产品 URL 以及属性名/值。
   - 当用户给出精确分面时使用 `category`、`family`、`standard` 或 `tag`。
2. 搜索 `/v1/parts` 并检查 `items`、`total` 和 `facets`。对于执行器（actuator）型号，在将空结果视为未命中之前，重试可能的别名、被省略的字母、厂商名称以及相关的 family 分面。
3. 如果结果不明确，在选择之前展示最佳的几个选项及其 `id`、`name`、`standard` 和关键属性。如果某个结果明显匹配，则返回所选记录的详细信息而不下载，除非用户要求本地 STEP 文件。
4. 当找到精确或近似的现货执行器（actuator）型号时，优先下载并使用其 STEP 文件，除非有明确的装配时理由使用简化的包络。显式记录该选择。
5. 当用户要求下载或保存 STEP 文件时，下载其 `stepUrl`，然后当记录中存在 `sha256` 时使用该值校验文件。
6. 下载后返回本地路径，以及所选的零件（part） id 和页面/API URL，以便用户可追溯来源。

## CAD 查看器交接（handoff）

在完成创建或更新本地 `.step` 或 `.stp` 文件的 step.parts 工作后，当 `$cad-viewer` 技能已安装时，你必须始终将显式文件路径交接（handoff）给 `$cad-viewer`。`$cad-viewer` 必须在尚未运行时启动 CAD 查看器，并返回相关已创建或已更新文件的链接；如果 `$cad-viewer` 不可用或启动失败，则报告该情况，而不是静默省略交接（handoff）。

## 内置下载器

使用 `scripts/download_step_part.py` 进行确定性的搜索、下载和校验和验证（validation）：

```bash
python scripts/download_step_part.py "M3 socket head 12" --download
python scripts/download_step_part.py --id iso4762_socket_head_cap_screw_m3x12 --download
python scripts/download_step_part.py "bearing 608zz" --limit 5
```

常用选项：

- `--origin`：仅当用户提供另一个托管 API 源时，覆盖 `https://api.step.parts`。
- `--tag`、`--category`、`--family`、`--standard`：可重复的分面过滤器。
- `--out-dir`：当用户要求特定目标位置时，覆盖下载目录。
- `--all`：与 `--download` 一起使用时，将返回页面上的每个结果作为独立的 STEP 下载。
- `--overwrite`：替换已有的输出文件。

脚本将 JSON 打印到标准输出。对于搜索，它打印匹配的记录。对于下载，它打印保存的文件路径、校验和和来源 URL。

## API 参考

当你需要端点详细信息、字段含义或查询语义时，阅读 `references/step-parts-api.md`。优先使用：

- `/v1/parts` 进行带绝对资源 URL 的过滤搜索。
- `/v1/parts/{id}` 获取单个富化记录。
- 返回的 `stepUrl` 用于 STEP 下载。
- `/v1/catalog/parts.index.json` 用于紧凑的发现索引。
- `/v1/catalog/schema` 用于字段和 family 属性含义。
- `/v1/openapi.json` 用于生成客户端或工具时。

## 搜索指南

- 查询词元由 API 进行 AND 运算，因此从具体但不过度约束开始。例如，在添加精确的 family 和 standard 过滤器之前，先使用 `M3 SHCS 12`。
- 单个分面内的值进行 OR 运算，而选定的 `tag`、`category`、`family` 和 `standard` 字段之间进行 AND 运算。使用精确分面在已知类别内缩小范围，然后按名称和属性手动排序。
- 标准可以以 `ISO 4762`、`ISO4762` 或精确的 `standard.designation` 形式查询。
- `attributes` 对象包含特定于 family 的事实，例如 `thread`、`lengthMm`、`bore1Mm`、`material`、`profileSeries`、`slotSizeMm` 以及以毫米为单位的尺寸。
- 零件、GLB 和 PNG URL 模式在 `https://www.step.parts` 上是可预测的；STEP URL 是环境感知的，在生产环境可能解析为 GitHub LFS 媒体。使用目录/API 的 `stepUrl` 进行下载。
