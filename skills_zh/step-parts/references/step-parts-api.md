# step.parts API 参考

## 源

默认使用 API 源 `https://api.step.parts`。仅当用户提供另一个托管的 step.parts 兼容 API 域时才使用不同的源。静态 HTML 页面位于 `https://www.step.parts`；API 记录中的 GLB 和 PNG 预览 URL 直接指向 Vercel Blob。STEP URL 是环境感知的，生产记录使用提交锁定的 GitHub LFS 媒体。如果 API 域无法解析，则将托管服务视为不可用，并在需要实时下载时要求提供已部署的源。

## 机器端点

| 端点 | 用途 |
| --- | --- |
| `https://www.step.parts/llms.txt` | 人类可读的代理指南，包含端点摘要和示例。 |
| `/v1/parts` | 搜索、过滤、分页并获取绝对资源 URL。 |
| `/v1/parts/{id}` | 按稳定 id 获取单个富化的零件（part）记录。 |
| `/v1/catalog/schema` | JSON Schema、字段语义、结果排序和 family 属性含义。 |
| `/v1/catalog/parts.index.json` | 紧凑的 id/名称/分面发现索引，用于在获取详细信息之前进行低成本查找。 |
| `/v1/openapi.json` | OpenAPI 3.1 契约，用于生成客户端/工具。 |

## `/v1/parts` 查询参数

- `q`：跨 id、name、description、category、family、stepSource、productPage、tags、aliases、standard 字段、属性键和属性值的分词元数据搜索。每个词元都必须匹配。
- `tag`、`category`、`family`、`standard`：可重复的过滤器。值也可以以逗号分隔。单个分面内的值进行 OR 运算，而选定的分面字段之间进行 AND 运算。
- `page`：从 1 开始的页码。
- `pageSize`：默认 `100`，最大 `500`。

未过滤的结果以固定的 100 件展示开始，然后以稳定的源目录顺序继续。过滤后的结果按稳定的源目录顺序排列。

示例：

```text
https://api.step.parts/v1/parts?q=M3&tag=screw&page=2
https://api.step.parts/v1/parts?pageSize=100
https://api.step.parts/v1/parts?category=fastener&family=socket-head-cap-screw&standard=ISO%204762
https://api.step.parts/v1/parts?q=lengthMm%2012
```

## 响应字段

`/v1/parts` 返回：

- `catalog`：零件（part）计数、最后修改时间戳、目录校验和，以及 schema/OpenAPI 的 URL。
- `items`：富化的零件（part）记录，带有绝对的 `pageUrl`、`apiUrl`、`stepUrl`、`glbUrl` 和 `pngUrl`。
- `page`、`pageSize`、`total`、`totalPages`、`hasNextPage`、`hasPreviousPage`。
- `facets`：可用的 `tags`、`categories`、`families` 和 `standards` 及其计数。
- `filters`：已解析的活动过滤器。

每个零件（part）记录包含：

- `id`：稳定的 snake_case 标识符和资源文件名基。
- `name`、`description`、`category`、`family`、`tags`、`aliases`。
- `standard`：可选的 `{ body, number, designation }`。
- `attributes`：特定于 family 的标量事实。
- `stepUrl`、`glbUrl`、`pngUrl`。
- `byteSize`、`sha256`。

## 资源 URL 模式

尽可能使用返回的 URL。模式为：

```text
https://www.step.parts/step/{id}.step
Use the absolute `glbUrl` and `pngUrl` returned by the API record. Preview assets are served from Vercel Blob.
https://www.step.parts/parts/{id}
```

`/step/{id}.step` 路由在本地/开发模式下提供本地检出的 STEP 字节，并在生产环境中重定向到提交锁定的 GitHub LFS 媒体。

## 下载与验证（validation）

下载 STEP 文件时：

1. 从 `/v1/parts` 或 `/v1/parts/{id}` 获取零件（part）记录。
2. 下载 `stepUrl`。
3. 当 `sha256` 不为 null 时，将文件的 SHA-256 与零件（part）记录的 `sha256` 进行比较。
4. 保留原始的 `.step` 扩展名，并在文件名中保留来源 id，除非用户另有要求。
