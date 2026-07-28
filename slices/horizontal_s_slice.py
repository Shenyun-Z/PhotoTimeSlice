from PIL import Image, ImageDraw
import numpy as np


def create_horizontal_s_slice(images, position="center", linear=False, progress_callback=None):
    """
    创建水平S型曲线时间切片 - 完美S形无缝拼接

    linear=False（同一位置）：每张照片都从同一个固定位置（由 position 决定：top/center/bottom）裁切后拼接，
        即所有照片取同一位置。
    linear=True（不同位置）：每张照片从其自身对应的横向条带位置裁切后拼接，
        保留经典时间切片的 S 形过渡（取不同位置）。
    """
    img_w, img_h = images[0].size
    num_images = len(images)
    result = Image.new('RGB', (img_w, img_h))
    if num_images == 0:
        return result
    strip_height = img_h / num_images

    for i, img in enumerate(images):
        # 当前条带的目标位置（结果图中固定占用的横向区域，保证无缝覆盖）
        y0 = i * strip_height
        y1 = (i + 1) * strip_height
        half = strip_height / 2

        # 线性模式（不同位置）：每张照片从其自身对应的横向条带位置裁切（经典 S 型时间切片）
        # 非线性的同一位置模式：所有照片都从同一个固定位置（由 position 决定）裁切
        if linear:
            src_center_y = y0 + half
        else:
            if position == "top":
                src_center_y = half
            elif position == "bottom":
                src_center_y = img_h - half
            elif position == "center":
                src_center_y = img_h / 2
            else:
                try:
                    pos = float(position)
                    src_center_y = (img_h - strip_height) * pos + half
                except (ValueError, TypeError):
                    src_center_y = img_h / 2

        # 创建蒙版 - 几何固定在当前条带内，保证结果图无缝覆盖
        mask = Image.new('L', (img_w, img_h), 0)
        draw = ImageDraw.Draw(mask)

        # 蒙版 S 形控制点 - 以目标条带中心为基准
        dst_center = y0 + half
        start_point = (0, dst_center)
        control1 = (img_w / 3, dst_center - half)
        control2 = (2 * img_w / 3, dst_center + half)
        end_point = (img_w, dst_center)

        # 计算曲线路径点
        points = []
        t_values = np.linspace(0, 1, 200)
        for t in t_values:
            x = (1 - t) ** 3 * start_point[0] + 3 * (1 - t) ** 2 * t * control1[0] + 3 * (1 - t) * t ** 2 * control2[0] + t ** 3 * end_point[0]
            y = (1 - t) ** 3 * start_point[1] + 3 * (1 - t) ** 2 * t * control1[1] + 3 * (1 - t) * t ** 2 * control2[1] + t ** 3 * end_point[1]
            points.append((x, y))

        # 创建S形路径
        path_points = []

        # 左边沿线 - 完全匹配S形
        for x, y in points:
            path_points.append((x, y - half))

        # 右边沿线 - 反向顺序保持连续性
        for x, y in reversed(points):
            path_points.append((x, y + half))

        # 闭合路径
        if path_points:
            path_points.append(path_points[0])

        # 填充S形路径 - 这将创建完美的S形蒙版
        if path_points:
            draw.polygon(path_points, fill=255)

        # 处理边界情况 - 对于第一张和最后一张图片
        if i == 0:
            # 上边填充
            draw.polygon([(0, 0), (img_w, 0), (img_w, y0), (0, y0)], fill=255)
        elif i == num_images - 1:
            # 下边填充
            draw.polygon([(0, y1), (img_w, y1), (img_w, img_h), (0, img_h)], fill=255)

        # 从源图以 src_center_y 为中心裁切条带区域，再平移到结果图的当前条带
        src_y0 = max(0, int(round(src_center_y - half)))
        src_y1 = min(img_h, int(round(src_center_y + half)))
        if src_y1 <= src_y0:
            src_y0 = max(0, src_y1 - 1)
        src_region = img.crop((0, src_y0, img_w, src_y1))
        target_h = int(round(y1 - y0))
        if src_region.height != target_h:
            src_region = src_region.resize((img_w, target_h))

        # 将处理好的S形部分粘贴到结果图的当前条带
        band_mask = mask.crop((0, int(round(y0)), img_w, int(round(y1))))
        result.paste(src_region, (0, int(round(y0))), band_mask)

        if progress_callback:
            progress_callback(i + 1)

    return result
