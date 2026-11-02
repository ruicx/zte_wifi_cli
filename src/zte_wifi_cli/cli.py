"""Click command-line interface for the ZTE portable WiFi hotspot.

Commands map one-to-one onto device capabilities: status queries, the WiFi
radio switch, SIM slot switching and network-mode selection. Human-readable
output uses Chinese labels; ``--json`` emits raw device fields for scripts
and agents.
"""

import functools
import json
import time
from collections.abc import Callable
from typing import Any, NoReturn

import click

from . import cred
from .client import (
    DEFAULT_HOST,
    AuthError,
    DeviceError,
    UnreachableError,
    ZteClient,
    ZteError,
)

# switchWiFiModule option values are inverted (verified live on U30Air):
# "0" turns the WiFi radio ON, "1" turns it OFF.
WIFI_OPTION_ON = "0"
WIFI_OPTION_OFF = "1"

# switch_sim_result values (from the device web UI source): "0" = switched,
# "2" = failed, anything else (e.g. "1") = still in progress.
SIM_RESULT_OK = "0"
SIM_RESULT_FAIL = "2"

SIM_SWITCH_TIMEOUT_S = 120.0
SIM_POLL_INTERVAL_S = 2.0
WIFI_SETTLE_TIMEOUT_S = 30.0
NET_MODE_SETTLE_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 1.5

# CLI name -> (BearerPreference value, human label), from the web UI's
# AUTO_MODES table.
NET_MODES: dict[str, tuple[str, str]] = {
    "auto": ("WL_AND_5G", "5G/4G/3G 自动"),
    "nsa": ("LTE_AND_5G", "5G NSA"),
    "sa": ("Only_5G", "5G SA"),
    "4g3g": ("WCDMA_AND_LTE", "仅 4G/3G"),
    "4g": ("Only_LTE", "仅 4G"),
    "3g": ("Only_WCDMA", "仅 3G"),
}
NET_MODE_LABELS = {value: label for value, label in NET_MODES.values()}

STATUS_CMDS: tuple[str, ...] = (
    "network_type",
    "network_provider_fullname",
    "network_signalbar",
    "Z5g_rsrp",
    "network_lte_rsrp",
    "ppp_status",
    "battery_value",
    "battery_charging",
    "flux_realtime_tx_thrpt",
    "flux_realtime_rx_thrpt",
    "network_net_select",
    "sim_slot",
    "dual_sim_support",
    "wifi_onoff_state",
    "wifi_chip1_ssid1_ssid",
    "wifi_chip2_ssid1_ssid",
    "station_list",
)
WIFI_STATE_CMDS: tuple[str, ...] = (
    "wifi_onoff_state",
    "RadioOff",
    "wifi_chip1_ssid1_ssid",
    "wifi_chip2_ssid1_ssid",
    "station_list",
)

PPP_STATUS_LABELS: dict[str, str] = {
    "ipv4_ipv6_connected": "已连接 (IPv4/IPv6)",
    "ipv4_connected": "已连接 (IPv4)",
    "ipv6_connected": "已连接 (IPv6)",
    "connecting": "连接中",
    "disconnect": "已断开",
}

#
# Error handling and shared plumbing
#


def _fail(message: str, exit_code: int) -> NoReturn:
    """Print an error to stderr and exit with the given code.

    Parameters
    ----------
    message : str
        Human-readable error message.
    exit_code : int
        Process exit code (1 device error, 2 credential error, 3 unreachable).
    """
    click.secho(f"错误: {message}", err=True, fg="red")
    raise SystemExit(exit_code)


def handle_device_errors[T](fn: Callable[..., T]) -> Callable[..., T]:
    """Decorator mapping ``ZteError`` subclasses onto CLI exit codes.

    Parameters
    ----------
    fn : callable
        Command callback to wrap.

    Returns
    -------
    callable
        Wrapped callback.

    Notes
    -----
    Exit codes: 0 success, 1 device error, 2 credential error, 3 device
    unreachable.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return fn(*args, **kwargs)
        except AuthError as exc:
            _fail(f"认证失败: {exc}（用 `zte auth` 重新存储密码）", 2)
        except UnreachableError as exc:
            _fail(f"设备不可达: {exc}（检查设备电源 / USB 连接）", 3)
        except ZteError as exc:
            _fail(f"设备错误: {exc}", 1)

    return wrapper


def _build_client(host: str) -> ZteClient:
    """Build a client using the keyring-stored password.

    Parameters
    ----------
    host : str
        Device hostname or IP.

    Returns
    -------
    ZteClient
        Client instance (not yet logged in; login happens on first use).

    Raises
    ------
    SystemExit
        With code 2 when no password has been stored yet.
    """
    password = cred.load_password()
    if password is None:
        _fail("尚未存储密码，请先运行 `zte auth`", 2)
    return ZteClient(host, password)


def _emit(as_json: bool, payload: dict[str, Any], text: str) -> None:
    """Print either raw JSON or pre-rendered human text.

    Parameters
    ----------
    as_json : bool
        Whether JSON output was requested.
    payload : dict
        Machine-readable payload for ``--json``.
    text : str
        Human-readable text (ignored when ``as_json`` is true).
    """
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(text)


def _poll_until(
    predicate: Callable[[], bool],
    timeout_s: float,
    interval_s: float = POLL_INTERVAL_S,
    progress: bool = False,
) -> bool:
    """Poll a predicate until it holds or the timeout expires.

    Parameters
    ----------
    predicate : callable
        Zero-argument callable returning True when the awaited state is met.
    timeout_s : float
        Maximum total wait in seconds.
    interval_s : float, optional
        Delay between polls in seconds.
    progress : bool, optional
        Print a dot per poll for long waits.

    Returns
    -------
    bool
        True when the predicate held before the timeout.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        if progress:
            click.echo(".", nl=False)
        time.sleep(interval_s)
    return False


#
# Pure formatting helpers
#

# Shorthand for the device status dicts passed around below.
MappingLike = dict[str, Any]


def _wifi_is_on(state: MappingLike) -> bool:
    """Derive the WiFi radio state from a device status read.

    Parameters
    ----------
    state : dict
        Response containing ``RadioOff`` (preferred) or ``wifi_onoff_state``.

    Returns
    -------
    bool
        True when the radio is on.
    """
    radio_off = state.get("RadioOff")
    if radio_off is not None:
        return str(radio_off) != "1"
    return str(state.get("wifi_onoff_state", "1")) != "1"


def _format_rate(bps: Any) -> str:
    """Format a bits-per-second value for human display.

    Parameters
    ----------
    bps : str or number
        Rate in bits per second as reported by the device.

    Returns
    -------
    str
        Rate with a suitable unit, or ``-`` when unavailable.
    """
    try:
        value = float(bps)
    except (TypeError, ValueError):
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} Mb/s"
    return f"{value / 1_000:.1f} Kb/s"


def _ssid_list(state: MappingLike) -> list[str]:
    """Collect non-empty SSID names from a status read.

    Parameters
    ----------
    state : dict
        Response containing ``wifi_chip1_ssid1_ssid`` / ``wifi_chip2_ssid1_ssid``.

    Returns
    -------
    list of str
        Non-empty SSID names.
    """
    ssids = [state.get("wifi_chip1_ssid1_ssid"), state.get("wifi_chip2_ssid1_ssid")]
    return [str(name) for name in ssids if name]


def _station_count(state: MappingLike) -> str:
    """Count devices connected to the hotspot WiFi.

    Parameters
    ----------
    state : dict
        Response containing ``station_list`` (a list of station entries).

    Returns
    -------
    str
        Number of connected WiFi devices.
    """
    stations = state.get("station_list") or []
    return str(len(stations))


def _battery_text(state: MappingLike) -> str:
    """Format the battery level; ``-1`` means powered without a battery.

    Parameters
    ----------
    state : dict
        Response containing ``battery_value`` and ``battery_charging``.

    Returns
    -------
    str
        Human-readable battery description.
    """
    if str(state.get("battery_value", "")) == "-1":
        return "无电池 (外接供电)"
    charging = "" if state.get("battery_charging") != "1" else " (充电中)"
    return f"{state.get('battery_value', '-')}{charging}"


#
# Command group
#


@click.group()
def main() -> None:
    """Control a ZTE portable WiFi hotspot (U30Air) from the command line."""


@main.command()
def auth() -> None:
    """Store the web console password in the OS keychain."""
    password = click.prompt("Web 控制台密码", hide_input=True, confirmation_prompt=True)
    cred.save_password(password)
    click.echo("密码已存入系统凭据管理器。")


@main.command()
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def status(host: str, as_json: bool) -> None:
    """Show an overview of the device status."""
    state = _build_client(host).get(STATUS_CMDS)
    if as_json:
        _emit(True, state, "")
        return
    _emit(
        False,
        state,
        "\n".join(
            [
                f"运营商      {state.get('network_provider_fullname', '-')} ({state.get('network_type', '-')})",
                f"信号        {state.get('network_signalbar', '-')} 格, RSRP {state.get('Z5g_rsrp', state.get('network_lte_rsrp', '-'))} dBm",
                f"连接        {PPP_STATUS_LABELS.get(str(state.get('ppp_status')), str(state.get('ppp_status', '-')))}",
                f"电池        {_battery_text(state)}",
                f"实时速率    ↓ {_format_rate(state.get('flux_realtime_rx_thrpt'))}  ↑ {_format_rate(state.get('flux_realtime_tx_thrpt'))}",
                f"网络模式    {NET_MODE_LABELS.get(str(state.get('network_net_select')), str(state.get('network_net_select', '-')))}",
                f"SIM 卡      槽 {state.get('sim_slot', '-')}{'' if state.get('dual_sim_support') == '1' else ' (单卡)'}",
                f"WiFi       {'开' if _wifi_is_on(state) else '关'}",
                f"SSID        {', '.join(_ssid_list(state)) or '-'}",
                f"在线设备    {_station_count(state)}",
            ]
        ),
    )


@click.group()
def wifi() -> None:
    """Show or toggle the WiFi radio."""


@wifi.command("status")
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def wifi_status(host: str, as_json: bool) -> None:
    """Show the WiFi radio state and SSIDs."""
    state = _build_client(host).get(WIFI_STATE_CMDS)
    if as_json:
        payload = dict(state)
        payload["wifi_on"] = _wifi_is_on(state)
        _emit(True, payload, "")
        return
    lines = [
        f"WiFi       {'开' if _wifi_is_on(state) else '关'}",
        f"SSID        {', '.join(_ssid_list(state)) or '-'}",
        f"在线设备    {_station_count(state)}",
    ]
    _emit(False, state, "\n".join(lines))


def _set_wifi(host: str, as_json: bool, option: str, action: str, confirm_text: str) -> None:
    """Shared implementation of ``zte wifi on`` / ``zte wifi off``.

    Parameters
    ----------
    host : str
        Device hostname or IP.
    as_json : bool
        Whether JSON output was requested.
    option : str
        ``switchWiFiModule`` SwitchOption value ("0" on, "1" off).
    action : str
        Action name for the JSON payload (``wifi_on`` / ``wifi_off``).
    confirm_text : str
        Confirmation prompt text; empty skips the prompt.
    """
    if confirm_text:
        click.confirm(confirm_text, abort=True)
    client = _build_client(host)
    client.set("switchWiFiModule", {"SwitchOption": option})
    want_on = option == WIFI_OPTION_ON
    _poll_until(
        lambda: _wifi_is_on(client.get(WIFI_STATE_CMDS)) == want_on,
        WIFI_SETTLE_TIMEOUT_S,
    )
    final_state = client.get(WIFI_STATE_CMDS)
    payload = {
        "action": action,
        "result": "ok" if _wifi_is_on(final_state) == want_on else "timeout",
        "wifi_on": _wifi_is_on(final_state),
    }
    if as_json:
        _emit(True, payload, "")
    elif payload["result"] == "ok":
        _emit(False, payload, f"WiFi 已{'开启' if want_on else '关闭'}。")
    else:
        _emit(False, payload, "命令已发送，但状态未在预期时间内变化，请用 `zte wifi status` 确认。")
    if payload["result"] != "ok":
        raise SystemExit(1)


@wifi.command("on")
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def wifi_on(host: str, as_json: bool) -> None:
    """Turn the WiFi radio on."""
    _set_wifi(host, as_json, WIFI_OPTION_ON, "wifi_on", "")


@wifi.command("off")
@click.option("--force", is_flag=True, help="跳过交互确认。")
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def wifi_off(force: bool, host: str, as_json: bool) -> None:
    """Turn the WiFi radio off (asks for confirmation)."""
    _set_wifi(
        host,
        as_json,
        WIFI_OPTION_OFF,
        "wifi_off",
        "" if force else "确定关闭 WiFi？所有无线设备将断开连接",
    )


@click.group()
def sim() -> None:
    """Show or switch the active SIM slot."""


@sim.command("status")
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def sim_status(host: str, as_json: bool) -> None:
    """Show the active SIM slot."""
    state = _build_client(host).get(("sim_slot", "dual_sim_support"))
    _emit(
        as_json,
        state,
        f"SIM 卡      槽 {state.get('sim_slot', '-')}"
        f"{'' if state.get('dual_sim_support') == '1' else ' (单卡)'}",
    )


@sim.command("switch")
@click.argument("slot", type=click.IntRange(1, 2))
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def sim_switch(slot: int, host: str, as_json: bool) -> None:
    """Switch the active SIM slot and wait for the modem to settle."""
    client = _build_client(host)
    client.set("SET_SIM_SLOT", {"sim_slot": str(slot), "notCallback": "true"})
    if not as_json:
        click.echo("已发送切卡命令，等待 modem 重新驻网", nl=False)

    def switched() -> bool:
        result = str(client.get(("switch_sim_result",)).get("switch_sim_result", ""))
        if result == SIM_RESULT_OK:
            return True
        if result == SIM_RESULT_FAIL:
            raise DeviceError(f"切卡失败 (switch_sim_result={SIM_RESULT_FAIL})")
        return False

    done = _poll_until(switched, SIM_SWITCH_TIMEOUT_S, SIM_POLL_INTERVAL_S, progress=not as_json)
    if not as_json:
        click.echo()  # finish the progress dots line
    final = client.get(("sim_slot", "network_provider_fullname", "network_type"))
    outcome = "ok" if done else "timeout"
    payload = {
        "action": "sim_switch",
        "slot_requested": slot,
        "result": outcome,
        "sim_slot": final.get("sim_slot"),
        "operator": final.get("network_provider_fullname"),
        "network_type": final.get("network_type"),
    }
    if as_json:
        _emit(True, payload, "")
    elif outcome == "ok":
        _emit(
            False,
            payload,
            f"已切到槽 {final.get('sim_slot')}，运营商: "
            f"{final.get('network_provider_fullname', '-')} ({final.get('network_type', '-')})",
        )
    else:
        _emit(False, payload, f"切卡未在 {SIM_SWITCH_TIMEOUT_S:.0f}s 内完成，请用 `zte sim status` 确认。")
    if outcome != "ok":
        raise SystemExit(1)


@click.group()
def net() -> None:
    """Show or change the network mode."""


@net.command("status")
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def net_status(host: str, as_json: bool) -> None:
    """Show the current network mode."""
    state = _build_client(host).get(("network_net_select", "network_net_select_mode"))
    value = str(state.get("network_net_select", ""))
    _emit(
        as_json,
        state,
        f"网络模式    {NET_MODE_LABELS.get(value, value or '-')} ({value or '-'})",
    )


@net.command("mode")
@click.argument("mode", type=click.Choice(sorted(NET_MODES)))
@click.option("--host", default=DEFAULT_HOST, envvar="ZTE_HOST", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出原始字段。")
@handle_device_errors
def net_mode(mode: str, host: str, as_json: bool) -> None:
    """Change the network mode (auto/nsa/sa/4g3g/4g/3g)."""
    value, label = NET_MODES[mode]
    client = _build_client(host)
    client.set("SET_BEARER_PREFERENCE", {"BearerPreference": value})
    settled = _poll_until(
        lambda: str(client.get(("network_net_select",)).get("network_net_select", "")) == value,
        NET_MODE_SETTLE_TIMEOUT_S,
    )
    current = str(client.get(("network_net_select",)).get("network_net_select", ""))
    payload = {
        "action": "net_mode",
        "mode": mode,
        "requested": value,
        "current": current,
        "result": "ok" if settled else "pending",
    }
    if as_json:
        _emit(True, payload, "")
    elif settled:
        _emit(False, payload, f"网络模式已切换为 {label}。")
    else:
        _emit(False, payload, f"命令已发送，当前模式仍为 {NET_MODE_LABELS.get(current, current)}，可能仍在切换中。")
    if not settled:
        raise SystemExit(1)


main.add_command(wifi)
main.add_command(sim)
main.add_command(net)
