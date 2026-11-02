---
name: zte-wifi
description: Control the user's ZTE portable WiFi hotspot (随身WiFi / MiFi, model U30Air) through the `zte` CLI — check signal, operator, connection and device status, turn the WiFi radio on or off, switch SIM slots (切卡/切网络), and change network mode (5G/4G). Use when the user mentions their portable WiFi, hotspot, 随身WiFi, asks to turn its WiFi on/off, switch SIM cards, or check its signal/data status.
---

# ZTE Portable WiFi Control

The user's portable WiFi hotspot (ZTE U30Air) is attached via USB and managed
by the `zte` CLI in `D:\work\utils\zte_wifi_cli`. Run commands from any
directory with:

```
uv run --directory D:\work\utils\zte_wifi_cli zte <command>
```

The web console password is stored in Windows Credential Manager (set up once
via `zte auth`). Never ask the user for the password.

## Commands

| Task | Command |
|---|---|
| Overall status (operator, signal, battery, rates, WiFi, SIM) | `zte status` |
| WiFi radio state | `zte wifi status` |
| Turn WiFi on | `zte wifi on` |
| Turn WiFi off | `zte wifi off --force` |
| Active SIM slot | `zte sim status` |
| Switch SIM slot (1 or 2) | `zte sim switch 2` |
| Current network mode | `zte net status` |
| Set network mode | `zte net mode auto\|nsa\|sa\|4g3g\|4g\|3g` |

Add `--json` to any command for machine-readable output — prefer it when you
need to inspect values programmatically. Set `ZTE_HOST` or pass `--host` if
the device is not at the default `192.168.0.1`.

## Behavior rules

- **`zte wifi off` asks for an interactive confirmation by default, which
  blocks automation.** When the user has clearly asked to turn the WiFi off
  (or disconnect wireless clients), run it with `--force`. If the intent is
  ambiguous, ask the user first.
- **SIM switching blocks while the modem re-registers** — it can take up to
  ~2 minutes. Tell the user it is in progress; the command exits by itself
  with the final operator/network info.
- **Changing network mode** (`zte net mode ...`) briefly drops cellular
  service while the modem re-registers; this is expected.
- WiFi state can be verified with `zte wifi status` afterwards; "开" = on,
  "关" = off (or `"wifi_on": true/false` in JSON).

## Exit codes and recovery

| Code | Meaning | What to do |
|---|---|---|
| 0 | Success | — |
| 1 | Device reported an error or a state change timed out | Re-check with `zte status` / `zte wifi status` and report to the user |
| 2 | Credential error (no password stored, or wrong password) | Ask the user to run `zte auth` interactively themselves |
| 3 | Device unreachable | The hotspot is powered off or its USB link is down; tell the user to check the device |

## Examples

```console
$ uv run --directory D:\work\utils\zte_wifi_cli zte status
运营商      中国电信 (5G)
信号        4 格, RSRP -103 dBm
连接        已连接 (IPv4/IPv6)
电池        无电池 (外接供电)
实时速率    ↓ 190.1 Kb/s  ↑ 45.3 Kb/s
网络模式    5G/4G/3G 自动
SIM 卡      槽 1
WiFi       开
SSID        XiaomiTV
在线设备    0
```

```console
$ uv run --directory D:\work\utils\zte_wifi_cli zte wifi off --force
WiFi 已关闭。
```
