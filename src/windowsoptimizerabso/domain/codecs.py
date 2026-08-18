"""Canonical encoding for captured state.

Two jobs, both load-bearing for rollback:

1. **Round-trip fidelity.** Captured state goes into a journal as JSON and comes back out to be
   written over a live machine. If the encoding is lossy, rollback restores something that is not
   what was there. The baseline could not survive this at all: ``REG_BINARY`` values are ``bytes``,
   and ``json.dumps`` raises ``TypeError`` on ``bytes``, so any operation touching binary registry
   data produced a session file that could not be written -- and the failure surfaced at save time,
   after the mutation had already happened (defect CORE-007).

2. **Canonical form.** Plan digests and state-equality checks compare encodings, so the same value
   must always encode to the same bytes: sorted keys, no insignificant whitespace, UTF-8, and no
   dependence on dict insertion order.

The tagged-union encoding uses a reserved ``__type__`` key. Payloads that legitimately contain that
key are escaped on the way in and unescaped on the way out, so a registry string value of
``{"__type__": "bytes"}`` cannot forge a decoded type.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

#: Bumped when the encoding changes in a way that old journals cannot be read under. Stored
#: alongside every persisted blob so a migration can be selected rather than guessed.
CODEC_VERSION = 1

_TYPE_KEY = "__type__"
_ESCAPE_KEY = "__escaped__"


class DecodeError(ValueError):
    """Raised when persisted state cannot be decoded. Never silently degraded to a default.

    A journal that returns a plausible-but-wrong pre-state is more dangerous than one that refuses
    to roll back, because the wrong value gets written over a live machine.
    """


def encode(value: Any) -> Any:
    """Convert a captured value into JSON-safe form, preserving exact type."""
    if isinstance(value, bytes):
        return {_TYPE_KEY: "bytes", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, bytearray):
        return {_TYPE_KEY: "bytes", "data": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("refusing to encode a naive datetime: timezone is required")
        return {_TYPE_KEY: "datetime", "data": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, tuple):
        # Registry REG_MULTI_SZ is an ordered sequence; tuples survive as lists but are tagged so
        # that a decoded multi-string is not confused with a JSON array of unrelated values.
        return {_TYPE_KEY: "tuple", "data": [encode(v) for v in value]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        if _TYPE_KEY in value or _ESCAPE_KEY in value:
            # Escape rather than reject: a registry value really can contain these keys, and losing
            # it would be a silent capture failure.
            return {_ESCAPE_KEY: True, "data": {str(k): encode(v) for k, v in value.items()}}
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"cannot encode {type(value).__name__} into captured state")


def decode(value: Any) -> Any:
    """Inverse of :func:`encode`. Raises :class:`DecodeError` on anything malformed."""
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value

    if value.get(_ESCAPE_KEY) is True:
        payload = value.get("data")
        if not isinstance(payload, dict):
            raise DecodeError("escaped payload is not an object")
        return {k: decode(v) for k, v in payload.items()}

    tag = value.get(_TYPE_KEY)
    if tag is None:
        return {k: decode(v) for k, v in value.items()}

    data = value.get("data")
    try:
        if tag == "bytes":
            if not isinstance(data, str):
                raise DecodeError("bytes payload is not a string")
            return base64.b64decode(data, validate=True)
        if tag == "datetime":
            if not isinstance(data, str):
                raise DecodeError("datetime payload is not a string")
            parsed = datetime.fromisoformat(data)
            if parsed.tzinfo is None:
                raise DecodeError("persisted datetime has no timezone")
            return parsed
        if tag == "tuple":
            if not isinstance(data, list):
                raise DecodeError("tuple payload is not an array")
            return tuple(decode(v) for v in data)
    except (ValueError, TypeError) as exc:
        raise DecodeError(f"could not decode tagged value {tag!r}: {exc}") from exc

    raise DecodeError(f"unknown tagged type {tag!r}")


def canonical_json(value: Any) -> str:
    """Deterministic JSON text for an already-encoded structure.

    Sorted keys and tight separators, so equal values always produce equal text and therefore equal
    digests. ``ensure_ascii`` is off so that non-ASCII data is compared as characters rather than
    as escape sequences that vary by encoder.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    """SHA-256 over the canonical encoding of ``value``.

    SHA-256, not MD5: the baseline used MD5 for backup checksums and never verified them
    (defect BAK-005). These digests decide whether a journal blob is trustworthy enough to write
    back over a live machine, so a collision-resistant hash is the minimum bar.
    """
    return hashlib.sha256(canonical_json(encode(value)).encode("utf-8")).hexdigest()


def dumps(value: Any) -> str:
    """Encode and serialise in one step, for storing captured state."""
    return canonical_json(encode(value))


def loads(text: str) -> Any:
    """Deserialise and decode in one step."""
    try:
        return decode(json.loads(text))
    except json.JSONDecodeError as exc:
        raise DecodeError(f"stored state is not valid JSON: {exc}") from exc


def states_equal(left: Any, right: Any) -> bool:
    """Exact equality over captured state.

    Used to prove that rollback restored what was captured, so it compares canonical encodings
    rather than Python objects: ``b"\\x01"`` and ``[1]`` are different captured states even though
    a looser comparison might treat them as equivalent, and ``1`` is not ``True``.
    """
    return canonical_json(encode(left)) == canonical_json(encode(right))
