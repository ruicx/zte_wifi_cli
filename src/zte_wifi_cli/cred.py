"""Web console credential storage backed by the OS keychain.

On Windows the ``keyring`` package stores secrets in Windows Credential
Manager, so the device password never lands in a plaintext file. The CLI and
the agent skill read it from here; the password is never embedded in code.
"""

from keyring import get_password, set_password

SERVICE_NAME = "zte-wifi-cli"
"""Keyring service name under which the web console password is stored."""

ENTRY_NAME = "web-admin"
"""Keyring entry name for the web console password."""


def load_password() -> str | None:
    """Load the stored web console password.

    Returns
    -------
    str or None
        The stored password, or ``None`` when nothing has been stored yet.
    """
    return get_password(SERVICE_NAME, ENTRY_NAME)


def save_password(password: str) -> None:
    """Store (or overwrite) the web console password in the keychain.

    Parameters
    ----------
    password : str
        The plain web console password.
    """
    set_password(SERVICE_NAME, ENTRY_NAME, password)
