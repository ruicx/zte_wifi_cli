"""Hashing helpers matching the device web UI's JavaScript conventions.

The device firmware hashes passwords and request signatures with SHA-256 and
compares them as **uppercase** hexadecimal strings (see ``js/util.js`` on the
device: ``paswordAlgorithmsCookie`` / ``cookWithRequest``). Using the wrong
case for the intermediate digest yields a different final hash, so the case
convention is part of the protocol.
"""

import hashlib


def sha256_upper(text: str) -> str:
    """Return the SHA-256 digest of a UTF-8 string as uppercase hex.

    Parameters
    ----------
    text : str
        Input string to hash.

    Returns
    -------
    str
        Uppercase hexadecimal SHA-256 digest.

    Notes
    -----
    The device JavaScript returns uppercase hex from its SHA-256
    implementation; the uppercase form is fed into subsequent hashing rounds.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()
