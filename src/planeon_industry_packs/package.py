"""Fixed-epoch, sorted, data-only pack archives."""

from __future__ import annotations

import gzip
import io
import os
import tarfile
from pathlib import Path

from .canonical import canonical_json_bytes
from .errors import PackValidationError
from .index import build_index
from .loader import load_pack

FIXED_EPOCH = 946684800


def _tar_member(name: str, data: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mode = 0o644
    info.mtime = FIXED_EPOCH
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info, data


def archive_bytes(root: Path, *, common_root: Path | None = None) -> tuple[str, bytes]:
    pack = load_pack(root, common_root=common_root)
    index = build_index(root, common_root=common_root)
    members = dict(pack.files)
    members["pack.index.json"] = canonical_json_bytes(index) + b"\n"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(members.items()):
            info, content = _tar_member(name, data)
            archive.addfile(info, io.BytesIO(content))
    gzip_buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gzip_buffer, mtime=0, compresslevel=9) as stream:
        stream.write(tar_buffer.getvalue())
    metadata = pack.manifest["metadata"]
    return f"{metadata['id']}-{metadata['version']}.tar.gz", gzip_buffer.getvalue()


def package_pack(root: Path, output_directory: Path, *, common_root: Path | None = None) -> Path:
    if output_directory.exists() or output_directory.is_symlink():
        raise PackValidationError("OUTPUT_EXISTS", "package output directory must not already exist", path=str(output_directory))
    name, data = archive_bytes(root, common_root=common_root)
    try:
        output_directory.mkdir(mode=0o755, parents=False, exist_ok=False)
        output = output_directory / name
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(descriptor, data)
        finally:
            os.close(descriptor)
        return output
    except Exception:
        if output_directory.is_dir() and not any(output_directory.iterdir()):
            output_directory.rmdir()
        raise

