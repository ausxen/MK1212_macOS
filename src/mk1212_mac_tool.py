#!/usr/bin/env python3
"""Reversible native macOS launcher and compatibility builder for MK1212.

Workshop packs and the signed Feral application are read-only inputs.  The
tool creates APFS clone-on-write movie packs, loose winning Lua files, DDS
repair overlays, an isolated Feral launcher preference tree, and a ledger.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import math
import os
import re
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, Iterable


APP_ID = "325610"
TOOL_VERSION = "0.7.0"
PROFILE_COMPATIBILITY_REVISION = "mac-runtime-slots-hide-windows-ui-v2"
SUPPORTED_RUNTIME_EXECUTABLE_SHA256 = (
    "13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e"
)
DEFAULT_STATE = Path.home() / "Library/Application Support/MK1212 Mac Launcher"
FERAL_STATE = Path.home() / "Library/Application Support/Feral Interactive/Total War ATTILA"
GENERATED_PREFIX = "zzz_mk1212shim_"
EXECUTABLE_RELATIVE = Path("Total War ATTILA.app/Contents/MacOS/Total War ATTILA")
NATIVE_CLONE_DIRNAME = "Total War ATTILA MK1212.app"

# Feral 1.6.1 build 480285.103778, arm64.  Each context is the exact three
# instruction sequence: store capital, set maximum slots, store it.  The tool
# changes only the middle ARM64 instruction in a private, locally generated
# clone.  It refuses every other binary or byte sequence.
NATIVE_SLOT_PATCHES = (
    {
        "virtual_address": 0x103457244,
        "file_offset": 0x03457244,
        "before_context": bytes.fromhex("08c00139c8008052087400b9"),
        "after_context": bytes.fromhex("08c0013948018052087400b9"),
    },
    {
        "virtual_address": 0x1034577F4,
        "file_offset": 0x034577F4,
        "before_context": bytes.fromhex("08c00139c8008052087400b9"),
        "after_context": bytes.fromhex("08c0013948018052087400b9"),
    },
)
SUPPORTED_NATIVE_EXECUTABLES = {
    "13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e": {
        "feral_version": "1.6.1",
        "feral_build": "480285.103778",
    },
}
CANONICAL_PACKS = [
    ("1934544571", "1-1212scripts.pack"),
    ("3010246623", "Custom cities beta.pack"),
    ("1429109380", "1212compbuild_v2.pack"),
    ("1429140619", "1212models1_v2.pack"),
    ("1371434091", "1212models2.pack"),
    ("1371420895", "1212models3.pack"),
    ("1371491650", "1212models4.pack"),
    ("1592154821", "1212models5.pack"),
    ("1934591700", "1212models6.pack"),
    ("2221976170", "1212models7.pack"),
    ("2660365008", "1212models8.pack"),
    ("3003589041", "1212models9.pack"),
    ("1582067661", "1212music.pack"),
]
STOCK_PACK_NAMES = {
    "blood.pack", "boot.pack", "charlemagne.pack", "data.pack", "models.pack",
    "models2.pack", "models3.pack", "movies.pack", "music.pack", "slavs.pack",
    "sound.pack", "terrain.pack", "terrain2.pack", "tiles.pack", "tiles2.pack",
    "tiles3.pack", "tiles4.pack", "local_en.pack", "local_en_shared_rome2.pack",
    "music_en_shared_rome2.pack",
}


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackEntry:
    internal_path: str
    relative_path: str
    size: int
    offset: int
    path_offset: int


@dataclass(frozen=True)
class DDSInfo:
    width: int
    height: int
    mip_count: int
    fourcc: str
    rgb_bits: int
    pf_flags: int
    pitch_or_linear: int
    flags: int
    caps: int
    caps2: int
    depth: int
    masks: tuple[int, int, int, int]
    byte_size: int

    @property
    def effective_mips(self) -> int:
        return max(1, self.mip_count)

    @property
    def full_mips(self) -> int:
        return int(math.floor(math.log2(max(self.width, self.height)))) + 1

    @property
    def format_name(self) -> str:
        return self.fourcc if self.fourcc else f"RGB{self.rgb_bits}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path_with_progress(path: Path, progress: Callable[[str], None]) -> str:
    """Hash a Workshop source while leaving visible progress breadcrumbs."""
    total = path.stat().st_size
    digest = hashlib.sha256()
    done = 0
    next_report = 25
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            done += len(chunk)
            percent = 100 if total == 0 else min(100, int(done * 100 / total))
            if percent >= next_report:
                progress(f"Hashing {path.name}: {percent}%")
                next_report += 25
    if next_report <= 100:
        progress(f"Hashing {path.name}: 100%")
    return digest.hexdigest()


def report_rebuild_progress(state_dir: Path, message: str, notify: bool = False) -> None:
    """Persist rebuild status and best-effort a non-blocking macOS notification."""
    now = utc_now()
    log_dir = Path.home() / "Library/Logs/MK1212 Mac Launcher"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "rebuild-progress.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{now}\t{message}\n")
        save_json(state_dir / "rebuild-progress.json", {"updated_at": now, "message": message})
    except OSError:
        # Progress reporting must never make the compatibility rebuild fail.
        pass
    if notify:
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display notification "{escaped}" with title "MK1212 Mac Launcher"'
        try:
            subprocess.run(["/usr/bin/osascript", "-e", script],
                           capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def quick_fingerprint(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha256(struct.pack("<Q", size))
    with path.open("rb") as stream:
        head = stream.read(min(size, 2 * 1024 * 1024))
        digest.update(head)
        if size > 4 * 1024 * 1024:
            stream.seek(size - 2 * 1024 * 1024)
            digest.update(stream.read(2 * 1024 * 1024))
    return digest.hexdigest()


def safe_relative_path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(p in ("", ".", "..") for p in path.parts):
        raise ToolError(f"unsafe pack path: {raw!r}")
    return path.as_posix()


def read_pack(path: Path) -> tuple[dict, list[PackEntry]]:
    total = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(24)
        if len(header) != 24:
            raise ToolError(f"truncated PFH4 header: {path}")
        sig, kind, dep_count, dep_bytes, file_count, index_bytes = struct.unpack("<4s5I", header)
        if sig != b"PFH4":
            raise ToolError(f"unsupported pack signature in {path}: {sig!r}")
        if dep_count or dep_bytes:
            raise ToolError(f"dependency-bearing PFH4 is not supported: {path}")
        index = stream.read(index_bytes + 4)
    if len(index) != index_bytes + 4:
        raise ToolError(f"truncated PFH4 index: {path}")
    pos = 4
    raw: list[tuple[str, str, int, int]] = []
    for _ in range(file_count):
        if pos + 4 > len(index):
            raise ToolError(f"PFH4 index ended early: {path}")
        size = struct.unpack_from("<I", index, pos)[0]
        pos += 4
        path_offset = 24 + pos
        try:
            end = index.index(0, pos)
        except ValueError as exc:
            raise ToolError(f"unterminated PFH4 path in {path}") from exc
        raw_path = index[pos:end]
        try:
            internal = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            # A few stock CA indexes contain legacy Windows-1252 names.  They
            # are read only for path comparison and are never rewritten.
            internal = raw_path.decode("cp1252")
        pos = end + 1
        raw.append((internal, safe_relative_path(internal), size, path_offset))
    if pos != len(index):
        raise ToolError(f"unexpected PFH4 index trailer in {path}: {len(index) - pos} bytes")
    offset = 28 + index_bytes
    entries: list[PackEntry] = []
    for internal, relative, size, path_offset in raw:
        entries.append(PackEntry(internal, relative, size, offset, path_offset))
        offset += size
    if offset != total:
        raise ToolError(f"PFH4 size mismatch for {path}: index={offset}, file={total}")
    return ({
        "signature": "PFH4", "pack_type": kind, "file_count": file_count,
        "file_index_bytes": index_bytes, "index_timestamp": struct.unpack_from("<I", index, 0)[0],
        "pack_bytes": total,
    }, entries)


def read_entry(stream: BinaryIO, entry: PackEntry) -> bytes:
    stream.seek(entry.offset)
    data = stream.read(entry.size)
    if len(data) != entry.size:
        raise ToolError(f"truncated member: {entry.internal_path}")
    return data


def parse_dds(data: bytes) -> DDSInfo:
    if len(data) < 128 or data[:4] != b"DDS " or struct.unpack_from("<I", data, 4)[0] != 124:
        raise ToolError("invalid legacy DDS header")
    flags, height, width, pitch, depth, mips = struct.unpack_from("<6I", data, 8)
    pf_size, pf_flags = struct.unpack_from("<2I", data, 76)
    if pf_size != 32 or width < 1 or height < 1:
        raise ToolError("invalid DDS dimensions or pixel-format header")
    fourcc = data[84:88].rstrip(b"\0").decode("ascii", errors="replace")
    rgb_bits = struct.unpack_from("<I", data, 88)[0]
    masks = struct.unpack_from("<4I", data, 92)
    caps = struct.unpack_from("<I", data, 108)[0]
    caps2 = struct.unpack_from("<I", data, 112)[0]
    return DDSInfo(width, height, mips, fourcc, rgb_bits, pf_flags, pitch, flags, caps, caps2,
                   max(1, depth), masks, len(data))


def dds_level_size(info: DDSInfo, width: int, height: int) -> int:
    if info.fourcc == "DXT1":
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8
    if info.fourcc in ("DXT3", "DXT5"):
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    if not info.fourcc and info.rgb_bits == 32:
        return width * height * 4
    raise ToolError(f"unsupported DDS format: {info.format_name}")


def split_dds_levels(data: bytes, info: DDSInfo) -> list[bytes]:
    if info.caps2 & 0x200 or info.depth > 1:
        raise ToolError("cubemap/volume DDS transformation is not supported")
    levels, pos, width, height = [], 128, info.width, info.height
    for _ in range(info.effective_mips):
        size = dds_level_size(info, width, height)
        levels.append(data[pos:pos + size])
        if len(levels[-1]) != size:
            raise ToolError("DDS mip data is truncated")
        pos += size
        width, height = max(1, width // 2), max(1, height // 2)
    if pos != len(data):
        raise ToolError(f"DDS has {len(data) - pos} unaccounted bytes")
    return levels


def validate_dds_size(data: bytes, info: DDSInfo) -> None:
    width, height = info.width, info.height
    per_surface = 0
    for _ in range(info.effective_mips):
        per_surface += dds_level_size(info, width, height)
        width, height = max(1, width // 2), max(1, height // 2)
    surfaces = 6 if info.caps2 & 0x200 else 1
    if info.depth > 1:
        # Legacy volume layouts shrink depth with each level; avoid guessing.
        raise ToolError("volume DDS validation is not supported")
    expected = 128 + per_surface * surfaces
    if len(data) != expected:
        raise ToolError(f"DDS byte count is {len(data)}, expected {expected}")


def patch_dds_header(header: bytes, width: int, height: int, mips: int, linear: int) -> bytes:
    out = bytearray(header[:128])
    flags = struct.unpack_from("<I", out, 8)[0] | 0x20000
    caps = struct.unpack_from("<I", out, 108)[0] | 0x8 | 0x400000
    struct.pack_into("<I", out, 8, flags)
    struct.pack_into("<I", out, 12, height)
    struct.pack_into("<I", out, 16, width)
    struct.pack_into("<I", out, 20, linear)
    struct.pack_into("<I", out, 28, mips)
    struct.pack_into("<I", out, 108, caps)
    return bytes(out)


def downsample_rgba32(raw: bytes, width: int, height: int) -> tuple[bytes, int, int]:
    new_w, new_h = max(1, width // 2), max(1, height // 2)
    out = bytearray(new_w * new_h * 4)
    for y in range(new_h):
        ys = (min(height - 1, y * 2), min(height - 1, y * 2 + 1))
        for x in range(new_w):
            xs = (min(width - 1, x * 2), min(width - 1, x * 2 + 1))
            points = [((yy * width + xx) * 4) for yy in ys for xx in xs]
            base = (y * new_w + x) * 4
            for channel in range(4):
                out[base + channel] = sum(raw[p + channel] for p in points) // 4
    return bytes(out), new_w, new_h


def upscale_rgba32(raw: bytes, width: int, height: int) -> tuple[bytes, int, int]:
    new_w, new_h = width * 2, height * 2
    out = bytearray(new_w * new_h * 4)
    for y in range(new_h):
        for x in range(new_w):
            src = ((y // 2) * width + (x // 2)) * 4
            dst = (y * new_w + x) * 4
            out[dst:dst + 4] = raw[src:src + 4]
    return bytes(out), new_w, new_h


def expand_block_indices(value: int, bits: int, qx: int, qy: int) -> int:
    mask = (1 << bits) - 1
    matrix = [[(value >> (bits * (y * 4 + x))) & mask for x in range(4)] for y in range(4)]
    child = 0
    for y in range(4):
        for x in range(4):
            item = matrix[qy * 2 + y // 2][qx * 2 + x // 2]
            child |= item << (bits * (y * 4 + x))
    return child


def upscale_dxt(raw: bytes, width: int, height: int, fourcc: str) -> tuple[bytes, int, int]:
    if width % 4 or height % 4:
        raise ToolError(f"{fourcc} promotion requires dimensions divisible by four")
    block_size = 8 if fourcc == "DXT1" else 16
    src_bw, src_bh = width // 4, height // 4
    out = bytearray(width * 2 // 4 * (height * 2 // 4) * block_size)
    out_bw = width * 2 // 4
    for by in range(src_bh):
        for bx in range(src_bw):
            block = raw[(by * src_bw + bx) * block_size:(by * src_bw + bx + 1) * block_size]
            if len(block) != block_size:
                raise ToolError(f"truncated {fourcc} block")
            for qy in range(2):
                for qx in range(2):
                    if fourcc == "DXT1":
                        color = expand_block_indices(int.from_bytes(block[4:8], "little"), 2, qx, qy)
                        child = block[:4] + color.to_bytes(4, "little")
                    elif fourcc == "DXT3":
                        alpha = expand_block_indices(int.from_bytes(block[:8], "little"), 4, qx, qy)
                        color = expand_block_indices(int.from_bytes(block[12:16], "little"), 2, qx, qy)
                        child = alpha.to_bytes(8, "little") + block[8:12] + color.to_bytes(4, "little")
                    elif fourcc == "DXT5":
                        alpha = expand_block_indices(int.from_bytes(block[2:8], "little"), 3, qx, qy)
                        color = expand_block_indices(int.from_bytes(block[12:16], "little"), 2, qx, qy)
                        child = block[:2] + alpha.to_bytes(6, "little") + block[8:12] + color.to_bytes(4, "little")
                    else:
                        raise ToolError(f"unsupported block format: {fourcc}")
                    obx, oby = bx * 2 + qx, by * 2 + qy
                    pos = (oby * out_bw + obx) * block_size
                    out[pos:pos + block_size] = child
    return bytes(out), width * 2, height * 2


def transform_dds(data: bytes, target: DDSInfo) -> tuple[bytes, str]:
    info = parse_dds(data)
    levels = split_dds_levels(data, info)
    target_w, target_h = max(info.width, target.width), max(info.height, target.height)
    if target_w % info.width or target_h % info.height or target_w // info.width != target_h // info.height:
        raise ToolError(f"non-uniform DDS promotion {info.width}x{info.height} -> {target_w}x{target_h}")
    ratio = target_w // info.width
    if ratio < 1 or ratio & (ratio - 1):
        raise ToolError(f"DDS promotion ratio is not a power of two: {ratio}")
    prepended: list[bytes] = []
    current, width, height = levels[0], info.width, info.height
    while width < target_w:
        if info.fourcc in ("DXT1", "DXT3", "DXT5"):
            current, width, height = upscale_dxt(current, width, height, info.fourcc)
        elif not info.fourcc and info.rgb_bits == 32:
            current, width, height = upscale_rgba32(current, width, height)
        else:
            raise ToolError(f"cannot promote {info.format_name} DDS dimensions")
        prepended.insert(0, current)
    combined = prepended + levels
    width, height = target_w, target_h
    desired_mips = max(target.effective_mips, int(math.floor(math.log2(max(target_w, target_h)))) + 1)
    while len(combined) < desired_mips:
        last_index = len(combined) - 1
        last_w, last_h = max(1, target_w >> last_index), max(1, target_h >> last_index)
        next_w, next_h = max(1, last_w // 2), max(1, last_h // 2)
        if not info.fourcc and info.rgb_bits == 32:
            new, _, _ = downsample_rgba32(combined[-1], last_w, last_h)
        elif info.fourcc in ("DXT1", "DXT3", "DXT5") and next_w <= 4 and next_h <= 4:
            # BC formats always occupy one block below 4x4.  Reusing the
            # smallest available block is structurally valid and affects only
            # the last, sub-pixel mip used for distant filtering.
            new = combined[-1][:8 if info.fourcc == "DXT1" else 16]
        else:
            raise ToolError(f"cannot synthesize missing {info.format_name} mip levels")
        combined.append(new)
    linear = dds_level_size(info, target_w, target_h)
    header = patch_dds_header(data, target_w, target_h, len(combined), linear)
    reason = f"{info.width}x{info.height}/{info.effective_mips} mips -> {target_w}x{target_h}/{len(combined)} mips"
    return header + b"".join(combined), reason


def parse_manifest(raw: bytes) -> list[tuple[str, int]]:
    if b"\r" in raw:
        raise ToolError("manifest has CR line endings")
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    records = []
    for number, line in enumerate(lines, 1):
        name, sep, size = line.rpartition(b"\t")
        if not name or not sep or not size.isdigit():
            raise ToolError(f"malformed manifest record at line {number}")
        records.append((name.decode("utf-8"), int(size)))
    names = [name for name, _ in records]
    if len(names) != len(set(names)):
        raise ToolError("manifest contains duplicate paths")
    return records


def replace_manifest_entries(raw: bytes, remove: set[str], additions: list[tuple[str, int]]) -> bytes:
    records = [(name, size) for name, size in parse_manifest(raw) if name not in remove]
    names = {name for name, _ in records}
    duplicates = [name for name, _ in additions if name in names]
    if duplicates:
        raise ToolError("manifest path collision: " + ", ".join(duplicates[:5]))
    records.extend(additions)
    return b"\n".join(f"{name}\t{size}".encode("utf-8") for name, size in records)


def atomic_write_like(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{path.name}.mk1212-{os.getpid()}")
    try:
        shutil.copy2(path, temp)
        with temp.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def clonefile(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    clone = libc.clonefile
    clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clone.restype = ctypes.c_int
    if clone(os.fsencode(source), os.fsencode(destination), 0) != 0:
        error = ctypes.get_errno()
        if error in (errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS):
            shutil.copy2(source, destination)
            return
        raise OSError(error, os.strerror(error), str(destination))


def clone_tree(source: Path, destination: Path) -> None:
    """Make an APFS clone of an app bundle without ever changing its source."""
    if not source.is_dir():
        raise ToolError(f"native clone source is not an app bundle: {source}")
    if destination.exists():
        raise ToolError(f"native clone destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for current, directories, files in os.walk(source, followlinks=False):
            current_path = Path(current)
            relative = current_path.relative_to(source)
            target_dir = destination / relative
            target_dir.mkdir()
            created.append(target_dir)
            for directory in directories[:]:
                original = current_path / directory
                if original.is_symlink():
                    (target_dir / directory).symlink_to(os.readlink(original))
                    directories.remove(directory)
            for filename in files:
                original = current_path / filename
                target = target_dir / filename
                if original.is_symlink():
                    target.symlink_to(os.readlink(original))
                else:
                    clonefile(original, target)
        for directory in reversed(created):
            shutil.copystat(source / directory.relative_to(destination), directory, follow_symlinks=False)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def native_clone_root(state_dir: Path, state: dict | None = None) -> Path:
    if state is not None and state.get("game_root"):
        return Path(state["game_root"])
    return state_dir / "native-clone"


def native_clone_app_path(state_dir: Path, state: dict | None = None) -> Path:
    return native_clone_root(state_dir, state) / NATIVE_CLONE_DIRNAME


def native_clone_executable_path(state_dir: Path, state: dict | None = None) -> Path:
    return native_clone_app_path(state_dir, state) / "Contents/MacOS/Total War ATTILA"


def native_clone_data_link_path(state_dir: Path, state: dict) -> Path:
    """The Feral executable resolves its data directory beside its app bundle."""
    data_directory = Path(state["data_root"])
    feral_data_root = data_directory.parent
    if data_directory.name != "data" or feral_data_root.name != "TotalWarAttilaData":
        raise ToolError(f"unexpected Feral data-directory layout: {data_directory}")
    return native_clone_root(state_dir, state) / feral_data_root.name


def ensure_native_clone_data_link(state_dir: Path, state: dict) -> Path:
    """Give the independently located clone the original bundle-relative data view.

    This is a directory symlink in shim state, never a change to the Steam game
    directory.  ATTILA's macOS startup code expects TotalWarAttilaData to be a
    sibling of the .app bundle.
    """
    data_directory = Path(state["data_root"]).resolve()
    data_root = data_directory.parent
    if data_directory.name != "data" or data_root.name != "TotalWarAttilaData" or not data_root.is_dir():
        raise ToolError(f"Feral data directory is unavailable: {data_directory}")
    link = native_clone_data_link_path(state_dir, state)
    if os.path.lexists(link):
        if link.resolve() != data_root or (not link.is_symlink() and not link.is_dir()):
            raise ToolError(f"unexpected native clone data-link target: {link}")
    else:
        if not link.parent.is_dir():
            raise ToolError(f"native clone root is unavailable: {link.parent}")
        link.symlink_to(data_root, target_is_directory=True)
    return link


def verify_native_preimage(executable: Path) -> dict:
    """Return supported-build metadata only if every patch guard matches."""
    digest = sha256_path(executable)
    metadata = SUPPORTED_NATIVE_EXECUTABLES.get(digest)
    if metadata is None:
        raise ToolError(
            "unsupported Feral executable hash; native ten-slot patch is refused: " + digest
        )
    with executable.open("rb") as stream:
        for patch in NATIVE_SLOT_PATCHES:
            start = patch["file_offset"] - 4
            stream.seek(start)
            actual = stream.read(len(patch["before_context"]))
            if actual != patch["before_context"]:
                raise ToolError(
                    "unsupported Feral instruction context at "
                    f"0x{patch['virtual_address']:x}; native patch is refused"
                )
    return {"sha256": digest, **metadata}


def patch_native_clone(executable: Path) -> list[dict]:
    """Patch the independently generated clone after exact preimage checks."""
    applied = []
    with executable.open("r+b") as stream:
        for patch in NATIVE_SLOT_PATCHES:
            start = patch["file_offset"] - 4
            stream.seek(start)
            actual = stream.read(len(patch["before_context"]))
            if actual != patch["before_context"]:
                raise ToolError(
                    "native clone preimage mismatch at "
                    f"0x{patch['virtual_address']:x}; clone is left unmodified"
                )
        for patch in NATIVE_SLOT_PATCHES:
            stream.seek(patch["file_offset"])
            stream.write(patch["after_context"][4:8])
            applied.append({
                "virtual_address": f"0x{patch['virtual_address']:x}",
                "file_offset": f"0x{patch['file_offset']:x}",
                "before": patch["before_context"][4:8].hex(),
                "after": patch["after_context"][4:8].hex(),
            })
        stream.flush()
        os.fsync(stream.fileno())
    with executable.open("rb") as stream:
        for patch in NATIVE_SLOT_PATCHES:
            stream.seek(patch["file_offset"] - 4)
            if stream.read(len(patch["after_context"])) != patch["after_context"]:
                raise ToolError("native clone post-write verification failed")
    return applied


def codesign_local_clone(app: Path) -> None:
    result = subprocess.run(
        ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(app)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ToolError("local clone signing failed: " + result.stderr.strip())
    verify = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
        capture_output=True, text=True,
    )
    if verify.returncode != 0:
        raise ToolError("local clone signature verification failed: " + verify.stderr.strip())


def build_native_clone(state_dir: Path, state: dict) -> dict:
    if game_running():
        raise ToolError("ATTILA is running; native clone creation is refused")
    source = Path(state["game_root"]) / EXECUTABLE_RELATIVE
    source_metadata = verify_native_preimage(source)
    app_source = source.parents[2]
    clone = native_clone_app_path(state_dir, state)
    if clone.exists():
        raise ToolError(f"native clone already exists: {clone}")
    try:
        clone_tree(app_source, clone)
        data_link = ensure_native_clone_data_link(state_dir, state)
        cloned_executable = native_clone_executable_path(state_dir, state)
        applied = patch_native_clone(cloned_executable)
        codesign_local_clone(clone)
        result = {
            "status": "ready", "created_at": utc_now(),
            "source_app": str(app_source), "source_executable": str(source),
            "source": source_metadata, "clone_app": str(clone),
            "clone_executable": str(cloned_executable),
            "data_root_link": str(data_link),
            "clone_executable_sha256": sha256_path(cloned_executable),
            "patches": applied, "locally_signed": True,
        }
        state["native_slot_clone"] = result
        save_json(state_dir / "state.json", state)
        return result
    except BaseException:
        shutil.rmtree(clone, ignore_errors=True)
        raise


def safe_destination(root: Path, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if (normalized.is_absolute() or not normalized.parts or ".." in normalized.parts
            or re.match(r"^[A-Za-z]:", normalized.as_posix())):
        raise ToolError(f"unsafe generated relative path: {relative_path!r}")
    destination = root.joinpath(*normalized.parts)
    resolved_root = root.resolve()
    resolved_parent = destination.parent.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise ToolError(f"generated path escapes data root: {relative_path!r}")
    return destination


def steam_libraries() -> list[Path]:
    root = Path.home() / "Library/Application Support/Steam"
    result = [root]
    config = root / "steamapps/libraryfolders.vdf"
    if config.is_file():
        for raw in re.findall(r'"path"\s+"([^"]+)"', config.read_text(errors="replace")):
            candidate = Path(raw.replace(r"\\", "\\"))
            if candidate not in result:
                result.append(candidate)
    return result


def discover_game_root(explicit=None) -> Path:
    if explicit:
        candidates = [Path(explicit).expanduser().resolve()]
    else:
        candidates = []
        for library in steam_libraries():
            acf = library / f"steamapps/appmanifest_{APP_ID}.acf"
            if not acf.is_file():
                continue
            match = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text(errors="replace"))
            if match:
                candidates.append(library / "steamapps/common" / match.group(1))
    valid = [p for p in candidates if (p / "Total War ATTILA.app/Contents/MacOS/Total War ATTILA").is_file()]
    if len(valid) != 1:
        raise ToolError(f"expected one ATTILA installation, found {len(valid)}")
    return valid[0]


def inventory_packs(game_root: Path) -> dict[str, list[Path]]:
    roots: list[Path] = []
    for library in steam_libraries():
        root = library / f"steamapps/workshop/content/{APP_ID}"
        if root.is_dir():
            roots.append(root)
    roots.append(game_root / "TotalWarAttilaData/data")
    found: dict[str, list[Path]] = {}
    for root in roots:
        depth = 2 if "workshop/content" in str(root) else 1
        pattern = "*/*.pack" if depth == 2 else "*.pack"
        for path in root.glob(pattern):
            if path.name.startswith(GENERATED_PREFIX) or path.name in STOCK_PACK_NAMES:
                continue
            found.setdefault(path.name.casefold(), []).append(path)
    return found


def feral_mod_records(preferences: Path = FERAL_STATE / "Preferences Data") -> list[dict]:
    if not preferences.is_file():
        return []
    root = ET.parse(preferences).getroot()
    records = []
    for launcher in root.iter("key"):
        if launcher.get("name") != "Launcher":
            continue
        mods = next((child for child in launcher.findall("key") if child.get("name") == "mods"), None)
        if mods is None:
            continue
        for value in mods.findall("value"):
            raw = (value.text or "").split("|")
            if len(raw) != 3:
                continue
            records.append({
                "name": value.get("name", ""), "timestamp": int(raw[0]),
                "enabled": raw[1] == "1", "order": int(raw[2]),
            })
    return records


def load_order_names(path: Path) -> list[str]:
    if not path.is_file():
        raise ToolError(f"load-order file does not exist: {path}")
    names = []
    seen = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        if "/" in name or "\\" in name:
            raise ToolError(f"load-order line {number} must be a bare pack filename: {name!r}")
        key = name.casefold()
        if key in seen:
            raise ToolError(f"duplicate pack on load-order line {number}: {name!r}")
        seen.add(key)
        names.append(name)
    if not names:
        raise ToolError(f"load-order file is empty: {path}")
    return names


def selected_packs(game_root: Path, profile: str, load_order_file: str | None = None) -> list[Path]:
    inventory = inventory_packs(game_root)
    records = feral_mod_records()
    selected_names: list[str]
    if load_order_file:
        selected_names = load_order_names(Path(load_order_file).expanduser().resolve())
    elif profile == "feral":
        selected_names = [r["name"] for r in sorted(records, key=lambda x: (x["order"], x["name"].casefold())) if r["enabled"]]
    else:
        selected_names = [name for _, name in CANONICAL_PACKS]
        canonical = {name.casefold() for name in selected_names}
        # Feral retains stale records for unsubscribed packs.  Only import an
        # enabled submod when its source still exists; canonical MK1212 packs
        # remain mandatory and are diagnosed below if absent.
        extras = [r for r in records if r["enabled"] and r["name"].casefold() not in canonical
                  and r["name"].casefold() in inventory]
        selected_names.extend(r["name"] for r in sorted(extras, key=lambda x: (x["order"], x["name"].casefold())))
    result = []
    for name in selected_names:
        matches = inventory.get(name.casefold(), [])
        if len(matches) != 1:
            if profile == "feral" and not matches:
                continue
            raise ToolError(f"expected one installed source for {name!r}, found {len(matches)}")
        result.append(matches[0])
    if not result:
        raise ToolError("selected mod set is empty")
    return result


def disabled_internal_name(path: str, occupied: set[str]) -> str:
    slash = max(path.rfind("/"), path.rfind("\\"))
    if slash < 0 or slash + 1 >= len(path):
        raise ToolError(f"cannot rename unsafe member: {path}")
    for char in ("~", "!", "#", "$", "%"):
        candidate = path[:slash + 1] + char + path[slash + 2:]
        if candidate.casefold().replace("\\", "/") not in occupied:
            return candidate
    raise ToolError(f"cannot find unused disabled name for {path}")


def stock_dds_contracts(data_root: Path, wanted: set[str]) -> dict[str, DDSInfo]:
    result: dict[str, DDSInfo] = {}
    for pack in sorted(data_root.glob("*.pack"), key=lambda p: p.name.casefold()):
        if pack.name not in STOCK_PACK_NAMES:
            continue
        try:
            _, entries = read_pack(pack)
        except ToolError:
            continue
        matches = [e for e in entries if e.relative_path.casefold() in wanted]
        if not matches:
            continue
        with pack.open("rb") as stream:
            for entry in matches:
                try:
                    info = parse_dds(read_entry(stream, entry))
                except ToolError:
                    continue
                key = entry.relative_path.casefold()
                old = result.get(key)
                if old is None or (info.width * info.height, info.effective_mips) > (old.width * old.height, old.effective_mips):
                    result[key] = info
    return result


def plan_compatibility(game_root: Path, packs: list[Path]) -> tuple[list[dict], dict[str, tuple[Path, PackEntry]]]:
    parsed = []
    wanted: set[str] = set()
    for pack in packs:
        metadata, entries = read_pack(pack)
        if metadata["pack_type"] not in (3, 4):
            raise ToolError(f"selected pack has unsupported type {metadata['pack_type']}: {pack}")
        dds_entries = [e for e in entries if e.relative_path.casefold().endswith(".dds")]
        wanted.update(e.relative_path.casefold() for e in dds_entries)
        parsed.append((pack, metadata, entries, dds_entries))
    stock_contracts = stock_dds_contracts(game_root / "TotalWarAttilaData/data", wanted)
    # The confirmed ARM64 failures violate same-path stock asset contracts.
    # Check each override independently against that immutable contract.  Do
    # not coerce intentional mod-to-mod replacements: those may differ in DDS
    # format and dimensions, and rewriting them would alter mod semantics.
    plan: list[dict] = []
    for order, (pack, metadata, entries, dds_entries) in enumerate(parsed, 1):
        repairs = []
        with pack.open("rb") as stream:
            for entry in dds_entries:
                key = entry.relative_path.casefold()
                stock = stock_contracts.get(key)
                try:
                    source_data = read_entry(stream, entry)
                    source_info = parse_dds(source_data)
                except ToolError as exc:
                    if stock is not None:
                        raise ToolError(f"unsafe DDS override cannot be validated: {entry.relative_path} in {pack.name}: {exc}")
                    continue
                if stock is not None and (source_info.width < stock.width or source_info.height < stock.height or source_info.effective_mips < stock.effective_mips):
                    try:
                        transformed, reason = transform_dds(source_data, stock)
                    except ToolError as exc:
                        raise ToolError(f"unsafe DDS override needs unsupported transformation: {entry.relative_path} in {pack.name}: {exc}") from exc
                    repaired_info = parse_dds(transformed)
                    repairs.append({"entry": entry, "data": transformed, "reason": reason,
                                    "source": vars(source_info), "target": vars(repaired_info)})
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", pack.stem)[:64]
        content_name = f"{GENERATED_PREFIX}{order:03d}_content_{safe}_movie.pack"
        overlay_name = f"{GENERATED_PREFIX}{order:03d}_repair_{safe}_movie.pack" if repairs else None
        plan.append({"order": order, "source": pack, "metadata": metadata, "entries": entries,
                     "repairs": repairs, "content_name": content_name, "overlay_name": overlay_name})
    lua_winners: dict[str, tuple[Path, PackEntry]] = {}
    for pack, _, entries, _ in parsed:
        for entry in entries:
            if entry.relative_path.casefold().endswith(".lua"):
                lua_winners.setdefault(entry.relative_path.casefold(), (pack, entry))
    return plan, lua_winners


def write_overlay(path: Path, repairs: list[dict], timestamp: int) -> None:
    index_bytes = sum(4 + len(item["entry"].internal_path.encode()) + 1 for item in repairs)
    with path.open("xb") as stream:
        stream.write(struct.pack("<4s5I", b"PFH4", 4, 0, 0, len(repairs), index_bytes))
        stream.write(struct.pack("<I", timestamp))
        for item in repairs:
            entry, data = item["entry"], item["data"]
            stream.write(struct.pack("<I", len(data)))
            stream.write(entry.internal_path.encode() + b"\0")
        for item in repairs:
            stream.write(item["data"])
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o644)


def write_content_clone(source: Path, destination: Path, metadata: dict, entries: list[PackEntry], repairs: list[dict]) -> None:
    clonefile(source, destination)
    occupied = {e.relative_path.casefold() for e in entries}
    with destination.open("r+b") as stream:
        stream.seek(4)
        stream.write(struct.pack("<I", 4))
        for item in repairs:
            entry = item["entry"]
            replacement = disabled_internal_name(entry.internal_path, occupied)
            old, new = entry.internal_path.encode(), replacement.encode()
            if len(old) != len(new):
                raise ToolError("disabled pack path changed byte length")
            stream.seek(entry.path_offset)
            if stream.read(len(old)) != old:
                raise ToolError(f"pack index changed while patching {entry.internal_path}")
            stream.seek(entry.path_offset)
            stream.write(new)
            item["disabled_path"] = replacement
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(destination, 0o644)


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temp, path)


def load_state(state_dir: Path) -> dict:
    path = state_dir / "state.json"
    if not path.is_file():
        raise ToolError(f"no installed launcher state at {path}")
    return json.loads(path.read_text())


def game_running() -> bool:
    result = subprocess.run(["/usr/bin/pgrep", "-f", "Total War ATTILA.app/Contents/MacOS/Total War ATTILA"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def manifest_backup(manifest: Path, state_dir: Path, operation: str) -> dict:
    raw = manifest.read_bytes()
    digest = sha256_bytes(raw)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S.%f")
    path = state_dir / "backups" / f"manifest.{stamp}.{operation}.{digest}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ToolError(f"refusing to overwrite manifest backup: {path}")
    shutil.copy2(manifest, path)
    if path.read_bytes() != raw:
        raise ToolError("manifest backup verification failed")
    return {"path": str(path), "sha256": digest, "bytes": len(raw), "created_at": utc_now(), "operation": operation}


def prepare_isolated_home(state_dir: Path) -> Path:
    home = state_dir / "runtime-home"
    isolated = home / "Library/Application Support/Feral Interactive/Total War ATTILA"
    isolated.mkdir(parents=True, exist_ok=True)
    source_prefs = FERAL_STATE / "Preferences Data"
    target_prefs = isolated / "Preferences Data"
    tree = ET.parse(source_prefs)
    for launcher in tree.getroot().iter("key"):
        if launcher.get("name") != "Launcher":
            continue
        for mods in launcher.findall("key"):
            if mods.get("name") == "mods":
                for value in mods.findall("value"):
                    parts = (value.text or "").split("|")
                    if len(parts) == 3:
                        value.text = f"{parts[0]}|0|-1"
    tree.write(target_prefs, encoding="UTF-8", xml_declaration=True)
    real_vfs = FERAL_STATE / "VFS"
    isolated_vfs = isolated / "VFS"
    isolated_vfs.mkdir(exist_ok=True)
    for name in ("User", "Local"):
        link, target = isolated_vfs / name, real_vfs / name
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.exists() or link.is_symlink():
            raise ToolError(f"unexpected isolated VFS path: {link}")
        link.symlink_to(target, target_is_directory=True)
    return home


def used_mods_text(packs: list[Path]) -> bytes:
    dirs = []
    seen = set()
    for pack in packs:
        if pack.parent not in seen:
            seen.add(pack.parent)
            dirs.append(pack.parent)
    lines = [f'add_working_directory "{path}";' for path in dirs]
    lines.extend(f'mod "{pack.name}";' for pack in packs)
    return ("\n".join(lines) + "\n").encode()


def inspect_command(args: argparse.Namespace) -> None:
    game_root = discover_game_root(args.game_root)
    packs = selected_packs(game_root, args.profile, args.load_order_file)
    plan, lua = plan_compatibility(game_root, packs)
    report = {
        "tool_version": TOOL_VERSION, "game_root": str(game_root), "profile": args.profile,
        "load_order_file": str(Path(args.load_order_file).expanduser().resolve()) if args.load_order_file else None,
        "working_directory": str(game_root / "TotalWarAttilaData"),
        "executable": str(game_root / "Total War ATTILA.app/Contents/MacOS/Total War ATTILA"),
        "selected_packs": [str(p) for p in packs], "lua_winner_count": len(lua),
        "packs": [{"order": p["order"], "source": str(p["source"]), "content_name": p["content_name"],
                   "overlay_name": p["overlay_name"], "repair_count": len(p["repairs"]),
                   "repairs": [{"path": r["entry"].relative_path, "reason": r["reason"]} for r in p["repairs"]]}
                  for p in plan],
    }
    print(json.dumps(report, indent=2))


def source_record(pack: Path, pack_type: int,
                  progress: Callable[[str], None] | None = None) -> dict:
    stat = pack.stat()
    digest = sha256_path_with_progress(pack, progress) if progress else sha256_path(pack)
    after = pack.stat()
    if (after.st_size != stat.st_size or after.st_mtime_ns != stat.st_mtime_ns or
            after.st_dev != stat.st_dev or after.st_ino != stat.st_ino):
        raise ToolError(f"Workshop source changed while it was being hashed: {pack}")
    return {"name": pack.name, "path": str(pack), "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "device": stat.st_dev, "inode": stat.st_ino,
            "sha256": digest, "pack_type": pack_type,
            "optional": pack.name.casefold() not in {name.casefold() for _, name in CANONICAL_PACKS}}


def refresh_optional_sources(state: dict) -> list[str]:
    """Add installed Workshop submods to the launcher's selectable set.

    Feral keeps disabled Workshop entries in its preferences, but a newly
    subscribed pack may not appear there until Feral's own launcher has seen
    it.  Use the immutable Workshop inventory as the discovery source and use
    Feral's records only for deterministic preference order where available.
    This makes newly downloaded packs selectable without enabling them in
    Feral or modifying the Workshop file.
    """
    game_root = Path(state["game_root"])
    inventory = inventory_packs(game_root)
    existing = {record["name"].casefold() for record in state.get("source_packs", [])}
    canonical = {name.casefold() for _, name in CANONICAL_PACKS}
    added: list[str] = []
    feral_records = feral_mod_records()
    preference_order = {record["name"].casefold(): record["order"] for record in feral_records}
    candidates: list[tuple[int, str, Path]] = []
    for key, matches in inventory.items():
        if key in existing or key in canonical or len(matches) != 1:
            continue
        candidates.append((preference_order.get(key, 1_000_000), key, matches[0]))
    for _, key, pack in sorted(candidates, key=lambda item: (item[0], item[1])):
        name = pack.name
        key = name.casefold()
        metadata, _ = read_pack(pack)
        if metadata["pack_type"] not in (3, 4):
            continue
        state.setdefault("source_packs", []).append(source_record(pack, metadata["pack_type"]))
        existing.add(key)
        added.append(name)
    # Keep a separate, user-controlled order for optional packs.  Newly
    # discovered Workshop content is appended instead of silently changing
    # the priority of packs the user has already arranged.
    if added:
        if "optional_load_order" in state:
            current = list(state.get("optional_load_order") or [])
        else:
            added_keys = {name.casefold() for name in added}
            current = [record["name"] for record in state["source_packs"]
                       if record.get("optional") and record["name"].casefold() not in added_keys]
        known = {name.casefold() for name in current}
        for name in added:
            if name.casefold() not in known:
                current.append(name)
                known.add(name.casefold())
        state["optional_load_order"] = current
    return added


def profile_key(records: list[dict], compatibility_revision: str = PROFILE_COMPATIBILITY_REVISION) -> str:
    value = {
        "compatibility_revision": compatibility_revision,
        "sources": [{"name": item["name"], "sha256": item["sha256"]} for item in records],
    }
    return sha256_bytes(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())[:20]


def apply_lua_compatibility(relative_path: str, data: bytes) -> tuple[bytes, list[str]]:
    """Apply narrowly-scoped, reversible Feral UI compatibility edits.

    Feral's scaled frontend turns the implicit ``resize children=true`` on the
    MK1212 faction-details parent into a severe horizontal compression.  Keep
    the requested parent bounds while preserving the authored child bounds.
    """
    relative_folded = relative_path.casefold()
    if relative_folded == "campaigns/main_attila/mk1212_slots.lua":
        function_old = b'''function ModifyHardcodedLimits()
\tDISCLAIMER_ACCEPTED = true;

\t--if not util.fileExists("MK1212_10slots.exe") then
\t\trequire("lua_scripts/slots_binaries");

\t\tlocal slotsFile = io.open("MK1212_10slots.exe", "wb");
\t\tlocal binary = "";
\t\t\t
\t\tfor i = 1, #slots_binaries do
\t\t\tlocal number = tonumber("0x"..slots_binaries[i]);
\t\t\tlocal char = string.char(number);

\t\t\tbinary = binary..char;
\t\tend

\t\tslotsFile:write(binary);
\t\tslotsFile:close();
\t--end

\tlocal command = "MK1212_10slots.exe";

\tos.execute(command);

\tsvr:SaveBool("SBOOL_Prompt_Already_Shown", true);
\tsvr:SaveBool("SBOOL_Hardcoded_Limits_Modified", true);
end
'''
        function_new = b'''function ModifyHardcodedLimits()
\t-- The bundled helper is Windows-only. Never extract or execute it on macOS.
\tDISCLAIMER_ACCEPTED = true;
\tsvr:SaveBool("SBOOL_Prompt_Already_Shown", true);
\tsvr:SaveBool("SBOOL_Hardcoded_Limits_Modified", true);
end
'''
        accepted_old = b'DISCLAIMER_ACCEPTED = svr:LoadBool("SBOOL_Hardcoded_Limits_Modified") or false;'
        accepted_new = b'DISCLAIMER_ACCEPTED = true; -- macOS runtime patch supplies ten slots automatically.'
        show_guard_old = b'\t\tif not DISCLAIMER_ACCEPTED then'
        show_guard_new = b'\t\tif true then -- macOS: always suppress the obsolete Windows helper UI.'
        button_declaration = (
            b'\t\t\t\tlocal button_disclaimer_uic = '
            b'UIComponent(main_settlement_panel_uic:Find("button_disclaimer"));'
        )
        button_declaration_hidden = button_declaration + b'\n\t\t\t\tbutton_disclaimer_uic:SetVisible(false);'
        show_button_old = b'button_disclaimer_uic:SetVisible(true);'
        show_button_new = b'button_disclaimer_uic:SetVisible(false);'
        shape = (
            data.count(function_old), data.count(accepted_old), data.count(show_guard_old),
            data.count(button_declaration), data.count(show_button_old),
        )
        if shape != (1, 1, 1, 1, 4):
            raise ToolError(
                "unexpected MK1212 slot script shape; refusing a partial Lua compatibility edit"
            )
        data = data.replace(function_old, function_new)
        data = data.replace(accepted_old, accepted_new)
        data = data.replace(show_guard_old, show_guard_new)
        data = data.replace(button_declaration, button_declaration_hidden)
        data = data.replace(show_button_old, show_button_new)
        return data, [
            "replaced the Windows-only ten-slot executable call with a safe macOS no-op",
            "kept the obsolete Windows ten-slot button and popup hidden",
        ]

    if relative_folded != "lua_scripts/frontend_scripted.lua":
        return data, []

    faction_old = b"faction_details_parent_uic:Resize(436, 616);"
    faction_new = b"faction_details_parent_uic:Resize(436, 616, false);"
    faction_occurrences = data.count(faction_old)
    if faction_occurrences not in (0, 2):
        raise ToolError(
            "unexpected MK1212 faction layout script shape; refusing a partial Lua compatibility edit"
        )

    popup_old = (
        b"popup_menu_uic:Resize((225 * num_columns), (30 * max_rows) + 12);\n"
        b"\t\t\t\t\t\t\t\t\t\t\t--popup_menu_uic:SetMoveable(true);\n"
        b"\t\t\t\t\t\t\t\t\t\t\t--popup_menu_uic:MoveTo(popup_menuX - ((boundsX * num_columns) / 2), popup_menuY);\n"
        b"\t\t\t\t\t\t\t\t\t\t\t--popup_menu_uic:SetMoveable(false);\n"
        b"\n"
        b"\t\t\t\t\t\t\t\t\t\t\tpopup_listX, popup_listY = popup_list_uic:Position(); -- Reset pos."
    )
    popup_new = (
        b"popup_menu_uic:Resize((225 * num_columns), (30 * max_rows) + 12, false);\n"
        b"\t\t\t\t\t\t\t\t\t\t\t-- Keep the pre-resize popup-list origin on Feral."
    )
    popup_occurrences = data.count(popup_old)
    if popup_occurrences not in (0, 1):
        raise ToolError(
            "unexpected MK1212 custom-battle popup script shape; refusing a partial Lua compatibility edit"
        )

    hide_start_old = (
        b"if popup_menu_uic and popup_menu_uic:Visible() then\n"
        b"\t\t\t\t\t\t\ttm:callback("
    )
    hide_start_new = (
        b"if popup_menu_uic and popup_menu_uic:Visible() then\n"
        b"\t\t\t\t\t\t\tpopup_list_uic:SetVisible(false);\n"
        b"\t\t\t\t\t\t\ttm:callback("
    )
    hide_end_old = (
        b"uic:SetMoveable(false);\n"
        b"\t\t\t\t\t\t\t\t\t\t\t\tuic:SetVisible(true);\n"
        b"\t\t\t\t\t\t\t\t\t\t\tend"
    )
    hide_end_new = (
        b"uic:SetMoveable(false);\n"
        b"\t\t\t\t\t\t\t\t\t\t\t\tuic:SetVisible(true);\n"
        b"\t\t\t\t\t\t\t\t\t\t\tend\n"
        b"\t\t\t\t\t\t\t\t\t\t\tpopup_list_uic:SetVisible(true);"
    )
    hide_counts = (data.count(hide_start_old), data.count(hide_end_old))
    if (popup_occurrences, *hide_counts) not in ((0, 0, 0), (1, 1, 1)):
        raise ToolError(
            "unexpected MK1212 custom-battle visibility script shape; refusing a partial Lua compatibility edit"
        )

    repairs = []
    if faction_occurrences:
        data = data.replace(faction_old, faction_new)
        repairs.append("preserved faction-details child bounds during two parent resizes")
    if popup_occurrences:
        data = data.replace(popup_old, popup_new)
        data = data.replace(hide_start_old, hide_start_new)
        data = data.replace(hide_end_old, hide_end_new)
        repairs.append(
            "preserved custom-battle faction-popup geometry and hid its entries during delayed arrangement"
        )
    return data, repairs


def profile_cache_path(profile: dict, record: dict) -> Path:
    return safe_destination(Path(profile["cache_dir"]), record["cache_relative_path"])


def verify_profile(profile: dict) -> list[str]:
    failures = []
    for record in profile["files"]:
        path = profile_cache_path(profile, record)
        if not path.is_file() or path.stat().st_size != record["size"]:
            failures.append(f"missing or wrong cache size: {path}")
            continue
        if record["kind"] == "content_pack":
            if quick_fingerprint(path) != record["quick_fingerprint"]:
                failures.append(f"cache fingerprint mismatch: {path}")
            elif read_pack(path)[0]["pack_type"] != 4:
                failures.append(f"cached content pack is not type 4: {path}")
        elif sha256_path(path) != record["sha256"]:
            failures.append(f"cache hash mismatch: {path}")
    used = profile["used_mods"]
    used_path = safe_destination(Path(profile["cache_dir"]), used["cache_relative_path"])
    if not used_path.is_file() or sha256_path(used_path) != used["sha256"]:
        failures.append(f"cached used_mods.txt mismatch: {used_path}")
    return failures


def build_profile_cache(state_dir: Path, game_root: Path, records: list[dict],
                        prepared: tuple[list[dict], dict[str, tuple[Path, PackEntry]]] | None = None,
                        progress: Callable[[str], None] | None = None) -> dict:
    key = profile_key(records)
    cache_root = game_root / "TotalWarAttilaData/.mk1212-cache/profiles"
    profile_dir = cache_root / key
    if profile_dir.exists():
        raise ToolError(f"unledgered profile cache already exists: {profile_dir}")
    cache_root.mkdir(parents=True, exist_ok=True)
    staging = cache_root / f".{key}.building-{os.getpid()}"
    if staging.exists():
        raise ToolError(f"stale profile staging directory exists: {staging}")
    staging.mkdir()
    packs = [Path(record["path"]) for record in records]
    if progress:
        progress(f"Inspecting {len(packs)} packs for the {key} cache profile")
    plan, lua_winners = prepared if prepared is not None else plan_compatibility(game_root, packs)
    profile = {"key": key, "created_at": utc_now(), "cache_dir": str(profile_dir),
               "pack_names": [record["name"] for record in records], "source_packs": records,
               "compatibility_revision": PROFILE_COMPATIBILITY_REVISION,
               "files": [], "dds_repairs": [], "lua_repairs": [],
               "lua_count": len(lua_winners), "used_mods": None}
    try:
        pack_dir = staging / "packs"
        pack_dir.mkdir()
        for index, item in enumerate(plan, start=1):
            source = item["source"]
            if progress:
                progress(f"Cloning pack {index}/{len(plan)}: {source.name}")
            content = pack_dir / item["content_name"]
            write_content_clone(source, content, item["metadata"], item["entries"], item["repairs"])
            os.chmod(content, 0o444)
            profile["files"].append({"kind": "content_pack", "cache_relative_path": f"packs/{content.name}",
                                     "relative_path": content.name, "size": content.stat().st_size,
                                     "quick_fingerprint": quick_fingerprint(content), "source": str(source),
                                     "pack_order": item["order"]})
            if item["repairs"]:
                overlay = pack_dir / item["overlay_name"]
                write_overlay(overlay, item["repairs"], item["metadata"]["index_timestamp"])
                os.chmod(overlay, 0o444)
                profile["files"].append({"kind": "repair_pack", "cache_relative_path": f"packs/{overlay.name}",
                                         "relative_path": overlay.name, "size": overlay.stat().st_size,
                                         "sha256": sha256_path(overlay), "pack_order": item["order"]})
                for repair in item["repairs"]:
                    profile["dds_repairs"].append({"source_pack": str(source),
                                                   "path": repair["entry"].relative_path,
                                                   "reason": repair["reason"],
                                                   "disabled_path": repair["disabled_path"]})
        for index, (_, (source, entry)) in enumerate(sorted(lua_winners.items()), start=1):
            if progress and (index == 1 or index % 25 == 0 or index == len(lua_winners)):
                progress(f"Extracting winning Lua files: {index}/{len(lua_winners)}")
            destination = safe_destination(staging / "lua", entry.relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as stream:
                data = read_entry(stream, entry)
            data, lua_repairs = apply_lua_compatibility(entry.relative_path, data)
            for reason in lua_repairs:
                profile["lua_repairs"].append({"source_pack": str(source),
                                               "path": entry.relative_path,
                                               "reason": reason})
            destination.write_bytes(data)
            os.chmod(destination, 0o444)
            profile["files"].append({"kind": "lua", "cache_relative_path": f"lua/{entry.relative_path}",
                                     "relative_path": entry.relative_path, "size": len(data),
                                     "sha256": sha256_bytes(data), "source": str(source)})
        used_data = used_mods_text(packs)
        used_path = staging / "used_mods.txt"
        used_path.write_bytes(used_data)
        os.chmod(used_path, 0o444)
        profile["used_mods"] = {"cache_relative_path": "used_mods.txt", "size": len(used_data),
                                "sha256": sha256_bytes(used_data)}
        save_json(staging / "profile.json", profile)
        os.replace(staging, profile_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    failures = verify_profile(profile)
    if failures:
        raise ToolError("new profile cache verification failed:\n  " + "\n  ".join(failures))
    if progress:
        progress(f"Cache profile {key} is complete and verified")
    return profile


def records_for_names(state: dict, names: list[str]) -> list[dict]:
    by_name = {record["name"].casefold(): record for record in state["source_packs"]}
    missing = [name for name in names if name.casefold() not in by_name]
    if missing:
        raise ToolError("profile sources are missing: " + ", ".join(missing))
    return [by_name[name.casefold()] for name in names]


def ensure_profile(state_dir: Path, state: dict, names: list[str]) -> dict:
    records = records_for_names(state, names)
    key = profile_key(records)
    cached = state.get("profiles", {}).get(key)
    if cached is not None:
        failures = verify_profile(cached)
        if failures:
            raise ToolError("profile cache verification failed:\n  " + "\n  ".join(failures))
        return cached
    profile = build_profile_cache(state_dir, Path(state["game_root"]), records)
    state.setdefault("profiles", {})[key] = profile
    save_json(state_dir / "state.json", state)
    return profile


def active_file_matches(path: Path, record: dict) -> bool:
    if not path.is_file() or path.stat().st_size != record["size"]:
        return False
    if record["kind"] == "content_pack":
        return quick_fingerprint(path) == record["quick_fingerprint"]
    return sha256_path(path) == record["sha256"]


def remove_empty_parents(path: Path, stop: Path) -> None:
    parent = path.parent
    while parent != stop and stop in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def deactivate_profile(state_dir: Path, state: dict, activation: dict) -> None:
    if game_running():
        raise ToolError("ATTILA is still running; transient compatibility cleanup is refused")
    data_root = Path(state["data_root"])
    manifest = Path(state["manifest"])
    backup = manifest_backup(manifest, state_dir, "deactivate")
    names = {record["relative_path"] for record in activation["files"]}
    current = manifest.read_bytes()
    updated = replace_manifest_entries(current, names, [])
    atomic_write_like(manifest, updated)
    recovery_root = Path(state["cache_root"]) / "recovery" / activation["id"]
    recovered = []
    for record in reversed(activation["files"]):
        path = safe_destination(data_root, record["relative_path"])
        if not path.exists():
            continue
        if active_file_matches(path, record):
            path.unlink()
        else:
            recovery = safe_destination(recovery_root, record["relative_path"])
            recovery.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, recovery)
            recovered.append(str(recovery))
        remove_empty_parents(path, data_root)
    used = Path(activation["used_mods_path"])
    if used.exists():
        if used.is_file() and sha256_path(used) == activation["used_mods_sha256"]:
            used.unlink()
        else:
            recovery = recovery_root / "used_mods.txt"
            recovery.parent.mkdir(parents=True, exist_ok=True)
            os.replace(used, recovery)
            recovered.append(str(recovery))
    activation["status"] = "deactivated"
    activation["deactivated_at"] = utc_now()
    activation["deactivate_manifest_backup"] = backup
    activation["manifest_after_deactivate_sha256"] = sha256_bytes(updated)
    activation["recovered_changed_files"] = recovered
    history = state_dir / "activation-history" / f"{activation['id']}.json"
    save_json(history, activation)
    (state_dir / "activation.json").unlink(missing_ok=True)


def recover_stale_activation(state_dir: Path, state: dict) -> None:
    path = state_dir / "activation.json"
    if not path.is_file():
        return
    activation = json.loads(path.read_text())
    if game_running():
        raise ToolError("an active transient profile already owns the running ATTILA process")
    deactivate_profile(state_dir, state, activation)
    print("Recovered and removed a stale transient compatibility activation.")


def activate_profile(state_dir: Path, state: dict, profile: dict) -> dict:
    if game_running():
        raise ToolError("ATTILA is already running; transient activation is refused")
    data_root = Path(state["data_root"])
    manifest = Path(state["manifest"])
    used_path = Path(state["game_root"]) / "TotalWarAttilaData/used_mods.txt"
    destinations = [(record, safe_destination(data_root, record["relative_path"]))
                    for record in profile["files"]]
    collisions = [str(path) for _, path in destinations if path.exists()]
    if used_path.exists():
        collisions.append(str(used_path))
    if collisions:
        raise ToolError("transient activation would overwrite existing files: " + ", ".join(collisions[:8]))
    backup = manifest_backup(manifest, state_dir, "activate")
    activation_id = datetime.now().strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    activation = {"schema": 1, "id": activation_id, "status": "activating", "created_at": utc_now(),
                  "profile_key": profile["key"], "pack_names": profile["pack_names"],
                  "manifest_backup": backup, "files": profile["files"],
                  "used_mods_path": str(used_path),
                  "used_mods_sha256": profile["used_mods"]["sha256"]}
    save_json(state_dir / "activation.json", activation)
    try:
        for record, destination in destinations:
            cache = profile_cache_path(profile, record)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(cache, destination)
        cached_used = safe_destination(Path(profile["cache_dir"]), profile["used_mods"]["cache_relative_path"])
        os.link(cached_used, used_path)
        additions = [(record["relative_path"], record["size"]) for record in profile["files"]]
        updated = replace_manifest_entries(manifest.read_bytes(), set(), additions)
        atomic_write_like(manifest, updated)
        activation["status"] = "active"
        activation["activated_at"] = utc_now()
        activation["manifest_active_sha256"] = sha256_bytes(updated)
        save_json(state_dir / "activation.json", activation)
        return activation
    except BaseException:
        if not game_running():
            deactivate_profile(state_dir, state, activation)
        raise


def optional_pack_names(state: dict) -> list[str]:
    return [record["name"] for record in state["source_packs"] if record.get("optional")]


def optional_load_order(state: dict) -> list[str]:
    """Return all installed optional packs in the user's persisted order.

    Older state files have no explicit order.  In that case the source-pack
    order is the compatibility-preserving fallback, and missing/new packs are
    appended deterministically.
    """
    available = optional_pack_names(state)
    by_key = {name.casefold(): name for name in available}
    result: list[str] = []
    seen: set[str] = set()
    for name in state.get("optional_load_order", []):
        key = str(name).casefold()
        if key in by_key and key not in seen:
            result.append(by_key[key])
            seen.add(key)
    for name in available:
        key = name.casefold()
        if key not in seen:
            result.append(name)
            seen.add(key)
    return result


def selected_names(state: dict, optionals: list[str]) -> list[str]:
    enabled = {name.casefold() for name in optionals}
    # MK1212's own pack-checker expects optional utilities above the required
    # core packs.  Preserve the user's explicit optional priority while
    # keeping the source-order fallback for older state files.
    optional = [name for name in optional_load_order(state) if name.casefold() in enabled]
    core = [record["name"] for record in state["source_packs"] if not record.get("optional")]
    return optional + core


CHECKBOX_PICKER_JXA = r'''
ObjC.import("AppKit");

function run(argv) {
    const config = JSON.parse(argv[0]);
    const alert = $.NSAlert.alloc.init;
    alert.messageText = "MK1212 Mac Launcher";
    alert.informativeText = "Check the submods to use. Set a priority number to reorder them (1 loads first). Unchecked items are disabled for this launch; core MK1212 packs remain enabled.";
    alert.addButtonWithTitle(config.actionLabel);
    alert.addButtonWithTitle("Cancel");

    const width = 650;
    const rowHeight = 30;
    const height = Math.max(rowHeight, config.items.length * rowHeight);
    const view = $.NSView.alloc.initWithFrame($.NSMakeRect(0, 0, width, height));
    const boxes = [];
    const ranks = [];
    for (let index = 0; index < config.items.length; index++) {
        const item = config.items[index];
        const box = $.NSButton.alloc.initWithFrame(
            $.NSMakeRect(0, height - ((index + 1) * rowHeight), width - 100, rowHeight)
        );
        box.setButtonType($.NSSwitchButton);
        box.title = $(item.name);
        box.state = item.selected ? 1 : 0;
        view.addSubview(box);
        boxes.push(box);

        const rank = $.NSTextField.alloc.initWithFrame(
            $.NSMakeRect(width - 82, height - ((index + 1) * rowHeight) + 3, 72, rowHeight - 6)
        );
        rank.stringValue = $(String(item.rank));
        rank.alignment = $.NSTextAlignmentRight;
        rank.placeholderString = $("priority");
        view.addSubview(rank);
        ranks.push(rank);
    }
    alert.accessoryView = view;
    $.NSApplication.sharedApplication.activateIgnoringOtherApps(true);
    const response = Number(ObjC.unwrap(alert.runModal));
    if (response !== Number(ObjC.unwrap($.NSAlertFirstButtonReturn))) {
        return "__CANCEL__";
    }
    const rows = [];
    for (let index = 0; index < boxes.length; index++) {
        const name = config.items[index].name;
        const rawRank = Number(ObjC.unwrap(ranks[index].stringValue));
        const rank = Number.isFinite(rawRank) ? rawRank : index + 1;
        rows.push({name: name, selected: Number(ObjC.unwrap(boxes[index].state)) === 1,
                   rank: rank, index: index});
    }
    rows.sort((left, right) => left.rank - right.rank || left.index - right.index);
    const order = rows.map(row => row.name);
    const picked = [];
    for (const row of rows) {
        if (row.selected) {
            picked.push(row.name);
        }
    }
    return JSON.stringify({selected: picked, order: order});
}
'''


def choose_optional_packs(state: dict, action_label: str = "Launch") -> dict | None:
    optionals = optional_load_order(state)
    if not optionals:
        return {"selected": [], "order": []}
    current = {name.casefold() for name in state.get("selected_optional_packs", optionals)}
    items = [{"name": name, "selected": name.casefold() in current, "rank": index + 1}
             for index, name in enumerate(optionals)]
    config = json.dumps({"items": items, "actionLabel": action_label})
    result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", CHECKBOX_PICKER_JXA,
                             "--", config], capture_output=True, text=True)
    if result.returncode != 0:
        raise ToolError("submod chooser failed: " + result.stderr.strip())
    value = result.stdout.strip()
    if value == "__CANCEL__":
        return None
    try:
        picked = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ToolError(f"submod chooser returned invalid data: {value!r}") from exc
    if isinstance(picked, list):
        # Accept the old helper's output if a cached/older app happens to
        # return it; it cannot express a reordered list, but remains safe.
        if any(item not in optionals for item in picked):
            raise ToolError("submod chooser returned an invalid selection")
        return {"selected": [name for name in optionals if name in picked],
                "order": optionals}
    if not isinstance(picked, dict) or not isinstance(picked.get("selected"), list) \
            or not isinstance(picked.get("order"), list):
        raise ToolError("submod chooser returned an invalid selection")
    order = picked["order"]
    selected = picked["selected"]
    if (len(order) != len(optionals) or {str(item).casefold() for item in order} !=
            {name.casefold() for name in optionals} or
            any(item not in order for item in selected) or
            len({str(item).casefold() for item in selected}) != len(selected)):
        raise ToolError("submod chooser returned an invalid order or selection")
    canonical = {name.casefold(): name for name in optionals}
    order = [canonical[str(name).casefold()] for name in order]
    selected_set = {str(name).casefold() for name in selected}
    return {"selected": [name for name in order if name.casefold() in selected_set],
            "order": order}


def show_first_use_notice() -> None:
    script = ('display alert "MK1212 Mac Launcher" message '
              '"This submod combination is being prepared for its first use. This can take up to a minute; ATTILA will open automatically when it is ready." '
              'buttons {"Continue"} default button "Continue"')
    subprocess.run(["/usr/bin/osascript", "-e", script], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install_command(args: argparse.Namespace) -> None:
    if game_running():
        raise ToolError("ATTILA is running; installation is refused")
    game_root = discover_game_root(args.game_root)
    data_root = game_root / "TotalWarAttilaData/data"
    manifest = game_root / "TotalWarAttilaData/feral/en/manifest.txt"
    state_dir = Path(args.state_dir).expanduser().resolve()
    state_file = state_dir / "state.json"
    if (state_dir / "activation.json").exists():
        old = load_state(state_dir)
        recover_stale_activation(state_dir, old)
    if state_file.exists() and load_state(state_dir).get("status") == "prepared":
        raise ToolError("launcher cache is already prepared; verify or uninstall it first")
    active = list(data_root.glob(f"{GENERATED_PREFIX}*"))
    if active:
        raise ToolError("persistent compatibility files are still active: " + ", ".join(p.name for p in active[:8]))
    cache_root = game_root / "TotalWarAttilaData/.mk1212-cache"
    if cache_root.exists():
        raise ToolError(f"unledgered compatibility cache already exists: {cache_root}")
    packs = selected_packs(game_root, args.profile, args.load_order_file)
    plan, lua_winners = plan_compatibility(game_root, packs)
    current_manifest = manifest.read_bytes()
    legacy_lua = [name for name, _ in parse_manifest(current_manifest) if name.casefold().endswith(".lua")]
    if legacy_lua:
        raise ToolError(f"loose-Lua manifest entries are already active ({len(legacy_lua)} found)")
    backup = manifest_backup(manifest, state_dir, "install")
    metadata_by_path = {str(item["source"]): item["metadata"] for item in plan}
    sources = [source_record(pack, metadata_by_path[str(pack)]["pack_type"]) for pack in packs]
    state = {"schema": 3, "tool_version": TOOL_VERSION, "status": "preparing", "created_at": utc_now(),
             "game_root": str(game_root), "data_root": str(data_root), "manifest": str(manifest),
             "cache_root": str(cache_root), "profile": args.profile,
             "load_order_file": ({"path": str(Path(args.load_order_file).expanduser().resolve()),
                                  "sha256": sha256_path(Path(args.load_order_file).expanduser().resolve())}
                                 if args.load_order_file else None),
             "manifest_backups": [backup], "source_packs": sources, "profiles": {},
             "selected_optional_packs": [item["name"] for item in sources if item["optional"]],
             "optional_load_order": [item["name"] for item in sources if item["optional"]]}
    state_dir.mkdir(parents=True, exist_ok=True)
    save_json(state_file, state)
    try:
        full = build_profile_cache(state_dir, game_root, sources, (plan, lua_winners))
        state["profiles"][full["key"]] = full
        state["default_profile_key"] = full["key"]
        core_records = [item for item in sources if not item["optional"]]
        if len(core_records) != len(sources):
            core = build_profile_cache(state_dir, game_root, core_records)
            state["profiles"][core["key"]] = core
            state["core_profile_key"] = core["key"]
        prepare_isolated_home(state_dir)
        state["status"] = "prepared"
        state["prepared_at"] = utc_now()
        save_json(state_file, state)
        verify_command(argparse.Namespace(state_dir=str(state_dir), quick=True, json=False))
    except BaseException:
        shutil.rmtree(cache_root, ignore_errors=True)
        state["status"] = "rolled_back"
        state["rolled_back_at"] = utc_now()
        save_json(state_file, state)
        raise
    full_files = len(full["files"])
    print(f"Prepared {len(state['profiles'])} transient profiles; default has {len(sources)} packs, "
          f"{full_files} cached files, {len(full['dds_repairs'])} DDS repairs, and {full['lua_count']} Lua files.")
    print(f"The live data tree and manifest remain vanilla while the launcher is not running.")
    print(f"Manifest backup: {backup['path']} ({backup['sha256']})")


def verify_command(args: argparse.Namespace) -> None:
    state_dir = Path(args.state_dir).expanduser().resolve()
    state = load_state(state_dir)
    if state.get("status") != "prepared":
        raise ToolError(f"state is {state.get('status')!r}, not prepared")
    activation_path = state_dir / "activation.json"
    if activation_path.exists() and not game_running():
        recover_stale_activation(state_dir, state)
    failures = []
    cached_count = 0
    for profile in state.get("profiles", {}).values():
        cached_count += len(profile["files"])
        failures.extend(verify_profile(profile))
    changed_sources = []
    for record in state["source_packs"]:
        path = Path(record["path"])
        if not path.is_file() or path.stat().st_size != record["size"] or path.stat().st_mtime_ns != record["mtime_ns"]:
            changed_sources.append(str(path))
        elif not args.quick and sha256_path(path) != record["sha256"]:
            changed_sources.append(str(path))
    if changed_sources:
        failures.append("Workshop sources changed; rebuild required: " + ", ".join(changed_sources))
    native = state.get("native_slot_clone")
    if native is not None:
        clone_executable = Path(native.get("clone_executable", ""))
        source_executable = Path(native.get("source_executable", ""))
        if native.get("status") != "ready" or not clone_executable.is_file():
            failures.append("native ten-slot clone is missing or incomplete")
        else:
            try:
                data_link = native_clone_data_link_path(state_dir, state)
                if (data_link.resolve() != Path(state["data_root"]).resolve().parent
                        or (not data_link.is_symlink() and not data_link.is_dir())):
                    raise ToolError("native clone is missing its TotalWarAttilaData sibling link")
                with clone_executable.open("rb") as stream:
                    for patch in NATIVE_SLOT_PATCHES:
                        stream.seek(patch["file_offset"] - 4)
                        if stream.read(len(patch["after_context"])) != patch["after_context"]:
                            raise ToolError(f"native clone patch mismatch at 0x{patch['virtual_address']:x}")
                signed = subprocess.run(
                    ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(Path(native["clone_app"]))],
                    capture_output=True, text=True,
                )
                if signed.returncode != 0:
                    raise ToolError("native clone signature is invalid")
                if not source_executable.is_file() or sha256_path(source_executable) != native["source"]["sha256"]:
                    raise ToolError("original Feral executable changed; native clone rebuild required")
            except (OSError, KeyError, ToolError) as exc:
                failures.append(str(exc))
    active = activation_path.exists()
    manifest = Path(state["manifest"])
    manifest_map: dict[str, list[int]] = {}
    for name, size in parse_manifest(manifest.read_bytes()):
        manifest_map.setdefault(name, []).append(size)
    if active:
        activation = json.loads(activation_path.read_text())
        for record in activation["files"]:
            path = safe_destination(Path(state["data_root"]), record["relative_path"])
            if not active_file_matches(path, record):
                failures.append(f"active runtime file mismatch: {path}")
            if manifest_map.get(record["relative_path"], []) != [record["size"]]:
                failures.append(f"active manifest mismatch: {record['relative_path']}")
        used = Path(activation["used_mods_path"])
        if not used.is_file() or sha256_path(used) != activation["used_mods_sha256"]:
            failures.append(f"active used_mods.txt mismatch: {used}")
    else:
        live_packs = list(Path(state["data_root"]).glob(f"{GENERATED_PREFIX}*"))
        if live_packs:
            failures.append("inactive launcher left generated packs in the live data tree")
        runtime_names = {record["relative_path"] for profile in state.get("profiles", {}).values()
                         for record in profile["files"]}
        leftovers = [name for name in runtime_names if safe_destination(Path(state["data_root"]), name).exists()]
        if leftovers:
            failures.append("inactive launcher left runtime files: " + ", ".join(leftovers[:8]))
        leaked_manifest = [name for name in runtime_names if name in manifest_map]
        if leaked_manifest:
            failures.append("inactive launcher left manifest entries: " + ", ".join(leaked_manifest[:8]))
        used = Path(state["game_root"]) / "TotalWarAttilaData/used_mods.txt"
        if used.exists():
            failures.append(f"inactive launcher left used_mods.txt: {used}")
    result = {"ok": not failures, "failures": failures, "active": active,
              "profile_count": len(state.get("profiles", {})), "cached_file_count": cached_count,
              "source_count": len(state["source_packs"]), "manifest_sha256": sha256_path(manifest),
              "mode": "quick" if args.quick else "full"}
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    elif failures:
        raise ToolError("verification failed:\n  " + "\n  ".join(failures))
    else:
        location = "active transiently" if active else "inactive/vanilla"
        print(f"Verified {result['profile_count']} cached profiles, {result['source_count']} sources, "
              f"and the {location} live tree ({result['mode']}).")


def changed_source_records(state: dict) -> list[dict]:
    changed = []
    for record in state["source_packs"]:
        path = Path(record["path"])
        if not path.is_file():
            changed.append(record)
            continue
        stat = path.stat()
        if (stat.st_size != record["size"] or stat.st_mtime_ns != record["mtime_ns"] or
                ("device" in record and stat.st_dev != record["device"]) or
                ("inode" in record and stat.st_ino != record["inode"])):
            changed.append(record)
    return changed


def confirm_source_rebuild(records: list[dict]) -> bool:
    names = [record["name"] for record in records[:8]]
    if len(records) > len(names):
        names.append(f"and {len(records) - len(names)} more")
    message = ("Workshop files changed since this profile was prepared:\n\n" +
               "\n".join(names) +
               "\n\nRebuild the compatibility cache from the current files? "
               "This may take a few minutes; progress notifications will appear.")
    script = '''on run argv
try
    display dialog (item 1 of argv) with title "MK1212 Mac Launcher" buttons {"Cancel", "Rebuild Cache"} default button "Rebuild Cache" cancel button "Cancel"
    return "REBUILD"
on error number -128
    return "CANCEL"
end try
end run'''
    result = subprocess.run(["/usr/bin/osascript", "-e", script, "--", message],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "REBUILD"


def load_resumable_orphan_profile(cache_root: Path, records: list[dict]) -> dict | None:
    """Reuse a complete profile left on disk before the state ledger was saved."""
    key = profile_key(records)
    profile_dir = cache_root / key
    if not profile_dir.exists() and not profile_dir.is_symlink():
        return None
    if profile_dir.is_symlink() or not profile_dir.is_dir():
        raise ToolError(f"unregistered cache path is not a normal directory; preserving it: {profile_dir}")
    profile_path = profile_dir / "profile.json"
    if not profile_path.is_file():
        raise ToolError(f"unregistered cache is incomplete and was preserved for inspection: {profile_dir}")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"unregistered cache metadata is unreadable and was preserved: {profile_path}") from exc

    source_fields = ("name", "path", "size", "mtime_ns", "sha256", "pack_type", "optional")
    expected_sources = [{field: record.get(field) for field in source_fields} for record in records]
    actual_sources = [{field: record.get(field) for field in source_fields}
                      for record in profile.get("source_packs", [])]
    if (profile.get("key") != key or profile.get("pack_names") != [r["name"] for r in records] or
            profile.get("compatibility_revision") != PROFILE_COMPATIBILITY_REVISION or
            actual_sources != expected_sources or
            Path(profile.get("cache_dir", "")).resolve() != profile_dir.resolve()):
        raise ToolError(f"unregistered cache does not match current sources; preserving it: {profile_dir}")
    failures = verify_profile(profile)
    if failures:
        raise ToolError("unregistered cache failed verification and was preserved:\n  " +
                        "\n  ".join(failures[:12]))
    return profile


def rebuild_profiles_for_current_sources(state_dir: Path, state: dict) -> None:
    """Refresh selected and core caches, reusing verified output after interruption."""
    progress = lambda message, notify=False: report_rebuild_progress(state_dir, message, notify)
    current_sources = state["source_packs"]
    progress(f"Checking {len(current_sources)} Workshop source files", notify=True)
    new_sources = []
    changed_count = 0
    for index, old_record in enumerate(current_sources, start=1):
        path = Path(old_record["path"])
        if not path.is_file():
            raise ToolError(f"Workshop source is missing; resubscribe before rebuilding: {path}")
        stat = path.stat()
        same_file = (("device" not in old_record or stat.st_dev == old_record["device"]) and
                     ("inode" not in old_record or stat.st_ino == old_record["inode"]))
        unchanged = (same_file and stat.st_size == old_record["size"] and
                     stat.st_mtime_ns == old_record["mtime_ns"])
        if unchanged:
            new_sources.append(dict(old_record))
            progress(f"Workshop sources checked: {index}/{len(current_sources)} ({path.name} unchanged)")
            continue
        changed_count += 1
        progress(f"Hashing updated Workshop source {changed_count}: {path.name}", notify=True)
        metadata, _ = read_pack(path)
        if metadata["pack_type"] not in (3, 4):
            raise ToolError(f"updated Workshop source has unsupported pack type: {path}")
        new_sources.append(source_record(
            path, metadata["pack_type"],
            progress=lambda detail, name=path.name: progress(
                f"{name}: {detail}",
                notify=any(detail.endswith(f": {percent}%") for percent in (25, 50, 75, 100)),
            ),
        ))

    if not changed_count:
        progress("No changed source files needed refreshing")
    names = selected_names(state, state.get("selected_optional_packs", optional_pack_names(state)))
    source_by_name = {record["name"].casefold(): record for record in new_sources}
    try:
        selected = [source_by_name[name.casefold()] for name in names]
        core = [record for record in new_sources if not record["optional"]]
    except KeyError as exc:
        raise ToolError(f"selected pack is missing from the source inventory: {exc.args[0]}") from exc

    profiles = dict(state.get("profiles", {}))
    cache_root = Path(state["game_root"]) / "TotalWarAttilaData/.mk1212-cache/profiles"

    def prepare(records: list[dict], label: str) -> dict:
        key = profile_key(records)
        cached = profiles.get(key)
        if cached is not None:
            progress(f"Verifying saved {label} cache", notify=True)
            failures = verify_profile(cached)
            if failures:
                raise ToolError("existing profile cache verification failed:\n  " +
                                "\n  ".join(failures[:12]))
            progress(f"Reused saved {label} cache")
            return cached
        orphan = load_resumable_orphan_profile(cache_root, records)
        if orphan is not None:
            progress(f"Resuming: found and verified completed {label} cache {key}", notify=True)
            profiles[key] = orphan
            return orphan
        progress(f"Building {label} compatibility cache {key}", notify=True)
        profile = build_profile_cache(
            state_dir, Path(state["game_root"]), records,
            progress=lambda message: progress(f"{label}: {message}"),
        )
        profiles[profile["key"]] = profile
        return profile

    try:
        selected_profile = prepare(selected, "selected")
        core_profile = prepare(core, "core")
        progress("Checking that Workshop packs stayed unchanged during the rebuild", notify=True)
        for index, record in enumerate(new_sources, start=1):
            path = Path(record["path"])
            stat = path.stat()
            if (stat.st_size != record["size"] or stat.st_mtime_ns != record["mtime_ns"] or
                    ("device" in record and stat.st_dev != record["device"]) or
                    ("inode" in record and stat.st_ino != record["inode"])):
                raise ToolError(f"Workshop source changed during rebuild; retry after it finishes updating: {path}")
            if index % 4 == 0 or index == len(new_sources):
                progress(f"Workshop stability check: {index}/{len(new_sources)}")

        updated = dict(state)
        updated["source_packs"] = new_sources
        updated["profiles"] = profiles
        updated["default_profile_key"] = selected_profile["key"]
        updated["core_profile_key"] = core_profile["key"]
        updated["rebuilt_at"] = utc_now()
        progress("Saving the refreshed cache ledger", notify=True)
        save_json(state_dir / "state.json", updated)
        state.clear()
        state.update(updated)
        progress("Workshop cache refresh complete; the submod selector will open next", notify=True)
    except Exception as exc:
        progress(f"Refresh paused before the state file was updated: {exc}. "
                 "Completed cache folders were preserved for resume.", notify=True)
        raise


def uninstall_command(args: argparse.Namespace) -> None:
    if game_running():
        raise ToolError("ATTILA is running; uninstall is refused")
    state_dir = Path(args.state_dir).expanduser().resolve()
    state = load_state(state_dir)
    if state.get("status") != "prepared":
        raise ToolError(f"state is {state.get('status')!r}, not prepared")
    recover_stale_activation(state_dir, state)
    verify_command(argparse.Namespace(state_dir=str(state_dir), quick=True, json=False))
    backup = manifest_backup(Path(state["manifest"]), state_dir, "uninstall")
    cache_root = Path(state["cache_root"])
    expected = Path(state["game_root"]) / "TotalWarAttilaData/.mk1212-cache"
    if cache_root.resolve() != expected.resolve():
        raise ToolError(f"refusing unexpected cache removal target: {cache_root}")
    shutil.rmtree(cache_root)
    native = state.get("native_slot_clone")
    if native:
        native_app = Path(native.get("clone_app", ""))
        expected_native_app = Path(state["game_root"]) / NATIVE_CLONE_DIRNAME
        if native_app.resolve() != expected_native_app.resolve():
            raise ToolError(f"refusing unexpected native clone removal target: {native_app}")
        if native_app.exists():
            shutil.rmtree(native_app)
    state["status"] = "uninstalled"
    state["uninstalled_at"] = utc_now()
    state["uninstall_manifest_backup"] = backup
    save_json(state_dir / "state.json", state)
    print(f"Removed {len(state.get('profiles', {}))} cached profiles. The live ATTILA tree was already vanilla.")


def configure_command(args: argparse.Namespace) -> None:
    state_dir = Path(args.state_dir).expanduser().resolve()
    state = load_state(state_dir)
    if state.get("status") != "prepared":
        raise ToolError(f"state is {state.get('status')!r}, not prepared")
    recover_stale_activation(state_dir, state)
    refresh_optional_sources(state)
    choice = choose_optional_packs(state, "Save")
    if choice is None:
        print("Submod selection cancelled.")
        return
    state["optional_load_order"] = choice["order"]
    state["selected_optional_packs"] = choice["selected"]
    names = selected_names(state, choice["selected"])
    if profile_key(records_for_names(state, names)) not in state.get("profiles", {}):
        show_first_use_notice()
    profile = ensure_profile(state_dir, state, names)
    save_json(state_dir / "state.json", state)
    print("Selected optional submods: " +
          (", ".join(choice["selected"]) if choice["selected"] else "none (core only)"))
    print(f"Prepared profile {profile['key']} with {len(profile['pack_names'])} packs.")


def launch_command(args: argparse.Namespace) -> None:
    if game_running():
        raise ToolError("ATTILA is already running; launch is refused")
    state_dir = Path(args.state_dir).expanduser().resolve()
    state = load_state(state_dir)
    if state.get("status") != "prepared":
        raise ToolError(f"state is {state.get('status')!r}, not prepared")
    recover_stale_activation(state_dir, state)
    refresh_optional_sources(state)
    changed = changed_source_records(state)
    if changed:
        if not confirm_source_rebuild(changed):
            print("Workshop cache rebuild cancelled.")
            return
        rebuild_profiles_for_current_sources(state_dir, state)
    verify_command(argparse.Namespace(state_dir=str(state_dir), quick=True, json=False))
    if args.core_only:
        picked = []
    elif args.no_picker:
        picked = state.get("selected_optional_packs", optional_pack_names(state))
    else:
        report_rebuild_progress(state_dir, "Opening the optional submod selector", notify=True)
        choice = choose_optional_packs(state)
        if choice is None:
            report_rebuild_progress(
                state_dir, "Submod selection cancelled; ATTILA was not launched", notify=True,
            )
            print("Launch cancelled.")
            return
        state["optional_load_order"] = choice["order"]
        picked = choice["selected"]
        report_rebuild_progress(state_dir, "Submod selection confirmed; preparing ATTILA launch",
                                notify=True)
    state["selected_optional_packs"] = picked
    names = selected_names(state, picked)
    if profile_key(records_for_names(state, names)) not in state.get("profiles", {}):
        show_first_use_notice()
    profile = ensure_profile(state_dir, state, names)
    save_json(state_dir / "state.json", state)
    game_root = Path(state["game_root"])
    original_executable = game_root / EXECUTABLE_RELATIVE
    executable = original_executable
    if not executable.is_file():
        raise ToolError(f"selected ATTILA executable is missing: {executable}")
    executable_sha256 = sha256_path(executable)
    if executable_sha256 != SUPPORTED_RUNTIME_EXECUTABLE_SHA256:
        raise ToolError(
            "the ten-slot runtime patch supports only Feral ATTILA 1.6.1 build 480285.103778; "
            f"found executable SHA-256 {executable_sha256}"
        )
    runtime_library = Path(__file__).resolve().with_name("libmk1212-slot-runtime-patch.dylib")
    if not runtime_library.is_file():
        # Source-tree commands use the reproducible build output; packaged apps
        # carry the same signed library beside this Python module.
        development_library = Path(__file__).resolve().parents[1] / "build/libmk1212-slot-runtime-patch.dylib"
        if development_library.is_file():
            runtime_library = development_library
    if not runtime_library.is_file():
        raise ToolError(f"ten-slot runtime patch library is missing: {runtime_library}")
    signature = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", str(runtime_library)],
        capture_output=True, text=True,
    )
    if signature.returncode != 0:
        raise ToolError("ten-slot runtime patch library signature is invalid: " + signature.stderr.strip())
    home = prepare_isolated_home(state_dir)
    activation = activate_profile(state_dir, state, profile)
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    launch_stamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    log = log_dir / f"launch-{launch_stamp}.json"
    patch_log = log_dir / f"ten-slot-runtime-patch-{launch_stamp}.log"
    payload = {"tool_version": TOOL_VERSION, "launched_at": utc_now(), "executable": str(executable),
               "executable_sha256": executable_sha256, "cwd": str(game_root / "TotalWarAttilaData"),
               "original_executable": str(original_executable),
               "original_executable_sha256": sha256_path(original_executable),
               "argv": [str(executable)], "isolated_home": str(home),
               "feral_app_unchanged": True,
               "ten_slot_runtime_patch_library": str(runtime_library),
               "ten_slot_runtime_patch_log": str(patch_log),
               "profile_key": profile["key"], "pack_names": profile["pack_names"],
               "optional_packs": picked, "dds_repairs": profile["dds_repairs"],
               "lua_repairs": profile.get("lua_repairs", []),
               "activation_id": activation["id"]}
    save_json(log, payload)
    environment = os.environ.copy()
    environment["CFFIXED_USER_HOME"] = str(home)
    environment["MK1212_MAC_SLOT_LOG"] = str(log_dir / "slot-diagnostic.log")
    environment["MK1212_MAC_SLOT_PATCH_LOG"] = str(patch_log)
    environment["DYLD_INSERT_LIBRARIES"] = str(runtime_library)
    environment.setdefault("SteamAppId", APP_ID)
    environment.setdefault("SteamGameId", APP_ID)
    child = None
    old_handlers = {}
    try:
        child = subprocess.Popen([str(executable)], cwd=game_root / "TotalWarAttilaData", env=environment)
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda received, frame: child.send_signal(received) if child.poll() is None else None)
        old_handlers[signal.SIGHUP] = signal.getsignal(signal.SIGHUP)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        return_code = child.wait()
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        if child is not None and child.poll() is None:
            child.wait()
        deactivate_profile(state_dir, state, activation)
    if return_code != 0:
        patch_result = patch_log.read_text(errors="replace").strip() if patch_log.is_file() else "no patch log"
        raise ToolError(
            f"ATTILA exited with status {return_code}; transient compatibility files were removed. "
            f"Ten-slot patch report: {patch_result}"
        )
    patch_result = patch_log.read_text(errors="replace").strip() if patch_log.is_file() else ""
    if "status=patched-6-to-10 kern_return=0" not in patch_result:
        raise ToolError(
            "ATTILA exited, but the ten-slot runtime patch did not report success; "
            f"inspect {patch_log}"
        )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE))
    parser.add_argument("--game-root")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect"); inspect.add_argument("--profile", choices=("mk1212", "feral"), default="mk1212"); inspect.add_argument("--load-order-file"); inspect.set_defaults(func=inspect_command)
    install = sub.add_parser("install"); install.add_argument("--profile", choices=("mk1212", "feral"), default="mk1212"); install.add_argument("--load-order-file"); install.set_defaults(func=install_command)
    verify = sub.add_parser("verify"); verify.add_argument("--quick", action="store_true"); verify.add_argument("--json", action="store_true"); verify.set_defaults(func=verify_command)
    uninstall = sub.add_parser("uninstall"); uninstall.set_defaults(func=uninstall_command)
    configure = sub.add_parser("configure"); configure.set_defaults(func=configure_command)
    launch = sub.add_parser("launch")
    launch.add_argument("--no-picker", action="store_true", help="reuse the last optional-submod selection")
    launch.add_argument("--core-only", action="store_true", help="disable every optional submod for this launch")
    launch.set_defaults(func=launch_command)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        args.func(args)
    except (ToolError, OSError, ValueError, KeyError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
