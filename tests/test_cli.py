"""cli.run_timeslice 的端到端测试：9 种切片、格式白名单、防覆盖、进度回调。"""
import os

import pytest
from PIL import Image

import cli

SLICE_TYPES = [
    "vertical", "horizontal", "circular_sector", "elliptical_sector", "elliptical_band",
    "rectangular_band", "circular_band", "vertical_s", "horizontal_s",
]


@pytest.mark.parametrize("slice_type", SLICE_TYPES)
def test_each_slice_type_produces_image(slice_type, make_photos, out_dir):
    folder = make_photos(n=6, size=(240, 180))
    path = cli.run_timeslice(str(folder), str(out_dir), slice_type, extension="png",
                             output_basename=slice_type, lang="en")
    assert os.path.exists(path)
    with Image.open(path) as img:
        assert img.size == (240, 180)
        assert img.mode == "RGB"


@pytest.mark.parametrize("bad_ext", ["gif", "png/../../escaped", "../evil", "", "bmp", "jpg.exe"])
def test_rejects_disallowed_extensions(bad_ext, make_photos, out_dir):
    folder = make_photos(n=2)
    with pytest.raises(ValueError):
        cli.run_timeslice(str(folder), str(out_dir), "vertical", extension=bad_ext)


def test_extension_is_normalized(make_photos, out_dir):
    folder = make_photos(n=2)
    path = cli.run_timeslice(str(folder), str(out_dir), "vertical", extension=".PNG")
    assert path.endswith(".png")


def test_output_stays_inside_output_dir(make_photos, out_dir):
    folder = make_photos(n=2)
    path = cli.run_timeslice(str(folder), str(out_dir), "vertical")
    assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(out_dir)


def test_existing_file_is_not_overwritten(make_photos, out_dir):
    folder = make_photos(n=2)
    first = cli.run_timeslice(str(folder), str(out_dir), "vertical", output_basename="dup")
    second = cli.run_timeslice(str(folder), str(out_dir), "vertical", output_basename="dup")
    assert first != second
    assert os.path.exists(first) and os.path.exists(second)
    assert os.path.basename(second).startswith("dup_1")


def test_no_temp_file_left_behind(make_photos, out_dir):
    folder = make_photos(n=2)
    cli.run_timeslice(str(folder), str(out_dir), "vertical", output_basename="atomic")
    assert not [n for n in os.listdir(out_dir) if n.endswith(".tmp")]


def test_progress_callback_reports_start_and_end(make_photos, out_dir):
    folder = make_photos(n=5)
    seen = []
    cli.run_timeslice(str(folder), str(out_dir), "vertical", progress_callback=seen.append)
    assert seen[0] == 0
    assert seen[-1] == 5


def test_empty_dir_raises(make_photos, out_dir, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(Exception):
        cli.run_timeslice(str(empty), str(out_dir), "vertical")


def test_missing_input_dir_raises(out_dir):
    with pytest.raises(Exception):
        cli.run_timeslice("/nonexistent/pts/input", str(out_dir), "vertical")


def test_unknown_slice_type_raises(make_photos, out_dir):
    folder = make_photos(n=2)
    with pytest.raises(Exception):
        cli.run_timeslice(str(folder), str(out_dir), "diagonal")


def test_filename_pieces(make_photos, out_dir):
    folder = make_photos(n=2)
    path = cli.run_timeslice(str(folder), str(out_dir), "vertical_s", output_basename="my_slice",
                             include_timestamp=True, include_slice_type=True, lang="en")
    name = os.path.basename(path)
    assert name.startswith("my_slice-")
    assert name.endswith(".jpg")


def test_generate_output_filename_sanitizes_base():
    name = cli.generate_output_filename("a/b", False, False, "vertical", "jpg")
    assert name == "a_b.jpg"
