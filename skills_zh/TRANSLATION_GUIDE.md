# skills_zh 翻译规范

本目录是 `skills/` 的中文翻译版。翻译原则如下。

## 翻译原则

1. **完整翻译所有自然语言文本**为中文。标题、正文、列表项、表格单元格、
   admonition 内容全部翻译。
2. **保留以下内容不翻译**（原样保留）：
   - 代码块 ` ```code ``` ` 的内容（除非是纯说明性注释，可翻译注释但保留代码）
   - 行内代码 `` `code` `` 中的标识符、路径、命令、函数名
   - 文件路径、URL、命令行参数（如 `scripts/step`、`gen_step()`、`--kind`）
   - YAML frontmatter 的 `name:` 字段值（技能标识符，保留英文）
   - frontmatter 的 `description:` 字段：翻译为中文，但保留其中的代码引用
   - 技术专有名词首次出现时保留英文括注，如：装配体（assembly）、
     关节（joint）、位姿（pose）
   - 度量单位、数值、版本号
3. **术语处理（重要）**：CAD/机器人技术术语**一律保留英文原文**。两种方式任选：
   - **优先**：中英对照，如 `装配体（assembly）`、`关节（joint）`、`参考系（frame）`
   - 或直接保留英文不翻译，如 `assembly`、`joint`、`frame`
   - 常见术语对照（中文 + 英文，翻译时两者都保留）：
     - 装配体 assembly / 零件 part / 关节 joint / 连杆 link
     - 参考系 frame / 位姿 pose / 网格 mesh / 拓扑 topology
     - 选择器 selector / 基准 datum / 配合 mating
     - 圆角 fillet / 倒角 chamfer / 凸台 boss / 型腔 pocket
     - 支柱 standoff / 加强筋 rib / 间隙孔 clearance hole / 通孔 through-hole
     - 盲孔 blind hole / 沉孔 counterbore / 锪孔 countersink
     - 外壳 enclosure / 支架 bracket / 法兰 flange / 套筒 sleeve
     - 轴承 bearing / 执行器 actuator / 舵机 servo / 惯性参数 inertial
     - 碰撞 collision / 快照 snapshot / 交接 handoff / 清册 ledger
     - 约束规则 guardrails / 工作流 workflow / 验证 validation
     - 产物 artifact / 附带产物 sidecar / 清单 manifest
   - 这些术语在**每次出现时**都应保留英文，不仅限于首次。
4. **保持原文的 Markdown 结构**：标题层级、列表、表格、代码块标记、
   链接、 admonition 标记（`> **注意**：`）等原样保留。
5. **保持原文的语义和语气**：祈使句翻译为中文祈使句，警告/不可妥协条款
   保留严肃语气。
6. **保留原文的章节锚点和引用**：如 "见 `references/xxx.md`" 中的
   路径不翻译。
7. 输出文件路径：`skills_zh/<对应相对路径>`，与源文件结构一致。

## 输出要求

- 每个文件完整翻译，不要省略任何章节。
- 保留 YAML frontmatter（`---` 包裹的部分），翻译 description 字段。
- 不要添加原文没有的内容（不擅自补充解释）。
- 不要删除原文的任何内容。
