"""Canonical text form for corpus files: the bytes that define index_version."""

from __future__ import annotations

import hashlib
import unicodedata


def decode_utf8(raw: bytes, source: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{source}: not valid UTF-8 ({exc})") from exc


def normalize_text(text: str) -> str:
    """BOM removed, CRLF/CR → LF, Unicode NFC, trailing spaces stripped, one final newline.

    A CRLF checkout therefore yields exactly the same canonical text, and so the same
    index_version, as an LF checkout.
    """
    text = text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
