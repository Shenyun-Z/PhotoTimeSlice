from itertools import chain


def iter_with_count(images, num_images=None):
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
