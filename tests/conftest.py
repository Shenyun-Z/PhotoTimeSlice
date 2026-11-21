"""pytest 公共夹具：在临时目录里生成可控的合成照片。"""
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _solid(size, color):
    return Image.new("RGB", size, color)


@pytest.fixture
def make_photos(tmp_path):
    """返回一个工厂函数：make_photos(n=6, size=(240,180), suffix='.jpg', dir_name='in')

    每张图为纯色，颜色互不相同，便于断言“第 i 条带来自第 i 张图”。
    """

    def _factory(n=6, size=(240, 180), suffix=".jpg", dir_name="in", colors=None):
        folder = tmp_path / dir_name
        folder.mkdir(parents=True, exist_ok=True)
        palette = colors or [((i * 30) % 256, 80 + (i * 10) % 120, 200) for i in range(n)]
        for i in range(n):
            img = _solid(size, palette[i])
            img.save(folder / f"IMG_{i:03d}{suffix}", quality=95)
        return folder

    return _factory


@pytest.fixture
def out_dir(tmp_path):
    folder = tmp_path / "out"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
