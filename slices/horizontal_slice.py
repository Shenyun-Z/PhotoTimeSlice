from PIL import Image, ImageDraw
import sys

# 检查是否为打包环境
is_frozen = getattr(sys, 'frozen', False)

def create_horizontal_slice(images, position, linear=False):
    img_w, img_h = images[0].size
    num_images = len(images)
    result = Image.new('RGB', (img_w, img_h))
    strip_height = max(1, img_h // num_images)

    if not is_frozen:
        print("生成横向切片...", end="", flush=True)
    for i, img in enumerate(images):
        if linear:
            crop_y = int(i * (img_h - strip_height) / (num_images - 1)) if num_images > 1 else 0
        else:
            if position == "top":
                crop_y = 0
            elif position == "bottom":
                crop_y = img_h - strip_height
            elif position == "center":
                crop_y = (img_h - strip_height) // 2
            else:
                try:
                    pos = float(position)
                    crop_y = int((img_h - strip_height) * pos)
                except ValueError:
                    crop_y = (img_h - strip_height) // 2

        paste_y = i * strip_height
        strip = img.crop((0, crop_y, img_w, crop_y + strip_height))

        if strip.height < strip_height:
            strip = strip.resize((img_w, strip_height))
        elif strip.height > strip_height:
            strip = strip.crop((0, 0, img_w, strip_height))

        result.paste(strip, (0, paste_y))

    if not is_frozen:
        print("完成")
    return result