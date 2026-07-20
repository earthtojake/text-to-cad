# 新打印机入门

当用户要求设置、添加、配对、配置或测试新的 Bambu Lab 打印机以进行本地 LAN 交接（handoff）时，使用此参考。目标是平静、逐步的设置，让用户始终知道什么是安全的、什么是私密的，以及 agent 接下来会做什么。

## Agent 流程

1. 首先确认这只是设置。说明在入门期间不会发生上传或打印，除非用户稍后明确要求。
2. 如果尚未知道打印机型号或系列，请询问。使用稳定的本地打印机 ID，如 `a1-mini`、`a1`、`p1s`、`p1p`、`x1c` 或 `h2d`。
3. 告诉用户你需要从打印机触摸屏获取两个值：打印机 IP 地址和 LAN 访问码。说明序列号从打印机证书获取，默认不应要求用户提供。
4. 立即给出下方针对型号的触摸屏步骤。不要只是索要 IP 和访问码而不帮助用户找到它们。
5. 明确说明 LAN 前置条件：用户必须在实时本地启动命令前 **Enable LAN Only** 和 **Enable Developer Mode**。如果任一选项存在且关闭，停止设置并要求用户先启用。
6. 用户提供 IP 和访问码后，用 `config set` 将它们存储到工作区根目录的 `bambu-printers.json` 中，使用 `--fetch-serial`。不要在最终响应中重复访问码。
7. 运行 `status --push-all --wait-seconds 10` 并用通俗语言总结结果：是否可达、空闲/运行/错误、SD/存储是否存在，以及任何 `print_error` 或 HMS 条目。
8. 如果设置成功，提供下一个安全步骤作为 dry-run 交接（handoff）计划。除非用户明确要求，否则在入门期间不要上传或启动任何内容。

## 首先说什么

使用类似这样的简短、令人安心的提示：

```text
我可以安全地进行设置。我需要从触摸屏获取打印机的 LAN IP 地址和 LAN 访问码。在你发送它们之前，请启用 LAN Only 和 Developer Mode；如果 Developer Mode 关闭，本地启动通常会失败或变为只读。我只会将访问码存储在工作区本地被忽略的配置中，并自动从打印机获取序列号。
```

然后给出与其打印机系列匹配的步骤。

## 按打印机系列的触摸屏步骤

### A1 / A1 Mini

1. 在打印机触摸屏上，打开 **Settings**。
2. 打开 **Network** 或 **WLAN**。
3. 将打印机连接到与这台计算机相同的受信任本地网络。
4. **Enable LAN Only**。
5. 在显示时，在同一网络/LAN 区域 **Enable Developer Mode**。
6. 记录网络屏幕上显示的 IPv4 地址。
7. 记录 LAN Only 或 Developer Mode 控制附近显示的 LAN 访问码。如果全为零，刷新/重新生成它，或切换 LAN Only 关闭再打开，然后记录新代码。
8. 更改 LAN Only 或 Developer Mode 后重启打印机电源。

### P1P / P1S

1. 在打印机屏幕上，打开 **Settings**。
2. 打开 **Network** 或 **WLAN**。
3. 确认打印机与这台计算机在相同的受信任本地网络上。
4. **Enable LAN Only**。
5. **Enable Developer Mode**。如果不可见，更新固件或在实时本地启动工作流（workflow）前停止。
6. 记录打印机 IPv4 地址。
7. 记录 LAN 访问码。如果代码全为零或空白，刷新它或切换 LAN Only 关闭再打开，然后记录新代码。
8. 在首次本地状态检查前重启打印机电源。

### X1 / X1C / X1E

1. 在打印机触摸屏上，打开 **Settings**。
2. 打开 **Network** 或 **WLAN**。
3. 确认打印机连接到相同的受信任本地网络。
4. **Enable LAN Only**。
5. **Enable Developer Mode**。如果不可见，更新固件或在实时本地启动工作流（workflow）前停止。
6. 记录 IPv4 地址。
7. 从 LAN/网络屏幕记录 LAN 访问码。
8. 更改 LAN 设置后重启打印机电源。

### H2D / 较新的 Bambu 打印机

1. 在打印机触摸屏上打开 **Settings**。
2. 打开 **Network**、**WLAN** 或打印机的 LAN 设置面板。
3. 确认本地网络连接。
4. **Enable LAN Only**。
5. **Enable Developer Mode**。
6. 记录 IPv4 地址和 LAN 访问码。
7. 更改 LAN 设置后重启电源。

对于未知的 Bambu 型号，引导用户到打印机的网络/WLAN 设置，然后在继续之前要求相同的四项：相同的本地网络、**Enable LAN Only**、**Enable Developer Mode**，以及收集 IP 和 LAN 访问码。

## Agent 命令

使用活动的 Python 环境：

```bash
python scripts/bambu_lan_print.py config set \
  --printer a1-mini \
  --host 192.168.1.34 \
  --access-code 12345678 \
  --model a1-mini \
  --fetch-serial
```

然后检查状态：

```bash
python scripts/bambu_lan_print.py status \
  --printer a1-mini \
  --push-all \
  --wait-seconds 10
```

在两个命令中使用针对型号的打印机 ID。如果沙盒阻止了本地网络访问，以联系打印机的权限重新运行同一命令。

## 平稳的失败处理

- 如果打印机不可达，要求用户确认 IP、相同的 Wi-Fi 或 VLAN 可达性，以及打印机是否已唤醒。
- 如果 MQTT 状态失败但 TLS 序列号获取成功，首先确认 **Developer Mode** 已启用，然后重启电源并重试状态。
- 如果访问码被拒绝或全为零，要求用户在打印机上刷新 LAN 访问码并重新运行 `config set --fetch-serial`。
- 如果在启用 LAN Only 或 Developer Mode 后状态返回陈旧的 `FAILED`、`print_error` 或 HMS 条目，停止。要求用户解决物理问题，重启电源，然后重试状态。仅在修复根本原因后使用 `clear-error --execute`。
- 如果设置成功，不要暗示实时打印已验证（validation）。说明 LAN 连接已配置且状态正常；实时打印仍需真实打印机清单（manifest）、dry-run 计划、仅上传和有监督的启动。
