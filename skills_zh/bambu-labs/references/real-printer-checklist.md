# 真实打印机清单（manifest）

在对物理 Bambu Lab 打印机执行任何 `--execute` 运行前使用此清单（manifest）。

## 凭证和网络

- 确认打印机 IP/主机名在受信任的本地网络上。
- 当打印机提供 LAN Only/Developer Mode 选项时确认已启用，特别是在 A1/A1 Mini 上。
- 用 `config set` 将访问码存储在工作区根目录的 `bambu-printers.json` 中；不要在最终消息中打印它。
- 用 `serial` 或 `config set --fetch-serial` 获取/缓存序列号。
- 运行 `status --push-all` 并验证（validation）目标打印机响应。
- 如果 LAN 设置在失败的启动后发生更改，在重试前清除陈旧错误并重启电源。

## 作业

- 确认 `$gcode` 已生成并验证（validation）普通 `.gcode`。
- 确认比例、方向、支撑、材料配置文件、喷嘴和板类型。
- 对于 A1 Mini LAN 启动，优先使用 `--handoff template-project` 和已知良好的同型号打印机 `.gcode.3mf` 模板。
- 仅将 `--handoff plain` 用于诊断或已验证（validation）`gcode_file` 的固件。
- 仅当脚本启用了精确的打印机/喷嘴配置文件时，才使用 `--handoff bambox-project`。
- 对于项目交接（handoff），上传到 FTPS 根目录并使用 `ftp:///<name>.gcode.3mf`。

## 物理打印机

如果当前用户请求明确要求打印或启动作业，将该请求视为此清单（manifest）的实时启动授权。在实时命令前说明这些物理检查，并在自动化验证（validation）和打印机状态健康时继续。仅在请求意图含糊或验证（validation）/状态检查引起担忧时要求再次确认。

- 构建板已安装、干净、清洁且适合该材料。
- 打印机内没有失败打印的残留物、松散工具、胶带碎片或碎屑。
- 耗材已装入且适合切片文件。
- 操作员在旁，用于加热、归零和首层观察。
- 有相机或直接观察可用。

## 首次实时序列

1. 运行精确的 `send` 命令（不带 `--execute`）并检查计划。
2. 首先运行 `send --action upload --execute`。
3. 如果可能，检查状态/UI/存储。
4. 重新运行 dry `send --action upload-start` 计划。
5. 当用户明确要求打印/启动时，或意图不明确时经确认后，运行 `send --action upload-start --execute --confirm-start-print`。
6. 轮询状态并观察打印机，直到首层明显正常。

如果状态在失败尝试后报告 `print_error` 或 HMS，停止。解决原因，可选地运行 `clear-error --execute`，然后在重试前轮询状态。
