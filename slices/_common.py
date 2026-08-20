from itertools import chain
from typing import Callable, Iterable, Iterator, List, Optional, Tuple, Union

from PIL import Image

# 图片输入：列表 / 元组 / 任意迭代器（生成器流式输入）
ImageSource = Union[Iterable[Image.Image], List[Image.Image]]
# 进度回调：处理完第 current 张时调用
ProgressCallback = Optional[Callable[[int], None]]


def iter_with_count(images: ImageSource, num_images: Optional[int] = None
                    ) -> Tuple[Iterator[Image.Image], int, Optional[Image.Image]]:
    """
    将图片输入规范化为统一的迭代模式。

    兼容：
      - 列表 / 元组（可通过 len 获取数量）
      - 生成器 / 任意迭代器（流式，需由调用方通过 num_images 提供数量，
        否则会收集全部元素以确定数量，失去流式意义）

    返回 (iterator, num_images, first)：
      - iterator 包含全部图片（first 在首）
      - num_images 为图片总数
      - first 为第一张图片（用于取基准尺寸）
    """
    it = iter(images)
    try:
        first = next(it)
    except StopIteration:
        return it, 0, None

    if num_images is None:
        if hasattr(images, '__len__'):
            num_images = len(images)
        else:
            rest = list(it)
            num_images = 1 + len(rest)
            it = chain([first], rest)

    return chain([first], it), num_images, first
