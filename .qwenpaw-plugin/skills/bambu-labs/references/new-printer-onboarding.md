# New Printer Onboarding

Use this reference whenever the user asks to set up, add, pair, configure, or
test a new Bambu Lab printer for local LAN handoff. The goal is a calm,
step-by-step setup where the user always knows what is safe, what is private,
and what the agent will do next.

## Agent Flow

1. Start by confirming this is setup only. Say that no upload or print will
   happen during onboarding unless the user explicitly asks later.
2. Ask for the printer model or family if it is not already known. Use a stable
   local printer id such as `a1-mini`, `a1`, `p1s`, `p1p`, `x1c`, or `h2d`.
3. Tell the user you need two values from the printer touchscreen:
   printer IP address and LAN access code. Explain that the serial is fetched
   from the printer certificate and should not be requested by default.
4. Immediately give the model-specific touchscreen steps below. Do not just ask
   for the IP and access code without helping the user find them.
5. Make the LAN prerequisites very explicit: the user must **Enable LAN Only**
   and **Enable Developer Mode** before live local start commands. If either
   option exists and is off, stop setup and ask them to enable it first.
6. After the user provides the IP and access code, store them with `config set`
   in workspace-root `bambu-printers.json`, using `--fetch-serial`. Do not repeat the
   access code in the final response.
7. Run `status --push-all --wait-seconds 10` and summarize the result in plain
   language: reachable or not, idle/running/error, SD/storage present, and any
   `print_error` or HMS entries.
8. If setup succeeds, offer the next safe step as a dry-run handoff plan. Do not
   upload or start anything during onboarding unless the user explicitly asks.

## What To Say First

Use a short, reassuring prompt like this:

```text
I can set this up safely. I need the printer's LAN IP address and LAN access
code from the touchscreen. Before you send them, please enable LAN Only and
Developer Mode; local starts often fail or become read-only if Developer Mode is
off. I will store the code only in the workspace-local ignored config and fetch the
serial from the printer automatically.
```

Then give the matching steps for their printer family.

## Touchscreen Steps By Printer Family

### A1 / A1 Mini

1. On the printer touchscreen, open **Settings**.
2. Open **Network** or **WLAN**.
3. Connect the printer to the same trusted local network as this computer.
4. **Enable LAN Only**.
5. **Enable Developer Mode** in the same network/LAN area when shown.
6. Record the IPv4 address shown on the network screen.
7. Record the LAN access code shown near the LAN Only or Developer Mode
   controls. If it is all zeros, refresh/regenerate it or toggle LAN Only off
   and on, then record the new code.
8. Power-cycle the printer after changing LAN Only or Developer Mode.

### P1P / P1S

1. On the printer screen, open **Settings**.
2. Open **Network** or **WLAN**.
3. Confirm the printer is on the same trusted local network as this computer.
4. **Enable LAN Only**.
5. **Enable Developer Mode**. If it is not visible, update firmware or stop
   before live local start workflows.
6. Record the printer IPv4 address.
7. Record the LAN access code. If the code is all zeros or blank, refresh it or
   toggle LAN Only off and on, then record the new code.
8. Power-cycle the printer before the first local status check.

### X1 / X1C / X1E

1. On the printer touchscreen, open **Settings**.
2. Open **Network** or **WLAN**.
3. Confirm the printer is connected to the same trusted local network.
4. **Enable LAN Only**.
5. **Enable Developer Mode**. If it is not visible, update firmware or stop
   before live local start workflows.
6. Record the IPv4 address.
7. Record the LAN access code from the LAN/network screen.
8. Power-cycle the printer after changing LAN settings.

### H2D / Newer Bambu Printers

1. Open **Settings** on the printer touchscreen.
2. Open **Network**, **WLAN**, or the printer's LAN settings panel.
3. Confirm local network connectivity.
4. **Enable LAN Only**.
5. **Enable Developer Mode**.
6. Record the IPv4 address and LAN access code.
7. Power-cycle after changing LAN settings.

For an unknown Bambu model, guide the user to the printer's network/WLAN
settings, then require the same four items before continuing: same local
network, **Enable LAN Only**, **Enable Developer Mode**, and collect IP plus
LAN access code.

## Agent Commands

Use the active Python environment:

```bash
python scripts/bambu_lan_print.py config set \
  --printer a1-mini \
  --host 192.168.1.34 \
  --access-code 12345678 \
  --model a1-mini \
  --fetch-serial
```

Then check status:

```bash
python scripts/bambu_lan_print.py status \
  --printer a1-mini \
  --push-all \
  --wait-seconds 10
```

Use the model-specific printer id in both commands. If sandboxing blocks local
network access, rerun the same command with permission to contact the printer.

## Smooth Failure Handling

- If the printer is unreachable, ask the user to confirm the IP, same Wi-Fi or
  VLAN reachability, and that the printer is awake.
- If MQTT status fails but TLS serial fetch worked, first confirm **Developer
  Mode** is enabled, then power-cycle and retry status.
- If the access code is rejected or all zeros, ask the user to refresh the LAN
  access code on the printer and rerun `config set --fetch-serial`.
- If status returns stale `FAILED`, `print_error`, or HMS entries after enabling
  LAN Only or Developer Mode, stop. Ask the user to resolve the physical issue,
  power-cycle, then retry status. Use `clear-error --execute` only after the
  underlying cause is fixed.
- If setup succeeds, do not imply that live printing is validated. Say that LAN
  connectivity is configured and status works; live printing still requires the
  real-printer checklist, a dry-run plan, upload-only, and supervised start.
