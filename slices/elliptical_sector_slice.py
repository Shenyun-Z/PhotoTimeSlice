from PIL import Image, ImageDraw
import sys

# 检查是否为打包环境
is_frozen = getattr(sys, 'frozen', False)

def create_elliptical_sector_slice(images, linear=False):
    img = images[0]
    img_w, img_h = img.size
    center_x, center_y = img_w // 2, img_h // 2
    a = img_w // 2
    b = img_h // 2
    num_images = len(images)
    result = Image.new('RGB', (img_w, img_h), (0, 0, 0))
    angle_step = 360 / num_images

    if not is_frozen:
        print("生成椭圆形扇形切片...", end="", flush=True)
    for i, src_img in enumerate(images):
        start_angle = i * angle_step
        end_angle = (i + 1) * angle_step
        if not linear:
            current_a = a
            current_b = b
        else:
            scale = i / (num_images - 1) if num_images > 1 else 1.0
            current_a = a * scale
            current_b = b * scale

        ellipse_bbox = [
            center_x - current_a, center_y - current_b,
            center_x + current_a, center_y + current_b
        ]

        mask = Image.new('L', (img_w, img_h))
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.pieslice(ellipse_bbox, start_angle, end_angle, fill=255)
        masked_img = Image.composite(src_img, result, mask)
        result.paste(masked_img, (0, 0))

    if not is_frozen:
        print("完成")
    return result