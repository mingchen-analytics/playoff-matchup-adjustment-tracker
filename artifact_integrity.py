"""Text artifact integrity across Git LF and Windows CRLF checkouts."""

import hashlib


def matches_text_sha256(path, expected):
    """Accept LF/CRLF conversion only; all other bytes remain significant."""
    data = path.read_bytes()
    return expected in {
        hashlib.sha256(data).hexdigest(),
        hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
    }
