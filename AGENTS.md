# zte-wifi-cli — Agent Instructions

CLI + agent skill that controls a ZTE U30Air portable WiFi hotspot
(firmware F50ProV1.0.0B28) by replaying its web console's HTTP API.
The protocol was reverse-engineered from the device's own frontend JS;
nothing here is officially documented — treat the constants in the code as
the source of truth.

## Non-negotiables

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

## Coding style

- **Type annotations**: every function and method fully annotated, using
  modern builtin generics (`list[T]`, `dict[str, Any]`, `X | Y`).
- **Static typing**: `uv run ty check` must pass with zero errors before any
  change counts as done.
- **Docstrings**: NumPy style on every module, class, and function (public
  and private), with `Parameters`, `Returns`, `Raises`, `Notes` sections
  where applicable.
- **Comments** are written in English.
- **Structure**: favor small pure helper functions and explicit dataclasses;
  never introduce global mutable state; no kitchen-sink modules.
- **Simplicity first**: minimum code that solves the problem — no features
  beyond what was asked, no speculative abstractions or configurability, no
  error handling for impossible scenarios.
- **Surgical changes**: touch only what the task requires; match the existing
  style; clean up only what your own changes orphaned.
- **Be honest**: if the approved approach hits a technical obstacle, stop and
  surface it to the user instead of silently redesigning.

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
- The agent skill source is `skill/zte-wifi/SKILL.md` (English).

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

Subjects as `<Type>: <summary>` where `<Type>` is one of `Feat` / `BugFix` /
`Refactor` / `Doc`, separated from the body by a blank line, then a numbered
list detailing the changes.
