from PIL import Image, ImageDraw
import sys

# 检查是否为打包环境
is_frozen = getattr(sys, 'frozen', False)

import math

def create_elliptical_band_slice(images):
    img = images[0]
    img_w, img_h = img.size
    center_x, center_y = img_w // 2, img_h // 2
    num_images = len(images)
    max_size = max(img_w, img_h)
    min_size = max_size // 20
    result = Image.new('RGB', (img_w, img_h), (0, 0, 0))
    size_step = (max_size - min_size) / math.sqrt(num_images)

    if not is_frozen:
        print("生成椭圆形环带切片...", end="", flush=True)
    for i in range(num_images):
        size = min_size + math.sqrt(i) * size_step
        size = min(size, max_size)
        width = size * (img_w / max_size)
        height = size * (img_h / max_size)
        left = center_x - width // 2
        top = center_y - height // 2
        right = center_x + width // 2
        bottom = center_y + height // 2

        mask = Image.new('L', (img_w, img_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse([left, top, right, bottom], fill=255)

        if i > 0:
            prev_size = min_size + math.sqrt(i - 1) * size_step
            prev_width = prev_size * (img_w / max_size)
            prev_height = prev_size * (img_h / max_size)
            prev_left = center_x - prev_width // 2
            prev_top = center_y - prev_height // 2
            prev_right = center_x + prev_width // 2
            prev_bottom = center_y + prev_height // 2
            mask_draw.ellipse([prev_left, prev_top, prev_right, prev_bottom], fill=0)

        masked_img = Image.composite(images[i], result, mask)
        result.paste(masked_img, (0, 0))

    if not is_frozen:
        print("完成")
    return result