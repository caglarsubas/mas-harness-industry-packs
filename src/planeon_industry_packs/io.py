"""Fail-closed pack filesystem and structured-data loading."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .canonical import sha256_bytes
from .errors import PackValidationError

MAX_FILE_BYTES = 2 * 1024 * 1024
ALLOWED_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".txt", ".csv", ".jsonl", ".rdf", ".ttl", ".owl"}
EXECUTABLE_SUFFIXES = {".py", ".sh", ".js", ".ts", ".rb", ".pl", ".ps1", ".bat", ".cmd", ".exe", ".dll", ".so", ".dylib", ".jar", ".wasm"}
MEDIA_TYPES = {
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".jsonl": "application/x-ndjson",
    ".rdf": "application/rdf+xml",
    ".ttl": "text/turtle",
    ".owl": "application/rdf+xml",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise PackValidationError("DUPLICATE_KEY", f"duplicate YAML key {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def normalize_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise PackValidationError("PATH_INVALID", "path must be a non-empty relative POSIX path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise PackValidationError("PATH_TRAVERSAL", "absolute, empty, dot, and parent segments are forbidden", path=value)
    if any(part.startswith(".") for part in parsed.parts):
        raise PackValidationError("HIDDEN_PATH", "hidden paths are forbidden", path=value)
    return parsed.as_posix()


def _read_regular(path: Path, relative: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise PackValidationError("FILE_OPEN_REFUSED", str(exc), path=relative) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PackValidationError("NON_REGULAR_FILE", "only regular files are admitted", path=relative)
        if metadata.st_mode & 0o111:
            raise PackValidationError("EXECUTABLE_MODE", "executable mode bits are forbidden", path=relative)
        if metadata.st_size > MAX_FILE_BYTES:
            raise PackValidationError("FILE_TOO_LARGE", f"file exceeds {MAX_FILE_BYTES} bytes", path=relative)
        chunks: list[bytes] = []
        remaining = MAX_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_FILE_BYTES:
            raise PackValidationError("FILE_TOO_LARGE", f"file exceeds {MAX_FILE_BYTES} bytes", path=relative)
        return data
    finally:
        os.close(descriptor)


def inventory(root: Path) -> dict[str, bytes]:
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise PackValidationError("PACK_ROOT_MISSING", str(exc)) from exc
    if root.is_symlink() or not stat.S_ISDIR(root_stat.st_mode):
        raise PackValidationError("PACK_ROOT_INVALID", "pack root must be an explicit regular directory")
    files: dict[str, bytes] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise PackValidationError("DIRECTORY_READ_REFUSED", str(exc)) from exc
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            normalize_relative(relative)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise PackValidationError("METADATA_READ_REFUSED", str(exc), path=relative) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise PackValidationError("LINK_FORBIDDEN", "symbolic links are forbidden", path=relative)
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(Path(entry.path))
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise PackValidationError("NON_REGULAR_FILE", "devices and special files are forbidden", path=relative)
            suffix = Path(relative).suffix.casefold()
            if suffix in EXECUTABLE_SUFFIXES:
                raise PackValidationError("EXECUTABLE_CONTENT", "executable suffix is forbidden", path=relative)
            if suffix not in ALLOWED_SUFFIXES:
                raise PackValidationError("UNKNOWN_MEDIA_TYPE", f"unsupported suffix {suffix or '<none>'}", path=relative)
            files[relative] = _read_regular(Path(entry.path), relative)
    return dict(sorted(files.items()))


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackValidationError("DUPLICATE_KEY", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_structured(data: bytes, path: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackValidationError("UTF8_REQUIRED", "pack files must be UTF-8", path=path) from exc
    if "\x00" in text:
        raise PackValidationError("NUL_FORBIDDEN", "NUL bytes are forbidden", path=path)
    try:
        if Path(path).suffix.casefold() == ".json":
            return json.loads(text, object_pairs_hook=_json_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except PackValidationError:
        raise
    except (json.JSONDecodeError, yaml.YAMLError, ValueError, TypeError) as exc:
        raise PackValidationError("STRUCTURED_DATA_INVALID", str(exc), path=path) from exc


def sha256_file_bytes(files: dict[str, bytes], path: str) -> str:
    try:
        return sha256_bytes(files[path])
    except KeyError as exc:
        raise PackValidationError("BOUND_FILE_MISSING", "bound file is absent", path=path) from exc


def media_type(path: str) -> str:
    return MEDIA_TYPES[Path(path).suffix.casefold()]

