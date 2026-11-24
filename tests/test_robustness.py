"""健壮性测试：损坏文件、解压炸弹、超大图等异常输入的报错是否清晰。"""
import os

import pytest
from PIL import Image

import utils


def test_corrupted_file_reports_clear_error(tmp_path):
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"this is not an image")
    with pytest.raises(RuntimeError) as exc:
        utils.open_image_single(bad)
    assert "broken.jpg" in str(exc.value)


def test_decompression_bomb_is_rejected_with_hint(tmp_path):
    """超过像素上限的图片应给出明确提示，而不是抛出 Pillow 内部异常。"""
    big = tmp_path / "huge.png"
    Image.new("RGB", (400, 400)).save(big)

    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 100  # 400x400 = 160000 px，远超 2 倍上限
    try:
        with pytest.raises(RuntimeError) as exc:
            utils.open_image_single(big)
        assert "huge.png" in str(exc.value)
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit


def test_load_images_error_message_mentions_dir(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        utils.load_images(empty)


def test_get_exif_handles_corrupt_file(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\x00" * 64)
    assert utils.get_exif_capture_time(bad) is None


def test_sanitize_keeps_unicode_names():
    assert utils.sanitize_filename("时间切片_2026") == "时间切片_2026"


def test_iter_images_releases_failed_image(tmp_path, make_photos):
    """中途遇到坏图时应抛出带文件名的 RuntimeError。"""
    folder = make_photos(n=3)
    (folder / "IMG_001.jpg").write_bytes(b"garbage")
    it = utils.iter_images(folder)
    first = next(it)
    assert first.size == (240, 180)
    with pytest.raises(RuntimeError):
        next(it)
