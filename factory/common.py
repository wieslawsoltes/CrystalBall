"""Validation and private-file primitives shared by factory tools (Python 3.11+)."""
from __future__ import annotations
import ipaddress
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]

def unit_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
        raise ValueError("Unit ID must contain 1-32 ASCII letters, digits, '-' or '_'")
    return value

def token(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value):
        raise ValueError("Device token must contain 32-128 URL-safe characters")
    return value

def origin(value: str) -> str:
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) >= 127 for c in value) or '\\' in value:
        raise ValueError("Gateway origin must be ASCII HTTPS without whitespace or backslashes")
    try:
        url = urlsplit(value)
        port = url.port
        host = url.hostname
        if url.scheme != 'https' or not host or url.username is not None or url.password is not None:
            raise ValueError()
        if url.netloc.endswith(':') or url.path not in ('', '/') or url.query or url.fragment or '?' in value or '#' in value:
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', s) for s in host.split('.')):
                raise ValueError()
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
    except ValueError as exc:
        raise ValueError("Use an HTTPS origin, e.g. https://orb-gateway.home.arpa, without path or credentials") from exc
    result = urlunsplit(('https', url.netloc.lower(), '', '', ''))
    if len(result.encode('ascii')) > 191:
        raise ValueError('Gateway origin exceeds firmware capacity')
    return result

def wifi(ssid: str, password: str) -> tuple[str, str]:
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in ssid):
        raise ValueError('SSID must contain 1-32 UTF-8 bytes without control characters')
    if not isinstance(password, str):
        raise ValueError('Wi-Fi password must be a string')
    if re.fullmatch(r'[0-9A-Fa-f]{64}', password):
        return ssid, password
    if not 8 <= len(password.encode('utf-8')) <= 63 or any(ord(c) < 32 for c in password):
        raise ValueError('WPA2 passphrase must contain 8-63 UTF-8 bytes, or be 64 hexadecimal digits')
    return ssid, password

def private_write(path: Path, data: str | bytes) -> None:
    """Exclusive create: do not follow a final symlink or overwrite existing credentials."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = data.encode('utf-8') if isinstance(data, str) else data
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise

def private_json(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing a symbolic-link credential file')
    if os.name != 'nt' and path.stat().st_mode & 0o077:
        raise ValueError('Credential file must not be accessible to group/others; use chmod 600')
    if path.stat().st_size > 16384:
        raise ValueError('Credential file is unexpectedly large')
    result = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(result, dict):
        raise ValueError('Expected a JSON object')
    return result


def artifact_hash(root: Path, name: str) -> str:
    if not isinstance(name,str) or '\\' in name:
        raise ValueError('Artifact requires a relative POSIX path')
    rel=PurePosixPath(name)
    if rel.is_absolute() or not rel.parts or '..' in rel.parts or str(rel)!=name:
        raise ValueError('Unsafe artifact path')
    base=root.resolve(); path=base
    for part in rel.parts:
        path=path/part
        if path.is_symlink():raise ValueError('Artifact path cannot traverse symbolic links')
    if not path.resolve().is_relative_to(base) or not path.is_file():
        raise ValueError('Artifact is not a regular in-root file')
    digest=hashlib.sha256();total=0
    with path.open('rb') as stream:
        while data:=stream.read(65536):
            total+=len(data)
            if total>64*1024*1024:raise ValueError('Evidence artifact exceeds 64 MiB')
            digest.update(data)
    if total==0:raise ValueError('Empty evidence is not accepted')
    return digest.hexdigest()

