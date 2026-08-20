from typing import Optional

from PIL import Image

from ._common import ImageSource, ProgressCallback, iter_with_count


def create_horizontal_slice(images: ImageSource, position: str, linear: bool = False,
                            progress_callback: ProgressCallback = None,
                            num_images: Optional[int] = None) -> Image.Image:
    """水平条带切片。images 可为列表或生成器（流式），配合 num_images 使用。"""
    it, num_images, first = iter_with_count(images, num_images)
    if num_images == 0:
        return Image.new('RGB', (1, 1))
    img_w, img_h = first.size
    result = Image.new('RGB', (img_w, img_h))
    step = img_h / num_images

    for i, img in enumerate(it):
        y0 = int(round(i * step))
        y1 = int(round((i + 1) * step))
        strip_h = max(1, y1 - y0)

        if linear:
            crop_y = int(i * (img_h - strip_h) / (num_images - 1)) if num_images > 1 else 0
        else:
            if position == "top":
                crop_y = 0
            elif position == "bottom":
                crop_y = img_h - strip_h
            elif position == "center":
                crop_y = (img_h - strip_h) // 2
            else:
                try:
                    pos = float(position)
                    crop_y = int((img_h - strip_h) * pos)
                except ValueError:
                    crop_y = (img_h - strip_h) // 2

        crop_y = max(0, min(crop_y, img_h - strip_h))
        strip = img.crop((0, crop_y, img_w, crop_y + strip_h))
        result.paste(strip, (0, y0))

        if progress_callback:
            progress_callback(i + 1)

    return result
