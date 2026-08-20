from typing import Optional

from PIL import Image

from ._common import ImageSource, ProgressCallback, iter_with_count


def create_vertical_slice(images: ImageSource, position: str, linear: bool = False,
                          progress_callback: ProgressCallback = None,
                          num_images: Optional[int] = None) -> Image.Image:
    """垂直条带切片。images 可为列表或生成器（流式），配合 num_images 使用。"""
    it, num_images, first = iter_with_count(images, num_images)
    if num_images == 0:
        return Image.new('RGB', (1, 1))
    img_w, img_h = first.size
    result = Image.new('RGB', (img_w, img_h))
    step = img_w / num_images

    for i, img in enumerate(it):
        x0 = int(round(i * step))
        x1 = int(round((i + 1) * step))
        strip_w = max(1, x1 - x0)

        if linear:
            crop_x = int(i * (img_w - strip_w) / (num_images - 1)) if num_images > 1 else 0
        else:
            if position == "left":
                crop_x = 0
            elif position == "right":
                crop_x = img_w - strip_w
            elif position == "center":
                crop_x = (img_w - strip_w) // 2
            else:
                try:
                    pos = float(position)
                    crop_x = int((img_w - strip_w) * pos)
                except ValueError:
                    crop_x = (img_w - strip_w) // 2

        crop_x = max(0, min(crop_x, img_w - strip_w))
        strip = img.crop((crop_x, 0, crop_x + strip_w, img_h))
        result.paste(strip, (x0, 0))

        if progress_callback:
            progress_callback(i + 1)

    return result
