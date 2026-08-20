from typing import Optional

from PIL import Image, ImageDraw
import numpy as np

from ._common import ImageSource, ProgressCallback, iter_with_count


def _resolve_sample_origin(position, max_offset):
    """同一位置模式下，将 top/center/bottom 或 0.0~1.0 数值转换为取样起点"""
    if position == "top":
        return 0.0
    if position == "bottom":
        return float(max_offset)
    if position == "center":
        return float(max_offset) / 2.0
    try:
        pos = float(position)
        pos = max(0.0, min(1.0, pos))
        return float(max_offset) * pos
    except (TypeError, ValueError):
        return float(max_offset) / 2.0


def _remap_vertical_strip(strip_arr, top, bottom, img_w, img_h):
    """
    将高度为 strip_h 的横条（strip_arr: strip_h x W x 3）逐列垂直重采样到
    S 形区域。top/bottom 为每列的区域上下边界（浮点数组，长度 W）。
    返回 (H x W x 3 数组, H x W mask)：区域外为 0，mask 与填充范围精确一致。
    """
    strip_h = strip_arr.shape[0]
    out = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    for x in range(img_w):
        t = top[x]
        b = bottom[x]
        h = b - t
        if h <= 0:
            continue
        y0 = max(0, int(np.floor(t)))
        y1 = min(img_h, int(np.ceil(b)))
        if y1 <= y0:
            continue
        ys = np.arange(y0, y1, dtype=np.float64)
        src = (ys - t) * (strip_h / h)
        src = np.clip(src.astype(np.int64), 0, strip_h - 1)
        out[y0:y1, x] = strip_arr[src, x]
        mask[y0:y1, x] = 255
    return out, mask


def create_horizontal_s_slice(images: ImageSource, position: str = "center", linear: bool = False,
                              progress_callback: ProgressCallback = None,
                              num_images: Optional[int] = None) -> Image.Image:
    """
    水平 S 型曲线时间切片（无缝、无黑缝）。

    linear=True （不同位置，经典 S 形）：区域 i 显示照片 i 中与区域 i 位置对应
        的内容（取样位置随区域移动），区域边界为 S 形曲线。
    linear=False（同一位置）：所有照片都从 position 指定的同一纵向位置裁切横条，
        再按 S 形曲线作为区域边界拼接（位置选项上/中/下生效）。

    算法：n 条等距 S 形分隔线将整图在垂直方向划分为 n 个区域，第 i 个区域填充
    第 i 张照片。相邻区域共用同一条分隔线 -> 精确拼接、零缝隙。
    """
    it, n, first = iter_with_count(images, num_images)
    if n == 0:
        return Image.new('RGB', (1, 1))
    img_w, img_h = first.size
    result = Image.new('RGB', (img_w, img_h))
    if n == 1:
        result.paste(first, (0, 0))
        if progress_callback:
            progress_callback(1)
        return result

    strip_h = img_h / n
    # S 形摆幅：始终保留（< 半条带高，确保相邻分隔线不交叉）
    amp = strip_h * 0.45

    xs = np.linspace(0, img_w, 200)

    def seam(k, xv):
        if k <= 0:
            return np.zeros_like(xv)
        if k >= n:
            return np.full_like(xv, float(img_h))
        base = (k / n) * img_h
        return base + amp * np.sin(np.pi * (xv / img_w - 0.5))

    # 同一位置模式的取样起点（仅 linear=False 使用）
    sample_y = _resolve_sample_origin(position, img_h - strip_h)

    for i, img in enumerate(it):
        # 两侧各向相邻条带重叠 1 像素：各条带区间在数学上连续覆盖整图，
        # 彻底消除接缝处光栅化可能产生的亚像素黑缝（后续条带会覆盖重叠区，视觉无偏移）
        top = seam(i, xs) - 1.0
        bot = seam(i + 1, xs) + 1.0

        # S 形区域 mask（两种模式共用）
        pts = [(float(xs[j]), float(top[j])) for j in range(len(xs))]
        pts += [(float(xs[len(xs) - 1 - j]), float(bot[len(xs) - 1 - j])) for j in range(len(xs))]
        mask = Image.new('L', (img_w, img_h), 0)
        ImageDraw.Draw(mask).polygon(pts, fill=255)

        if linear:
            # 不同位置（经典 S 形）：区域 i 显示照片 i 的对应位置内容
            result.paste(img, (0, 0), mask)
        else:
            # 同一位置：从照片 i 裁出固定源位置的横条，逐列重采样到 S 形区域。
            # region_img 已按逐行精确边界裁剪（区域外为黑），其边界与 S 形 mask
            # 存在 ±1px 多边形舍入偏差，若再叠加 mask 会把黑区带进来，故直接 paste。
            y0 = int(sample_y)
            y1 = int(sample_y + strip_h)
            strip = img.crop((0, y0, img_w, y1))
            strip_arr = np.asarray(strip.convert('RGB'), dtype=np.uint8)
            x_full = np.arange(img_w, dtype=np.float64)
            top_full = seam(i, x_full)
            bot_full = seam(i + 1, x_full)
            # 精确 mask 与重采样填充范围完全一致（逐列 seam 计算），
            # 避免 200 点多边形 mask 的 ±1px 舍入偏差带出区域外黑像素
            region_arr, region_mask = _remap_vertical_strip(strip_arr, top_full, bot_full, img_w, img_h)
            region_img = Image.fromarray(region_arr, 'RGB')
            result.paste(region_img, (0, 0), Image.fromarray(region_mask, 'L'))

        if progress_callback:
            progress_callback(i + 1)

    return result
