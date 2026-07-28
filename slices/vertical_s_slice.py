from PIL import Image, ImageDraw
import numpy as np


def create_vertical_s_slice(images, position="center", linear=False, progress_callback=None):
    """
    创建垂直S型曲线时间切片 - 完美S形无缝拼接

    linear=False（同一位置）：每张照片都从同一个固定位置（由 position 决定：left/center/right）裁切后拼接，
        即所有照片取同一位置。
    linear=True（不同位置）：每张照片从其自身对应的竖向条带位置裁切后拼接，
        保留经典时间切片的 S 形过渡（取不同位置）。
    """
    img_w, img_h = images[0].size
    num_images = len(images)
    result = Image.new('RGB', (img_w, img_h))
    if num_images == 0:
        return result
    strip_width = img_w / num_images

    for i, img in enumerate(images):
        # 当前条带的目标位置（结果图中固定占用的竖向区域，保证无缝覆盖）
        x0 = i * strip_width
        x1 = (i + 1) * strip_width
        half = strip_width / 2

        # 线性模式（不同位置）：每张照片从其自身对应的竖向条带位置裁切（经典 S 型时间切片）
        # 非线性的同一位置模式：所有照片都从同一个固定位置（由 position 决定）裁切
        if linear:
            src_center_x = x0 + half
        else:
            if position == "left":
                src_center_x = half
            elif position == "right":
                src_center_x = img_w - half
            elif position == "center":
                src_center_x = img_w / 2
            else:
                try:
                    pos = float(position)
                    src_center_x = (img_w - strip_width) * pos + half
                except (ValueError, TypeError):
                    src_center_x = img_w / 2

        # 创建蒙版 - 几何固定在当前条带内，保证结果图无缝覆盖
        mask = Image.new('L', (img_w, img_h), 0)
        draw = ImageDraw.Draw(mask)

        # 蒙版 S 形控制点 - 以目标条带中心为基准
        dst_center = x0 + half
        start_point = (dst_center, 0)
        control1 = (dst_center - half, img_h / 3)
        control2 = (dst_center + half, 2 * img_h / 3)
        end_point = (dst_center, img_h)

        # 计算曲线路径点
        points = []
        t_values = np.linspace(0, 1, 200)
        for t in t_values:
            x = (1 - t) ** 3 * start_point[0] + 3 * (1 - t) ** 2 * t * control1[0] + 3 * (1 - t) * t ** 2 * control2[0] + t ** 3 * end_point[0]
            y = (1 - t) ** 3 * start_point[1] + 3 * (1 - t) ** 2 * t * control1[1] + 3 * (1 - t) * t ** 2 * control2[1] + t ** 3 * end_point[1]
            points.append((x, y))

        # 创建S形路径
        path_points = []

        # 上边沿线 - 完全匹配S形
        for x, y in points:
            path_points.append((x + half, y))

        # 下边沿线 - 反向顺序保持连续性
        for x, y in reversed(points):
            path_points.append((x - half, y))

        # 闭合路径
        if path_points:
            path_points.append(path_points[0])

        # 填充S形路径 - 这将创建完美的S形蒙版
        if path_points:
            draw.polygon(path_points, fill=255)

        # 处理边界情况 - 对于第一张和最后一张图片
        if i == 0:
            # 左侧填充
            draw.polygon([(0, 0), (x0, 0), (x0, img_h), (0, img_h)], fill=255)
        elif i == num_images - 1:
            # 右侧填充
            draw.polygon([(x1, 0), (img_w, 0), (img_w, img_h), (x1, img_h)], fill=255)

        # 从源图以 src_center_x 为中心裁切条带区域，再平移到结果图的当前条带
        src_x0 = max(0, int(round(src_center_x - half)))
        src_x1 = min(img_w, int(round(src_center_x + half)))
        if src_x1 <= src_x0:
            src_x0 = max(0, src_x1 - 1)
        src_region = img.crop((src_x0, 0, src_x1, img_h))
        target_w = int(round(x1 - x0))
        if src_region.width != target_w:
            src_region = src_region.resize((target_w, img_h))

        # 将处理好的S形部分粘贴到结果图的当前条带
        band_mask = mask.crop((int(round(x0)), 0, int(round(x1)), img_h))
        result.paste(src_region, (int(round(x0)), 0), band_mask)

        if progress_callback:
            progress_callback(i + 1)

    return result
