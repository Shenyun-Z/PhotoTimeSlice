from typing import Optional

from PIL import Image, ImageDraw
import numpy as np

from ._common import ImageSource, ProgressCallback, iter_with_count


def _resolve_sample_origin(position, max_offset):
    """同一位置模式下，将 left/center/right 或 0.0~1.0 数值转换为取样起点"""
    if position == "left":
        return 0.0
    if position == "right":
        return float(max_offset)
    if position == "center":
        return float(max_offset) / 2.0
    try:
        pos = float(position)
        pos = max(0.0, min(1.0, pos))
        return float(max_offset) * pos
    except (TypeError, ValueError):
        return float(max_offset) / 2.0


def _remap_horizontal_strip(strip_arr, left, right, img_w, img_h):
    """
    将宽度为 strip_w 的竖条（strip_arr: H x strip_w x 3）逐行水平重采样到
    S 形区域。left/right 为每行的区域左右边界（浮点数组，长度 H）。
    返回 (H x W x 3 数组, H x W mask)：区域外为 0，mask 与填充范围精确一致。
    """
    strip_w = strip_arr.shape[1]
    out = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    for y in range(img_h):
        l = left[y]
        r = right[y]
        w = r - l
        if w <= 0:
            continue
        x0 = max(0, int(np.floor(l)))
        x1 = min(img_w, int(np.ceil(r)))
        if x1 <= x0:
            continue
        xs = np.arange(x0, x1, dtype=np.float64)
        src = (xs - l) * (strip_w / w)
        src = np.clip(src.astype(np.int64), 0, strip_w - 1)
        out[y, x0:x1] = strip_arr[y, src]
        mask[y, x0:x1] = 255
    return out, mask


def create_vertical_s_slice(images: ImageSource, position: str = "center", linear: bool = False,
                            progress_callback: ProgressCallback = None,
                            num_images: Optional[int] = None) -> Image.Image:
    """
    垂直 S 型曲线时间切片（无缝、无黑缝）。

    linear=True （不同位置，经典 S 形）：区域 i 显示照片 i 中与区域 i 位置对应
        的内容（取样位置随区域移动），区域边界为 S 形曲线。
    linear=False（同一位置）：所有照片都从 position 指定的同一横向位置裁切竖条，
        再按 S 形曲线作为区域边界拼接（位置选项左/中/右生效）。

    算法：n 条等距 S 形分隔线将整图在水平方向划分为 n 个区域，第 i 个区域填充
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

    strip_w = img_w / n
    # S 形摆幅：始终保留（< 半条带宽，确保相邻分隔线不交叉）
    amp = strip_w * 0.45

    ys = np.linspace(0, img_h, 200)

    def seam(k, yv):
        if k <= 0:
            return np.zeros_like(yv)
        if k >= n:
            return np.full_like(yv, float(img_w))
        base = (k / n) * img_w
        return base + amp * np.sin(np.pi * (yv / img_h - 0.5))

    # 同一位置模式的取样起点（仅 linear=False 使用）
    sample_x = _resolve_sample_origin(position, img_w - strip_w)

    for i, img in enumerate(it):
        # 两侧各向相邻条带重叠 1 像素：各条带区间在数学上连续覆盖整图，
        # 彻底消除接缝处光栅化可能产生的亚像素黑缝（后续条带会覆盖重叠区，视觉无偏移）
        left = seam(i, ys) - 1.0
        right = seam(i + 1, ys) + 1.0

        # S 形区域 mask（两种模式共用）
        pts = [(float(left[j]), float(ys[j])) for j in range(len(ys))]
        pts += [(float(right[len(ys) - 1 - j]), float(ys[len(ys) - 1 - j])) for j in range(len(ys))]
        mask = Image.new('L', (img_w, img_h), 0)
        ImageDraw.Draw(mask).polygon(pts, fill=255)

        if linear:
            # 不同位置（经典 S 形）：区域 i 显示照片 i 的对应位置内容
            result.paste(img, (0, 0), mask)
        else:
            # 同一位置：从照片 i 裁出固定源位置的竖条，逐行重采样到 S 形区域。
            # region_img 已按逐行精确边界裁剪（区域外为黑），其边界与 S 形 mask
            # 存在 ±1px 多边形舍入偏差，若再叠加 mask 会把黑区带进来，故直接 paste。
            x0 = int(sample_x)
            x1 = int(sample_x + strip_w)
            strip = img.crop((x0, 0, x1, img_h))
            strip_arr = np.asarray(strip.convert('RGB'), dtype=np.uint8)
            y_full = np.arange(img_h, dtype=np.float64)
            left_full = seam(i, y_full)
            right_full = seam(i + 1, y_full)
            # 精确 mask 与重采样填充范围完全一致（逐行 seam 计算），
            # 避免 200 点多边形 mask 的 ±1px 舍入偏差带出区域外黑像素
            region_arr, region_mask = _remap_horizontal_strip(strip_arr, left_full, right_full, img_w, img_h)
            region_img = Image.fromarray(region_arr, 'RGB')
            result.paste(region_img, (0, 0), Image.fromarray(region_mask, 'L'))

        if progress_callback:
            progress_callback(i + 1)

    return result
