"""切片算法测试：空输入、单图、覆盖完整性、接缝无黑缝、流式输入。"""
import numpy as np
import pytest
from PIL import Image

from slices import (_common, create_circular_band_slice, create_circular_sector_slice,
                    create_elliptical_band_slice, create_elliptical_sector_slice,
                    create_horizontal_s_slice, create_horizontal_slice,
                    create_rectangular_band_slice, create_vertical_s_slice,
                    create_vertical_slice)

W, H, N = 240, 180, 6
COLORS = [((i * 40) % 256, 90 + i * 10, 180) for i in range(N)]


def imgs(n=N, size=(W, H)):
    return [Image.new("RGB", size, COLORS[i % len(COLORS)]) for i in range(n)]


@pytest.mark.parametrize("factory", [
    lambda im, **k: create_vertical_slice(im, position="center", **k),
    lambda im, **k: create_horizontal_slice(im, position="center", **k),
    lambda im, **k: create_circular_sector_slice(im, **k),
    lambda im, **k: create_elliptical_sector_slice(im, **k),
    lambda im, **k: create_elliptical_band_slice(im, **k),
    lambda im, **k: create_rectangular_band_slice(im, **k),
    lambda im, **k: create_circular_band_slice(im, **k),
    lambda im, **k: create_vertical_s_slice(im, position="center", **k),
    lambda im, **k: create_horizontal_s_slice(im, position="center", **k),
])
def test_empty_input_returns_placeholder(factory):
    out = factory([])
    assert out.size == (1, 1)


@pytest.mark.parametrize("fn", [create_vertical_slice, create_horizontal_slice, create_vertical_s_slice])
def test_empty_input_with_declared_count_does_not_crash(fn):
    """调用方声明数量但实际没有图片时也不能 AttributeError。"""
    out = fn([], position="center", num_images=10)
    assert out.size == (1, 1)


def test_single_image_vertical_returns_original():
    src = imgs(1)[0]
    out = create_vertical_slice([src], position="center")
    assert out.size == src.size


def test_vertical_stripes_are_contiguous_and_colored():
    """垂直条带按顺序铺满整图，且不出现黑缝。"""
    out = create_vertical_slice(imgs(), position="center")
    arr = np.asarray(out.convert("RGB"))
    assert arr.shape == (H, W, 3)
    assert int((arr.sum(axis=2) == 0).sum()) == 0
    # 每条的宽度应为 W / N，取每条中心像素比对颜色
    step = W / N
    for i in range(N):
        x = int(i * step + step / 2)
        assert tuple(arr[H // 2, x]) == COLORS[i]


def test_horizontal_stripes_have_no_gap():
    out = create_horizontal_slice(imgs(), position="top")
    arr = np.asarray(out.convert("RGB"))
    assert int((arr.sum(axis=2) == 0).sum()) == 0


@pytest.mark.parametrize("fn", [create_vertical_s_slice, create_horizontal_s_slice])
def test_s_curve_has_no_black_seam(fn):
    out = fn(imgs(n=6), position="center")
    arr = np.asarray(out.convert("RGB"))
    assert int((arr.sum(axis=2) == 0).sum()) == 0


def test_s_curve_linear_mode_covers_every_region():
    out = create_vertical_s_slice(imgs(n=4), position="center", linear=True)
    arr = np.asarray(out.convert("RGB"))
    assert int((arr.sum(axis=2) == 0).sum()) == 0


def test_band_outer_ring_covers_short_side():
    """同心环带最外圈应完整覆盖短边对应的内切区域（中心区域不留黑）。"""
    out = create_circular_band_slice(imgs())
    arr = np.asarray(out.convert("RGB"))
    r = min(W, H) // 2
    cy, cx = H // 2, W // 2
    yy, xx = np.ogrid[:H, :W]
    inside = ((yy - cy) ** 2 + (xx - cx) ** 2) < (r - 2) ** 2
    assert int((arr.sum(axis=2) == 0)[inside].sum()) == 0


def test_stream_input_with_num_images():
    """生成器输入 + 显式数量，模拟 cli 的流式加载路径。"""
    def gen():
        for img in imgs():
            yield img

    out = create_vertical_slice(gen(), position="center", num_images=N)
    assert out.size == (W, H)


def test_iter_with_count_from_list():
    it, n, first = _common.iter_with_count(imgs())
    assert n == N and first is not None
    assert len(list(it)) == N


def test_iter_with_count_materializes_generator_without_count():
    it, n, _ = _common.iter_with_count((img for img in imgs()))
    assert n == N
    assert len(list(it)) == N


def test_progress_callback_called_per_image():
    calls = []
    create_vertical_slice(imgs(), position="center", progress_callback=calls.append)
    assert calls == list(range(1, N + 1))
