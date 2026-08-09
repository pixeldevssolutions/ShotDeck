"""Media inspection, with and without ffprobe."""

import os
import tempfile

import config
import media_inspector as mi

TMP = tempfile.mkdtemp(prefix="shotdeck-media-")


def _file(name, size=1024):
    path = os.path.join(TMP, name)
    with open(path, "wb") as f:
        f.write(b"\x00" * size)
    return path


def test_kinds_come_from_the_registry():
    assert config.media_kind("/jobs/x/plate.mov") == "movie"
    assert config.media_kind("/jobs/x/plate.EXR") == "image"
    assert config.media_kind("/jobs/x/notes.txt") == ""
    assert config.media_kind("") == ""


def test_registry_covers_the_formats_production_uses():
    for ext in (".mov", ".mp4", ".mxf", ".avi"):
        assert ext in config.MOVIE_EXTENSIONS
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr"):
        assert ext in config.IMAGE_EXTENSIONS


def test_file_dialog_filter_is_built_from_the_registry():
    text = config.media_filter()
    assert "*.mov" in text and "*.exr" in text
    assert text.startswith("Media (")


def test_missing_file_reports_rather_than_raises():
    info = mi.inspect(os.path.join(TMP, "nothing.mov"))
    assert not info.exists
    assert info.error == "File does not exist"
    assert info.size == 0


def test_unreadable_media_still_yields_size_and_kind():
    """A file ffprobe cannot parse is still publishable; it just shows less."""
    info = mi.inspect(_file("garbage.mov", 4096))
    assert info.kind == "movie"
    assert info.size == 4096
    assert info.summary().endswith("4.0 KB")


def test_png_resolution_is_read():
    from PySide6.QtGui import QPixmap, QColor
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    path = os.path.join(TMP, "plate.png")
    pm = QPixmap(640, 360)
    pm.fill(QColor("#3d9dff"))
    pm.save(path)

    info = mi.inspect(path)
    assert (info.width, info.height) == (640, 360)
    assert info.resolution == "640 × 360"
    assert "640 × 360" in info.summary()


def test_human_size_steps_up_units():
    assert mi.human_size(512) == "512 B"
    assert mi.human_size(1536) == "1.5 KB"
    assert mi.human_size(1024 ** 3 + 1024 ** 3 // 2) == "1.5 GB"


def test_summary_orders_movie_facts():
    info = mi.MediaInfo(_file("shot.mov", 2048))
    info.width, info.height = 1920, 1080
    info.fps, info.frames = 24, 120
    info.codec = "prores"
    text = info.summary()
    assert text.startswith("1920 × 1080")
    assert "24 fps" in text and "120 frames" in text and "prores" in text


def test_frame_count_falls_back_to_duration_times_rate():
    info = mi.MediaInfo(_file("nb_frames_missing.mov"))
    info.fps, info.duration = 25.0, 4.0
    assert mi._frames({}, info) == 100


def test_fps_is_parsed_from_a_rational():
    assert mi._fps({"avg_frame_rate": "24000/1001"}) == 23.976
    assert mi._fps({"avg_frame_rate": "0/0", "r_frame_rate": "25/1"}) == 25.0
    assert mi._fps({}) is None


def test_bit_depth_falls_back_to_the_pixel_format():
    assert mi._bit_depth({"bits_per_raw_sample": "10"}) == 10
    assert mi._bit_depth({"pix_fmt": "gbrpf32le"}) == 32
    assert mi._bit_depth({}) is None


def test_as_dict_is_loggable():
    info = mi.inspect(_file("clip.mov"))
    data = info.as_dict()
    assert data["kind"] == "movie" and data["size"] == 1024
    assert "path" in data
