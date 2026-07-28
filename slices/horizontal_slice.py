from PIL import Image


def create_horizontal_slice(images, position, linear=False, progress_callback=None):
    img_w, img_h = images[0].size
    num_images = len(images)
    result = Image.new('RGB', (img_w, img_h))
    if num_images == 0:
        return result
    step = img_h / num_images

    for i, img in enumerate(images):
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
