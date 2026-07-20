# SRDF disabled collision

Disabled collision 是规划安全数据。请将其视为推导出的证据，而非装饰性 XML。

## 有效来源

使用以下来源之一：

- 来自 URDF 运动学图的邻接 link 策略；
- MoveIt Setup Assistant 自碰撞（collision）矩阵生成；
- 来自已知 MoveIt 配置的采样 collision 分析；
- 显式用户提供的 collision 矩阵；
- 经过人工审查的特定对及具体理由。

不要从外观或模糊的文字描述推断 disabled collision 对。

## XML 形式

```xml
<disable_collisions link1="base_link" link2="shoulder_link" reason="Adjacent"/>
```

当前运行时要求：

- `link1` 和 `link2`；
- 两个 link 都存在于 URDF 中；
- 不同的 link 名称；
- 非空的 `reason`；
- 没有重复或反向重复的对。

## 理由和来源

使用真实的理由。示例：

| 理由 | 典型来源 |
|---|---|
| `Adjacent` | URDF 图邻接 |
| `Never` | Setup Assistant 采样矩阵 |
| `Always` | Setup Assistant 采样矩阵 |
| `Default` | Setup Assistant 采样矩阵 |
| `Manual: tool fixture is outside workspace envelope` | 显式人工审查 |

当前解析器将理由分类为宽泛的来源类别，如邻接、采样、Setup Assistant、手动或假定。除非用户明确要求临时 SRDF 且已报告风险，否则避免使用 `assumed`。

## 审查清单（manifest）

在提交 disabled collision 对之前：

- 该对是否邻接或采样安全？
- 禁用该对是否会隐藏计划任务期间可能的真实 collision？
- 该对的生成是否使用了足够的采样密度？
- 在几何体、limit 或 group 成员关系变更后，该对是否仍然有效？
- 是否记录了手动理由？

如果存在大量手动对，请优先使用 MoveIt Setup Assistant 重新生成自碰撞（collision）矩阵。
