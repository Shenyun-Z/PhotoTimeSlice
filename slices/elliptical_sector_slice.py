from PIL import Image, ImageDraw

from ._common import iter_with_count


def create_elliptical_sector_slice(images, linear=False, progress_callback=None, num_images=None):
    """椭圆形 360° 等分扇形切片。images 可为列表或生成器（流式）。"""
    it, num_images, first = iter_with_count(images, num_images)
    if num_images == 0:
        return Image.new('RGB', (1, 1))
    img_w, img_h = first.size
    center_x, center_y = img_w // 2, img_h // 2
    a = img_w // 2
    b = img_h // 2
    result = Image.new('RGB', (img_w, img_h), (0, 0, 0))
    angle_step = 360 / num_images

    for i, src_img in enumerate(it):
        start_angle = i * angle_step
        end_angle = (i + 1) * angle_step
        if not linear:
            current_a = a
            current_b = b
        else:
            # 线性模式：椭圆从最小逐步增长到最大，保证第 1 张也可见
            scale = (i + 1) / num_images if num_images > 1 else 1.0
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

        if progress_callback:
            progress_callback(i + 1)

    return result
