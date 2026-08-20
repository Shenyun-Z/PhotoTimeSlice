from typing import Optional

from PIL import Image, ImageDraw
import math

from ._common import ImageSource, ProgressCallback, iter_with_count


def create_circular_band_slice(images: ImageSource, progress_callback: ProgressCallback = None,
                               num_images: Optional[int] = None) -> Image.Image:
    """同心圆环带切片（由内向外）。images 可为列表或生成器（流式）。"""
    it, num_images, first = iter_with_count(images, num_images)
    if num_images == 0:
        return Image.new('RGB', (1, 1))
    img_w, img_h = first.size
    center_x, center_y = img_w // 2, img_h // 2
    result = Image.new('RGB', (img_w, img_h), (0, 0, 0))
    max_radius = min(img_w, img_h) // 2
    min_radius = max(1, max_radius // 20)

    def ring_radius(i):
        # (i+1)/num_images 保证最外圈恰好达到最大半径，避免外圈黑边
        return min_radius + (max_radius - min_radius) * math.sqrt((i + 1) / num_images)

    for i, src_img in enumerate(it):
        radius = ring_radius(i)
        left = center_x - radius
        top = center_y - radius
        right = center_x + radius
        bottom = center_y + radius

        mask = Image.new('L', (img_w, img_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([left, top, right, bottom], fill=255)

        if i > 0:
            prev_radius = ring_radius(i - 1)
            prev_left = center_x - prev_radius
            prev_top = center_y - prev_radius
            prev_right = center_x + prev_radius
            prev_bottom = center_y + prev_radius
            mask_draw.ellipse([prev_left, prev_top, prev_right, prev_bottom], fill=0)

        masked_img = Image.composite(src_img, result, mask)
        result.paste(masked_img, (0, 0))

        if progress_callback:
            progress_callback(i + 1)

    return result
