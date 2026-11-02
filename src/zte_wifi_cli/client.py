"""HTTP client for the ZTE U30Air portable hotspot web console API.

Implements the three protocol building blocks reverse-engineered from the
device web UI (all verified live against firmware F50ProV1.0.0B28):

1. **Login** -- a challenge-response scheme:
   ``password = SHA256_upper(SHA256_upper(pw) + LD)`` where ``LD`` is fetched
   from ``cmd=LD``. A successful login keeps the ``JSESSIONID`` session
   cookie for subsequent requests.
2. **Reads** -- ``GET /goform/goform_get_cmd_process?multi_data=1&cmd=a,b,c``.
3. **Writes** -- ``POST /goform/goform_set_cmd_process`` with ``goformId`` plus
   an ``AD`` signature: ``AD = SHA256_upper(SHA256_upper(rd0 + rd1) + RD)``
   where ``RD`` is a per-request challenge and ``rd0``/``rd1`` are the
   firmware version strings (``wa_inner_version`` / ``cr_version``).
"""

from collections.abc import Iterable, Mapping
from typing import Any

import requests

from .crypto import sha256_upper

DEFAULT_HOST = "192.168.0.1"
"""Default device address (reachable over the hotspot's WiFi or USB link)."""

_GET_PATH = "/goform/goform_get_cmd_process"
_SET_PATH = "/goform/goform_set_cmd_process"

_LOGIN_ERROR_MESSAGES: dict[str, str] = {
    "1": "login failed",
    "2": "another session is logged in; wait a few seconds and retry",
    "3": "wrong password",
    "5": "device requires on-screen (LCD) confirmation",
}


class ZteError(Exception):
    """Base class for all device communication errors."""


class UnreachableError(ZteError):
    """The device cannot be reached over the network."""


class AuthError(ZteError):
    """The device rejected our credentials."""


class DeviceError(ZteError):
    """The device responded with an unexpected or failing result."""


class ZteClient:
    """Stateful client that logs in on demand and signs write commands."""

    def __init__(self, host: str, password: str, timeout: float = 10.0) -> None:
        """Create a client for one device.

        Parameters
        ----------
        host : str
            Device hostname or IP (e.g. ``192.168.0.1``).
        password : str
            Web console password in plain text.
        timeout : float, optional
            Per-request timeout in seconds.
        """
        self._base_url = f"http://{host}"
        self._password = password
        self._timeout = timeout
        self._session = requests.Session()
        # The device lives on the LAN; never route through system proxies.
        self._session.trust_env = False
        self._logged_in = False
        self._rd_pair: tuple[str, str] | None = None

    def login(self) -> None:
        """Authenticate against the web console.

        Raises
        ------
        AuthError
            If the device rejects the credentials.
        DeviceError
            If the device does not provide a login challenge.
        UnreachableError
            If the device cannot be reached.
        """
        challenge = str(self._get_json({"isTest": "false", "cmd": "LD"}).get("LD", ""))
        if not challenge:
            raise DeviceError("device did not return a login challenge (LD)")
        digest = sha256_upper(sha256_upper(self._password) + challenge)
        response = self._post_json(
            {"isTest": "false", "goformId": "LOGIN", "password": digest}
        )
        result = str(response.get("result", ""))
        if result != "0":
            message = _LOGIN_ERROR_MESSAGES.get(result, f"login failed (result={result})")
            raise AuthError(message)
        self._logged_in = True

    def get(self, cmds: Iterable[str]) -> dict[str, Any]:
        """Read status fields from the device.

        Parameters
        ----------
        cmds : iterable of str
            Field names to read, e.g. ``("sim_slot", "ppp_status")``.

        Returns
        -------
        dict
            Mapping of field name to value, exactly as the device reports.

        Raises
        ------
        AuthError
            If login fails (performed on demand).
        DeviceError
            If the device returns a non-JSON or failing response.
        UnreachableError
            If the device cannot be reached.
        """
        self._ensure_logged_in()
        params = {"isTest": "false", "multi_data": "1", "cmd": ",".join(cmds)}
        return self._get_json(params)

    def set(self, goform_id: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        """Execute a write command with a fresh ``AD`` signature.

        Parameters
        ----------
        goform_id : str
            The command identifier, e.g. ``"switchWiFiModule"``.
        params : mapping of str to str, optional
            Additional command parameters.

        Returns
        -------
        dict
            The device response; write commands succeed with
            ``{"result": "success"}``.

        Raises
        ------
        AuthError
            If login fails (performed on demand).
        DeviceError
            If the device does not report success.
        UnreachableError
            If the device cannot be reached.
        """
        self._ensure_logged_in()
        body: dict[str, str] = {
            "isTest": "false",
            "goformId": goform_id,
            "AD": self._access_id(),
        }
        if params is not None:
            body.update(params)
        response = self._post_json(body)
        if str(response.get("result", "")) != "success":
            raise DeviceError(f"{goform_id} failed: {response!r}")
        return response

    def _ensure_logged_in(self) -> None:
        """Log in lazily before the first authenticated request."""
        if not self._logged_in:
            self.login()

    def _access_id(self) -> str:
        """Compute the ``AD`` signature for one write command.

        Returns
        -------
        str
            ``SHA256_upper(SHA256_upper(rd0 + rd1) + RD)`` with a fresh
            per-request ``RD`` challenge; the firmware version pair is cached
            on first use.

        Raises
        ------
        DeviceError
            If the device does not provide the ``RD`` challenge.

        Notes
        -----
        ``rd0``/``rd1`` mirror the web UI globals of the same name, which are
        populated from ``wa_inner_version`` and ``cr_version``.
        """
        if self._rd_pair is None:
            versions = self._get_json(
                {
                    "isTest": "false",
                    "multi_data": "1",
                    "cmd": "Language,cr_version,wa_inner_version",
                }
            )
            self._rd_pair = (
                str(versions.get("wa_inner_version", "")),
                str(versions.get("cr_version", "")),
            )
        challenge = str(self._get_json({"isTest": "false", "cmd": "RD"}).get("RD", ""))
        if not challenge:
            raise DeviceError("device did not return a write challenge (RD)")
        rd0, rd1 = self._rd_pair
        return sha256_upper(sha256_upper(rd0 + rd1) + challenge)

    def _get_json(self, params: Mapping[str, str]) -> dict[str, Any]:
        """Issue a GET request and parse the JSON response.

        Parameters
        ----------
        params : mapping of str to str
            Query parameters.

        Returns
        -------
        dict
            Parsed response body.

        Raises
        ------
        DeviceError
            On non-200 status or a non-object JSON body.
        UnreachableError
            On connection errors or timeouts.
        """
        try:
            response = self._session.get(
                self._base_url + _GET_PATH, params=params, timeout=self._timeout
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise UnreachableError(f"cannot reach device at {self._base_url}") from exc
        return _parse_json(response)

    def _post_json(self, data: Mapping[str, str]) -> dict[str, Any]:
        """Issue a form POST and parse the JSON response.

        Parameters
        ----------
        data : mapping of str to str
            Form fields to post.

        Returns
        -------
        dict
            Parsed response body.

        Raises
        ------
        DeviceError
            On non-200 status or a non-object JSON body.
        UnreachableError
            On connection errors or timeouts.
        """
        try:
            response = self._session.post(
                self._base_url + _SET_PATH, data=data, timeout=self._timeout
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise UnreachableError(f"cannot reach device at {self._base_url}") from exc
        return _parse_json(response)


def _parse_json(response: requests.Response) -> dict[str, Any]:
    """Validate and parse a device HTTP response as a JSON object.

    Parameters
    ----------
    response : requests.Response
        The raw HTTP response.

    Returns
    -------
    dict
        Parsed JSON object.

    Raises
    ------
    DeviceError
        If the status is not 200 or the body is not a JSON object.
    """
    if response.status_code != 200:
        raise DeviceError(f"unexpected HTTP {response.status_code} from device")
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise DeviceError("device returned a non-JSON response (rebooting?)") from exc
    if not isinstance(payload, dict):
        raise DeviceError("unexpected device response shape")
    return payload
