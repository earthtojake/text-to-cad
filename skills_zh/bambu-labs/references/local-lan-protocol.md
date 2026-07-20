# Bambu Lab 本地 LAN 协议笔记

仅在针对真实本地打印机进行规划或调试时使用此参考。
Bambu 并未为此技能提供稳定的公共本地打印 API
契约，因此请将这些视为观察到的 FTPS/MQTT 行为。

## 必需输入

- 已验证（validation）的普通 `.gcode`。
- 打印机 LAN IP/主机名。
- 打印机访问码。
- 用于 MQTT 主题 `device/{serial}/request` 的打印机序列号；用 `serial` 从打印机 TLS 证书获取，或让 `send` 获取/缓存。
- 交接（handoff）模式：`template-project`、`plain` 或 `bambox-project`。

工作区根目录下的 `bambu-printers.json` 存储打印机 ID、主机名、访问码、型号和缓存的序列号。它是本地配置，应被 Git 忽略。

## 传输

- FTPS 上传：端口 `990` 上的隐式 TLS。
- MQTT 控制/状态：端口 `8883` 上的 TLS。
- 用户名：`bblp`。
- 密码：打印机访问码。
- TLS 验证（validation）默认关闭，因为本地打印机通常使用设备/自签名证书。
- 除非设置了 `--allow-nonprivate-host`，否则助手拒绝公共 IP/主机名。
- FTPS 数据连接可能需要 TLS 会话重用。助手在上传和列表操作中重用控制 TLS 会话。

## MQTT 主题

- 请求主题：`device/{serial}/request`。
- 报告主题：`device/{serial}/report`。
- `status --push-all` 订阅报告，然后发布 `pushing.pushall` 以请求完整状态报告。
- 发布启动负载是请求，并非已被接受的证明。

## 交接（handoff）负载

### 模板项目

在本地 LAN 调试期间于 A1 Mini 上验证（validation）过：

1. 从已验证（validation）的普通 `.gcode` 开始。
2. 复制一个已知良好的同型号打印机 `.gcode.3mf` 模板。
3. 替换 `Metadata/plate_N.gcode` 并更新 `Metadata/plate_N.gcode.md5`。
4. 将生成的 `.gcode.3mf` 上传到 FTPS 根目录，而非 `cache/`。
5. 发布 `print.project_file`，使用根 FTP URL。

代表性负载：

```json
{
  "print": {
    "command": "project_file",
    "param": "Metadata/plate_1.gcode",
    "project_id": "0",
    "profile_id": "0",
    "task_id": "0",
    "subtask_id": "0",
    "subtask_name": "job",
    "url": "ftp:///job.gcode.3mf",
    "md5": "PROJECT_MD5_UPPERCASE",
    "timelapse": false,
    "bed_type": "auto",
    "bed_levelling": true,
    "flow_cali": true,
    "vibration_cali": false,
    "layer_inspect": true,
    "use_ams": false,
    "ams_mapping": ""
  }
}
```

### 普通 G-code

普通路径上传 `cache/<job>.gcode` 并发布：

```json
{
  "print": {
    "command": "gcode_file",
    "param": "cache/job.gcode"
  }
}
```

在测试的 A1 Mini 上，逐字节验证（validation）的上传仍产生 `gcode_file` 失败/空闲行为。仅将此路径用于诊断或已验证（validation）的打印机固件。

### Bambox 项目

可选的 `bambox-project` 路径将普通 G-code 打包成 `.gcode.3mf`（针对已启用的配置文件），验证（validation）归档，上传到 FTPS 根目录，并发布与模板项目相同的 `project_file` 格式。当前启用的配置文件是 `p1s-0.4`；A1/A1 Mini 在存在验证（validation）过的 bambox 配置文件之前处于禁用状态。

## 观察到的失败模式

- **直接 G-code 被拒绝：** `gcode_file` 之后的 MQTT 报告可能包含 `{"command":"gcode_file","result":"fail","reason":"error string"}`。停止并使用项目交接（handoff）。
- **直接 G-code 被忽略：** 上传的文件存在，HMS 为空，目标温度保持为零，`gcode_state` 保持 `IDLE`。不要持续循环路径变体。
- **`cache/` 中的项目失败：** `project_file` 可能被接受然后失败，出现 `print_error: 83935248` / `0500-C010`。清除错误并将项目文件上传到 FTPS 根目录，使用 `ftp:///<name>.gcode.3mf`。
- **HTTP/文件 URL 无效：** `file:///sdcard/cache/...` 和本地 HTTP URL 可能被接受但不获取或启动。不要为此工作流（workflow）使用它们。
- **Bambu/Orca 项目导出崩溃：** macOS 上基于 GUI 的 CLI 项目导出可能在 AppKit/BambuStudio 内崩溃。仅将切片器 CLI 用于普通 `.gcode`。
- **陈旧的打印机状态：** 在 LAN Only/Developer Mode 更改后，清除错误并重启电源。状态可能保留陈旧的 `FAILED`/HMS 值。
- **存储不可用：** 如果 FTPS 认证正常但上传失败出现 `553`，或状态报告无 SD/存储，请在 MQTT 启动前解决存储问题。

仅在修复根本原因后使用 `clear-error --execute`。它发布 `print.clean_print_error` 且不启动运动。
