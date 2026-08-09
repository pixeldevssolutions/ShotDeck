"""Work out what a media file actually is, before anything is published.

Deliberately dependency-free: ffprobe if the box has it (every VFX box does,
and it reads EXR and DPX as happily as it reads a mov), Qt's own image reader
as a fallback for stills, and file size alone as the floor. Nothing here raises
-- a file that cannot be inspected is still publishable, it just shows less.

No Qt import at module level, so this stays usable from a headless probe.
"""

import json
import os
import shutil
import subprocess

import applog
import config

log = applog.get()


class MediaInfo:
    """What we managed to learn about one file."""

    def __init__(self, path):
        self.path = path
        self.exists = os.path.isfile(path)
        self.size = os.path.getsize(path) if self.exists else 0
        self.kind = config.media_kind(path)          # "movie" / "image" / ""
        self.container = os.path.splitext(path)[1].lstrip(".").lower()

        self.width = None
        self.height = None
        self.fps = None
        self.frames = None
        self.duration = None        # seconds
        self.codec = None
        self.bit_depth = None
        self.channels = None
        self.source = None          # which inspector produced the numbers
        self.error = None           # why there are no numbers

    # -- presentation ------------------------------------------------------

    @property
    def resolution(self):
        if self.width and self.height:
            return f"{self.width} × {self.height}"
        return None

    def summary(self):
        """One line for the dialog: the facts that fit, in production order."""
        bits = [self.resolution]
        if self.kind == "movie":
            if self.fps:
                bits.append(f"{self.fps:g} fps")
            if self.frames:
                bits.append(f"{self.frames} frames")
            elif self.duration:
                bits.append(f"{self.duration:.1f}s")
            if self.codec:
                bits.append(self.codec)
        else:
            if self.bit_depth:
                bits.append(f"{self.bit_depth}-bit")
            if self.channels:
                bits.append(self.channels)
        bits.append(human_size(self.size))
        return "   |   ".join(b for b in bits if b)

    def as_dict(self):
        """Flat form, for logging and for the Version's own fields."""
        return {
            "path": self.path, "kind": self.kind, "size": self.size,
            "width": self.width, "height": self.height, "fps": self.fps,
            "frames": self.frames, "duration": self.duration,
            "codec": self.codec, "container": self.container,
            "bit_depth": self.bit_depth, "channels": self.channels,
            "source": self.source,
        }

    def __repr__(self):
        return f"<MediaInfo {os.path.basename(self.path)} {self.summary()}>"


def human_size(num):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0


def inspect(path):
    """MediaInfo for `path`. Never raises."""
    info = MediaInfo(path)
    if not info.exists:
        info.error = "File does not exist"
        return info

    if _ffprobe_path():
        try:
            _probe(info)
            return info
        except Exception as e:                      # pragma: no cover
            log.warning("ffprobe failed on %s: %s", path, e)
            info.error = str(e)

    if info.kind == "image":
        _read_image_header(info)
    return info


# -- ffprobe ---------------------------------------------------------------

def _ffprobe_path():
    exe = config.FFPROBE
    return exe if exe and shutil.which(exe.split()[0]) else None


def _probe(info):
    exe = _ffprobe_path()
    cmd = [exe, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", info.path]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=config.FFPROBE_TIMEOUT)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "ffprobe failed").strip())

    data = json.loads(out.stdout or "{}")
    stream = next((s for s in data.get("streams", [])
                   if s.get("codec_type") == "video"), None)
    if not stream:
        raise RuntimeError("no video or image stream found")

    info.source = "ffprobe"
    info.width = stream.get("width")
    info.height = stream.get("height")
    info.codec = stream.get("codec_name")
    info.bit_depth = _bit_depth(stream)
    info.channels = _channels(stream)

    if info.kind == "movie":
        info.fps = _fps(stream)
        info.duration = _duration(stream, data.get("format") or {})
        info.frames = _frames(stream, info)
    info.error = None


def _fps(stream):
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = stream.get(key) or ""
        if "/" in value:
            num, den = value.split("/", 1)
            try:
                num, den = float(num), float(den)
            except ValueError:
                continue
            if den:
                return round(num / den, 3)
    return None


def _duration(stream, fmt):
    for value in (stream.get("duration"), fmt.get("duration")):
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _frames(stream, info):
    try:
        return int(stream["nb_frames"])
    except (KeyError, TypeError, ValueError):
        pass
    # Containers that do not carry a frame count (mxf, some movs) still give a
    # duration, and duration × rate is what an artist would work out anyway.
    if info.fps and info.duration:
        return int(round(info.fps * info.duration))
    return None


def _bit_depth(stream):
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        try:
            depth = int(stream[key])
        except (KeyError, TypeError, ValueError):
            continue
        if depth:
            return depth
    # EXR half float and friends only announce themselves through the pixel
    # format name.
    fmt = (stream.get("pix_fmt") or "").lower()
    for token, depth in (("f32", 32), ("f16", 16), ("16", 16), ("10", 10),
                         ("12", 12), ("8", 8)):
        if token in fmt:
            return depth
    return None


def _channels(stream):
    fmt = (stream.get("pix_fmt") or "").lower()
    if not fmt:
        return None
    if fmt.startswith("gray"):
        return "grayscale"
    if "a" in fmt.replace("yuva", "a").replace("rgba", "a"):
        return "RGBA"
    return "RGB"


# -- Qt fallback ------------------------------------------------------------

def _read_image_header(info):
    """Resolution from Qt's reader, which parses the header only."""
    try:
        from PySide6.QtGui import QImageReader
    except ImportError:                             # pragma: no cover
        return
    reader = QImageReader(info.path)
    size = reader.size()
    if size.isValid():
        info.width, info.height = size.width(), size.height()
        info.source = "QImageReader"
        info.error = None
    elif not info.error:
        info.error = reader.errorString() or "no reader for this format"
