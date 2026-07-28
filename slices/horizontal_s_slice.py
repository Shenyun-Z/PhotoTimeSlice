from PIL import Image, ImageDraw
import numpy as np


def create_horizontal_s_slice(images, position="center", linear=False, progress_callback=None):
    """
    创建水平 S 型曲线时间切片（无缝、无黑缝）。

    linear=False（同一位置）：各照片按直线横向条带拼接（等价于普通水平切片）。
    linear=True（不同位置）：相邻照片之间以 S 形曲线分隔，形成经典 S 型过渡。

    算法：用 n 条等距 S 形分隔线将整图在垂直方向划分为 n 个区域，
    第 i 个区域填充第 i 张照片。相邻区域共用同一条分隔线 -> 精确拼接、零缝隙。
    """
    img_w, img_h = images[0].size
    n = len(images)
    result = Image.new('RGB', (img_w, img_h))
    if n == 0:
        return result
    if n == 1:
        result.paste(images[0], (0, 0))
        if progress_callback:
            progress_callback(1)
        return result

    strip_h = img_h / n
    # S 形摆幅：必须小于半条带高，确保相邻分隔线不交叉
    amp = strip_h * 0.45 if linear else 0.0

    xs = np.linspace(0, img_w, 200)

    def seam(k, xv):
        if k <= 0:
            return np.zeros_like(xv)
        if k >= n:
            return np.full_like(xv, float(img_h))
        base = (k / n) * img_h
        return base + amp * np.sin(np.pi * (xv / img_w - 0.5))

    for i in range(n):
        # 两侧各向相邻条带重叠 1 像素：各条带区间在数学上连续覆盖整图，
        # 彻底消除接缝处光栅化可能产生的亚像素黑缝（后续条带会覆盖重叠区，视觉无偏移）
        top = seam(i, xs) - 1.0
        bot = seam(i + 1, xs) + 1.0
        pts = [(float(xs[j]), float(top[j])) for j in range(len(xs))]
        pts += [(float(xs[len(xs) - 1 - j]), float(bot[len(xs) - 1 - j])) for j in range(len(xs))]
        mask = Image.new('L', (img_w, img_h), 0)
        ImageDraw.Draw(mask).polygon(pts, fill=255)
        result.paste(images[i], (0, 0), mask)
        if progress_callback:
            progress_callback(i + 1)

    return result
