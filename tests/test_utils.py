"""utils 模块的测试：目录发现、排序、文件名清洗、尺寸适配、时间戳。"""
import os

import pytest
from PIL import Image

import utils


def test_discovers_uppercase_suffixes(make_photos):
    """大小写不敏感：.JPG / .PNG 也要被发现（相机常输出大写后缀）。"""
    folder = make_photos(n=3, suffix=".JPG", dir_name="upper")
    paths = utils.get_sorted_image_paths(folder)
    assert len(paths) == 3
    assert all(p.suffix == ".JPG" for p in paths)


def test_mixed_suffixes_and_ignores_non_images(make_photos):
    folder = make_photos(n=2, suffix=".jpg", dir_name="mixed")
    Image.new("RGB", (8, 8)).save(folder / "SECOND.PNG")
    (folder / "notes.txt").write_text("hello", encoding="utf-8")
    (folder / "subdir.jpg").mkdir()
    paths = utils.get_sorted_image_paths(folder)
    names = sorted(p.name for p in paths)
    assert names == ["IMG_000.jpg", "IMG_001.jpg", "SECOND.PNG"]


def test_natural_sort_and_reverse(make_photos):
    folder = make_photos(n=12, suffix=".jpg", dir_name="sorted")
    paths = utils.get_sorted_image_paths(folder)
    assert [p.name for p in paths][:3] == ["IMG_000.jpg", "IMG_001.jpg", "IMG_002.jpg"]
    assert [p.name for p in utils.get_sorted_image_paths(folder, reverse=True)][0] == "IMG_011.jpg"


def test_natural_sort_key_numeric_order():
    names = ["IMG_10.jpg", "IMG_2.jpg", "IMG_1.jpg"]
    assert sorted(names, key=utils.natural_sort_key) == ["IMG_1.jpg", "IMG_2.jpg", "IMG_10.jpg"]


def test_missing_dir_returns_empty():
    assert utils.get_sorted_image_paths("/nonexistent/path/for/pts") == []


@pytest.mark.parametrize("raw,expected", [
    ("a/b:c*d", "a_b_c_d"),
    ("  spaced  ", "spaced"),
    ("CON", "CON_"),
    ("", "timeslice"),
    ("...", "timeslice"),
])
def test_sanitize_filename(raw, expected):
    assert utils.sanitize_filename(raw) == expected


def test_fit_image_strategies():
    src = Image.new("RGB", (400, 300))
    assert utils.fit_image(src, (200, 200), utils.FIT_STRETCH).size == (200, 200)
    assert utils.fit_image(src, (200, 200), utils.FIT_CROP_CENTER).size == (200, 200)
    out = utils.fit_image(src, (200, 200), utils.FIT_SCALE_CENTER, (255, 0, 0))
    assert out.size == (200, 200)
    # 4:3 缩放进 200x200 后上下会补红边
    assert out.getpixel((2, 2)) == (255, 0, 0)


def test_fit_none_rejects_mismatched_size():
    src = Image.new("RGB", (400, 300))
    with pytest.raises(ValueError):
        utils.fit_image(src, (200, 200), utils.FIT_NONE)


def test_fit_image_same_size_returns_input():
    src = Image.new("RGB", (10, 10))
    assert utils.fit_image(src, (10, 10)) is src


def test_iter_images_streams_and_fits(make_photos):
    folder = make_photos(n=4, size=(240, 180))
    imgs = list(utils.iter_images(folder))
    assert len(imgs) == 4
    assert all(img.size == (240, 180) for img in imgs)


def test_iter_images_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        next(utils.iter_images("/nonexistent/pts/dir"))


def test_compute_timestamp_composition_shape(make_photos):
    folder = make_photos(n=2)
    ts = utils.compute_timestamp("composition", str(folder))
    assert len(ts) == 15 and ts[8] == "_" and ts.replace("_", "").isdigit()


def test_compute_timestamp_falls_back_to_mtime(make_photos):
    folder = make_photos(n=2)
    ts = utils.compute_timestamp("first_modified", str(folder))
    expected = utils.format_timestamp(
        __import__("datetime").datetime.fromtimestamp(utils.get_file_modification_time(
            utils.get_sorted_image_paths(folder)[0])))
    assert ts == expected


def test_exif_capture_time_absent(make_photos):
    folder = make_photos(n=1)
    assert utils.get_exif_capture_time(utils.get_sorted_image_paths(folder)[0]) is None


def test_exif_orientation_is_applied(tmp_path):
    """手机竖拍照片（像素横放 + Orientation=6）应按方向摆正，否则切片会“躺倒”。"""
    path = tmp_path / "portrait.jpg"
    img = Image.new("RGB", (200, 100), (200, 0, 0))
    exif = img.getexif()
    exif[0x0112] = 6
    img.save(path, exif=exif)
    assert utils.open_image_single(path).size == (100, 200)


def test_no_orientation_tag_keeps_size(make_photos):
    folder = make_photos(n=1, size=(240, 180))
    assert utils.open_image_single(utils.get_sorted_image_paths(folder)[0]).size == (240, 180)
