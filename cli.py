import os
from pathlib import Path
from datetime import datetime

from utils import iter_images, get_sorted_image_paths, sanitize_filename, FIT_SCALE_CENTER
from slices import (
    create_vertical_slice,
    create_horizontal_slice,
    create_circular_sector_slice,
    create_elliptical_sector_slice,
    create_elliptical_band_slice,
    create_rectangular_band_slice,
    create_circular_band_slice,
    create_vertical_s_slice,
    create_horizontal_s_slice
)
from i18n import Translator


def get_translator(lang):
    """获取翻译器"""
    translator = Translator(lang)
    return translator


def generate_output_filename(base_name, include_timestamp, include_slice_type, slice_type, extension, timestamp_str=None, lang='en'):
    """生成输出文件名（切片类型名称随语言切换）"""
    translator = get_translator(lang)
    parts = [sanitize_filename(base_name)]

    if include_timestamp:
        timestamp = timestamp_str if timestamp_str else datetime.now().strftime("%Y%m%d_%H%M%S")
        parts.append(timestamp)

    if include_slice_type:
        # 切片类型简称（经翻译器转换，支持中英文）
        type_map = {
            "vertical": "垂直",
            "horizontal": "水平",
            "circular_sector": "圆形扇形",
            "elliptical_sector": "椭圆形扇形",
            "elliptical_band": "椭圆形环带",
            "rectangular_band": "矩形环带",
            "circular_band": "圆形环带",
            "vertical_s": "垂直S型",
            "horizontal_s": "水平S型"
        }
        type_name = translator.tr(type_map.get(slice_type, slice_type))
        parts.append(type_name)

    # 用"-"连接所有部分
    filename = "-".join(filter(None, parts))

    # 添加扩展名
    if not extension.startswith('.'):
        extension = '.' + extension

    return f"{filename}{extension}"


def run_timeslice(input_dir, output_dir, slice_type, position="center", linear=False, reverse=False,
                  sort_by='name', output_basename='timeslice', include_timestamp=False,
                  include_slice_type=False, extension='jpg', progress_callback=None,
                  lang='en', timestamp_source='composition',
                  fit_strategy=FIT_SCALE_CENTER, fill_color=(0, 0, 0)):
    """
    生成时间切片（纯 API 核心调度）。

    采用流式加载：逐张读取、适配并释放图片，避免一次性将所有图片载入内存。
    尺寸适配策略由 fit_strategy 指定（见 utils.FIT_* 常量）：
      - scale_center：缩放居中补边（默认）
      - crop_center ：缩放后居中裁切
      - stretch     ：拉伸铺满
      - none        ：尺寸不一致时报错
    """
    translator = get_translator(lang)

    # 确保输入目录存在
    if not os.path.exists(input_dir):
        raise Exception(f"{translator.tr('输入目录不存在:')} {input_dir}")

    # 创建输出目录
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise Exception(f"{translator.tr('无法创建输出目录:')} {str(e)}")

    # 检查输出目录是否可写
    if not os.access(output_dir, os.W_OK):
        raise Exception(f"{translator.tr('输出目录不可写:')} {output_dir}")

    # 计算时间戳（若需要）
    timestamp_str = None
    if include_timestamp:
        from utils import compute_timestamp
        timestamp_str = compute_timestamp(timestamp_source, input_dir, sort_by, reverse)
        if timestamp_str is None:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 生成输出文件名
    output_filename = generate_output_filename(
        base_name=output_basename,
        include_timestamp=include_timestamp,
        include_slice_type=include_slice_type,
        slice_type=slice_type,
        extension=extension,
        timestamp_str=timestamp_str,
        lang=lang
    )

    output_path = Path(output_dir) / output_filename

    # 避免同名文件被静默覆盖（#9）
    if output_path.exists():
        stem = output_path.stem
        suffix = output_path.suffix
        counter = 1
        while output_path.exists():
            output_path = Path(output_dir) / f"{stem}_{counter}{suffix}"
            counter += 1

    # 先取图片路径列表以确定总数（不加载像素），供流式切片使用
    try:
        image_paths = get_sorted_image_paths(input_dir, sort_by, reverse)
    except Exception as e:
        raise Exception(f"{translator.tr('加载图片失败:')} {str(e)}")

    if not image_paths:
        raise Exception(translator.tr("输入目录中没有找到图片"))

    num_images = len(image_paths)

    # 进度回调
    if progress_callback:
        progress_callback(0)

    # 生成切片（流式：逐张加载、适配、处理、释放）
    result = None
    try:
        image_iter = iter_images(input_dir, sort_by, reverse, fit_strategy, fill_color, lang)

        if slice_type == "vertical":
            result = create_vertical_slice(image_iter, position, linear, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "horizontal":
            result = create_horizontal_slice(image_iter, position, linear, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "circular_sector":
            result = create_circular_sector_slice(image_iter, linear, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "elliptical_sector":
            result = create_elliptical_sector_slice(image_iter, linear, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "elliptical_band":
            result = create_elliptical_band_slice(image_iter, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "rectangular_band":
            result = create_rectangular_band_slice(image_iter, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "circular_band":
            result = create_circular_band_slice(image_iter, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "vertical_s":
            result = create_vertical_s_slice(image_iter, position, linear, progress_callback=progress_callback, num_images=num_images)
        elif slice_type == "horizontal_s":
            result = create_horizontal_s_slice(image_iter, position, linear, progress_callback=progress_callback, num_images=num_images)
        else:
            raise ValueError(f"{translator.tr('未知切片类型:')} {slice_type}")

        # 检查 result 是否为 None
        if result is None:
            raise Exception(f"{translator.tr('切片生成函数返回了 None，可能是内存不足或算法错误')}")

    except Exception as e:
        # 添加详细错误信息
        import traceback
        error_details = traceback.format_exc()
        raise Exception(f"{translator.tr('生成切片失败:')}\n{str(e)}\n{error_details}")

    # 保存图片
    try:
        # 根据扩展名选择保存参数
        if extension.lower() in ['jpg', 'jpeg']:
            result.save(output_path, "JPEG", quality=100, subsampling=0)
        elif extension.lower() == 'png':
            result.save(output_path, "PNG", optimize=True)
        elif extension.lower() == 'webp':
            result.save(output_path, "WEBP", quality=95)
        else:
            # 默认使用JPEG
            result.save(output_path, "JPEG", quality=100, subsampling=0)
    except Exception as e:
        raise Exception(f"{translator.tr('保存图片失败:')} {str(e)}")

    return str(output_path)
