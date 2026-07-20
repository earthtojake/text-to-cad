---
name: bambu-labs
description: 对已验证（validation）的普通 `.gcode` 文件进行 dry-run、上传，并谨慎地从本地 Bambu Lab 发起打印作业，使用 Bambu LAN FTPS/MQTT 交接（handoff）。
---

# Bambu Labs

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
使用已安装的本地技能文件作为运行时的真相来源；仓库链接仅用于溯源和发布审查。

当普通 `.gcode` 文件已存在并通过验证（validation）后，使用此技能进行本地网络 Bambu Lab 打印交接（handoff）。此技能不对模型进行切片。

## 安全规则

- 默认使用 dry-run 计划。真实打印机流量需要 `--execute`。
- 没有 `--execute --confirm-start-print` 不得启动打印。
- 暂停和取消控制是实时的打印机请求；默认使用 dry-run 计划。
  取消打印需要 `--execute --confirm-cancel-print`。
- 将用户明确请求打印或启动特定作业视为实时启动授权；不要仅为物理检查而暂停等待第二次确认。仍需验证（validation）G-code、检查 dry-run 负载、读取打印机状态、在上传启动前优先仅上传、说明物理检查项，并在验证（validation）/状态/意图不安全或含糊时停止。
- 默认不要询问打印机序列号；用 `serial` 从打印机 TLS 证书中获取，或让 `send` 缓存它。
- 优先使用工作区根目录下的 `bambu-printers.json`，而不是在命令中重复访问码。该文件是本地配置，应被 Git 忽略。
- 在实时启动前，说明物理检查项：构建板干净、正确的板/耗材/喷嘴、环境安全、操作员在旁。
- 发布 MQTT 只是启动请求。通过打印机状态/UI 和物理观察确认已被接受。

## CAD Viewer 交接（handoff）

完成创建或修改本地支持的打印产物（artifact）（如 `.gcode` 或 `.3mf`）的 Bambu 工作后，当 `$cad-viewer` 技能已安装时，必须始终将显式文件路径交接（handoff）给 `$cad-viewer`。`$cad-viewer` 必须在尚未运行时启动 CAD Viewer，并返回相关已创建或更新文件的链接；如果 `$cad-viewer` 不可用或启动失败，应报告该情况，而不是静默省略交接（handoff）。

## 工作流（workflow）

1. 用 `$gcode` 生成并验证（validation）普通 G-code。
   如果未安装切片器，安装 OrcaSlicer 后重试；不要将缺少切片器视为阻塞项。在 macOS 上，优先使用 `brew install --cask orcaslicer`。
2. 配置打印机。用户可以在对话中提供 IP/访问码让 agent 写入 JSON，或直接编辑 `bambu-printers.json`。
   对于新打印机设置或入门请求，先阅读
   `references/new-printer-onboarding.md`。引导用户完成针对型号的触摸屏步骤以找到 IP 和 LAN 访问码，并在运行本地启动工作流（workflow）前明确 **Enable LAN Only** 加上 **Enable Developer Mode**。

```bash
python scripts/bambu_lan_print.py config set \
  --printer a1-mini \
  --host 192.168.1.34 \
  --access-code 12345678 \
  --model a1-mini \
  --fetch-serial
```

手动 JSON 格式：

```json
{
  "printers": {
    "a1-mini": {
      "host": "192.168.1.34",
      "access_code": "12345678",
      "model": "a1-mini"
    }
  }
}
```

在 A1/A1 Mini 上，在打印机触摸屏的网络/LAN 设置下找到 IP 和 LAN 访问码。在出现选项时启用 LAN Only 和 Developer Mode，然后在重试本地启动命令前重启电源。

3. 在实时操作前读取状态：

```bash
python scripts/bambu_lan_print.py status \
  --printer a1-mini \
  --push-all \
  --wait-seconds 10
```

4. Dry-run 精确的交接（handoff），检查 JSON 负载，然后仅运行上传。
只有在上传成功后才运行 upload-start。如果用户明确要求打印或启动作业，在验证（validation）、状态和上传检查通过后，继续执行 `upload-start --execute
--confirm-start-print`。如果用户只要求准备、切片、上传或审查，则在启动请求前停止。

## 交接（handoff）模式

`--handoff template-project` 是本仓库 LAN 调试验证（validation）过的 A1 Mini 路径。它从已验证（validation）的普通 `.gcode` 开始，复制一个已知良好的同型号打印机 `.gcode.3mf` 模板，替换 `Metadata/plate_N.gcode`，写入板 MD5，将项目上传到 FTPS 根目录，并发布 `print.project_file`，其中 `url: ftp:///<name>.gcode.3mf`。

```bash
python scripts/bambu_lan_print.py send \
  --printer a1-mini \
  --gcode /tmp/job.gcode \
  --handoff template-project \
  --template-project /path/to/same-printer-template.gcode.3mf \
  --action upload-start
```

当用户明确要求打印或启动时在审查后执行，或当意图不明确时在物理确认后执行：

```bash
python scripts/bambu_lan_print.py send \
  --printer a1-mini \
  --gcode /tmp/job.gcode \
  --handoff template-project \
  --template-project /path/to/same-printer-template.gcode.3mf \
  --action upload-start \
  --execute \
  --confirm-start-print
```

`--handoff plain` 上传 `cache/<name>.gcode` 并发布
`print.gcode_file`。保留用于诊断或已知可用的打印机/固件。在测试的 A1 Mini 上，直接普通 G-code 上传成功，但 `gcode_file` 失败或被忽略，因此不要将其用作 A1 Mini 实时启动路径。

`--handoff bambox-project` 用 `bambox` 打包普通 `.gcode`，将 `.gcode.3mf` 项目上传到 FTPS 根目录，并发布 `print.project_file`。当前仅对 `p1s-0.4` 启用，支持 `PLA`、`ASA` 或 `PETG-CF`。已知但尚未启用（直到存在验证（validation）过的配置文件）：`a1-mini-0.4`、`a1-0.4`、`x1c-0.4` 和 `p1p-0.4`。

## 常用调试命令

获取/缓存序列号：

```bash
python scripts/bambu_lan_print.py serial \
  --printer a1-mini \
  --json
```

在修复根本原因后清除陈旧的打印机错误：

```bash
python scripts/bambu_lan_print.py clear-error \
  --printer a1-mini \
  --execute
```

在调试打印机是否确认了 MQTT 发布以及随后报告了什么状态时，在 `send` 上使用 `--mqtt-qos 1 --wait-after-publish 10`。

## 打印控制

对于正在运行的打印，使用专用打印控制命令，而不是临时的 MQTT 代码片段。这些命令仅发布控制请求；它们不上传文件或启动新作业。执行后读取状态以确认打印机状态已改变。

Dry-run 暂停负载：

```bash
python scripts/bambu_lan_print.py pause \
  --printer a1-mini
```

执行暂停并收集打印机报告：

```bash
python scripts/bambu_lan_print.py pause \
  --printer a1-mini \
  --execute \
  --mqtt-qos 1 \
  --wait-after-publish 10
```

Dry-run 取消负载。发送给打印机的 Bambu LAN 命令是 `stop`：

```bash
python scripts/bambu_lan_print.py cancel \
  --printer a1-mini
```

仅当用户明确要求取消/停止打印时，或意图含糊时经确认后执行取消：

```bash
python scripts/bambu_lan_print.py cancel \
  --printer a1-mini \
  --execute \
  --confirm-cancel-print \
  --mqtt-qos 1 \
  --wait-after-publish 10
```

## 失败模式

- `gcode_file` 返回 `result: fail` 或使打印机保持 `IDLE`：普通 G-code 上传成功，但固件拒绝或忽略了直接本地启动。对于 A1 Mini，切换到 `template-project`。
- 上传到 `cache/` 下的项目启动后失败，出现 `print_error: 83935248` 或 `0500-C010`：清除错误，将项目交接（handoff）上传到 FTPS 根目录，并使用 `ftp:///<name>.gcode.3mf`。
- `file:///sdcard/cache/...` 或本地 HTTP URL 看似被接受但没有启动：停止为此工作流（workflow）使用这些 URL 形式。
- Bambu Studio 或 OrcaSlicer 项目导出在 macOS 上崩溃：不要持续重试基于 GUI 的项目导出。使用 OrcaSlicer 生成普通 `.gcode`，然后使用此技能进行交接（handoff）。
- 启用 Developer Mode 后陈旧的 `gcode_state: FAILED` 或 HMS：清除打印机错误并在重试前重启电源。
- FTPS 登录正常但上传失败出现 `553` 或缺少 `cache/`：在 MQTT 启动前检查打印机存储/SD 卡状态。
- MQTT 状态正常但启动不工作：在重试前确认序列号、访问码、Developer Mode/LAN Only 状态以及精确的交接（handoff）负载。

阅读 `references/new-printer-onboarding.md` 了解新打印机设置，
`references/local-lan-protocol.md` 了解协议详情，并在新打印机首次实时使用前阅读 `references/real-printer-checklist.md`。
