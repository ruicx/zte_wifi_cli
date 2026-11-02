# zte-wifi-cli — Agent Instructions

CLI + agent skill that controls a ZTE U30Air portable WiFi hotspot
(firmware F50ProV1.0.0B28) by replaying its web console's HTTP API.
The protocol was reverse-engineered from the device's own frontend JS;
nothing here is officially documented — treat the constants in the code as
the source of truth.

## Non-negotiables

- **Follow `~/.codex/AGENTS.md`** for coding style: complete type annotations
  (modern generics), NumPy-style docstrings on every module/class/function,
  English comments, small pure functions, no global mutable state.
- **`uv run ty check` must pass with zero errors** before any change counts
  as done.
- **The HTTP client must always bypass system proxies**
  (`requests.Session(trust_env=False)` in `client.py`). A local proxy
  (127.0.0.1:28618) usually runs on this machine and will intercept device
  traffic if respected.
- **Never put the device password in code, tests, logs, or the skill.**
  It lives in Windows Credential Manager (keyring service `zte-wifi-cli`,
  entry `web-admin`), managed via interactive `zte auth` only.
- **`switchWiFiModule` semantics are inverted**: `SwitchOption="0"` turns
  WiFi ON, `"1"` turns it OFF (verified live; do **not** "fix" this without
  a live round-trip test).

## Device quirks (learned from live testing)

- The dev PC talks to the device over **USB**, so toggling the WiFi radio
  never cuts the control channel.
- Device HTTP responses can lag a state change by up to ~30 s — action
  commands poll until settled and exit non-zero on timeout.
- Login uses double SHA-256 (uppercase hex) against the `LD` challenge;
  writes need the `AD` signature built from `RD` + firmware version strings.
  All implemented in `src/zte_wifi_cli/client.py`.
- `zte sim switch` follows the protocol extracted from the device JS but has
  **never been live-verified** (no SIM in slot 2 during development). If it
  misbehaves, re-check `SET_SIM_SLOT` params and `switch_sim_result` polling
  before assuming the client is wrong.

## Making changes

- Protocol details (goform IDs, cmd names, option values) belong in
  `client.py` / `cli.py` constants near their only users — no kitchen-sink
  constants module.
- User-facing CLI output stays in Chinese; `--json` output keys stay raw
  device field names.
- The agent skill source is `skill/zte-wifi/SKILL.md` (English). After
  editing it, copy it to `~/.zcode/skills/zte-wifi/SKILL.md` — the installed
  copy is what sessions load; the repo copy is the source of truth.

## Verification

Smoke-test against the real device (it must be attached via USB):

```console
uv run zte status          # reads: operator/signal/WiFi/SIM
uv run zte wifi status     # RadioOff/wifi_onoff_state
```

Destructive round-trips (`wifi off`→`on`, `net mode 4g`→`auto`) are safe
over USB but interrupt WiFi clients briefly — confirm with the user before
running them. `sim switch` interrupts cellular service for up to ~2 minutes;
only run it when the user asks.

## Commits

Subjects as `<Type>: <summary>` with `Feat` / `BugFix` / `Refactor` / `Doc`,
blank line, then a numbered list of changes (see `~/.codex/AGENTS.md`).
