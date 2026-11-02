# zte-wifi-cli

Command-line control for a ZTE portable WiFi hotspot (U30Air, firmware
F50ProV1.0.0B28) over its web console API — no browser needed.

Reverse-engineered protocol highlights (all verified live):

- **Login**: challenge-response `SHA256_upper(SHA256_upper(pw) + LD)` with the
  `LD` challenge from `cmd=LD`; session kept as a `JSESSIONID` cookie.
- **Writes** are signed: `AD = SHA256_upper(SHA256_upper(rd0 + rd1) + RD)`,
  where `rd0`/`rd1` are firmware version strings and `RD` is a per-request
  challenge.
- **WiFi switch**: `switchWiFiModule` with `SwitchOption` — **inverted
  semantics**: `"0"` turns the radio ON, `"1"` turns it OFF.

## Setup

```console
uv sync
uv run zte auth        # store the web console password in Windows Credential Manager
```

## Usage

```console
uv run zte status              # operator / signal / connection / rates / WiFi / SIM overview
uv run zte wifi status
uv run zte wifi on
uv run zte wifi off            # asks for confirmation; --force skips it
uv run zte sim status
uv run zte sim switch 2        # blocks until the modem re-registers (up to ~2 min)
uv run zte net status
uv run zte net mode 4g         # auto | nsa | sa | 4g3g | 4g | 3g
```

Every command accepts `--json` for machine-readable output and `--host` /
`ZTE_HOST` to override the default address `192.168.0.1`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Device error / state-change timeout |
| 2 | Credential error (run `zte auth`) |
| 3 | Device unreachable |

> Note: `zte sim switch` follows the protocol extracted from the device web
> UI (`SET_SIM_SLOT` + `switch_sim_result` polling) but has **not been live-
> verified yet** — no second SIM was available during development. WiFi
> on/off, network mode, and all status reads are live-verified.

## Agent skill

`skill/zte-wifi/SKILL.md` is an agent skill (English) that teaches an agent
to drive this CLI. Install it for all workspaces:

```console
xcopy /E /I /Y skill\zte-wifi "%USERPROFILE%\.zcode\skills\zte-wifi"
```

## Development

```console
uv run ty check        # static type analysis (must pass)
```

Project layout: `src/zte_wifi_cli/` — `client.py` (protocol), `cli.py`
(click commands), `cred.py` (keyring), `crypto.py` (device hashing).
