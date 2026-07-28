import argparse
import sys
import os
from pathlib import Path
from datetime import datetime

from utils import load_images, sanitize_filename
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

# Windows可执行文件判断
is_frozen = getattr(sys, 'frozen', False)


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
                  lang='en', timestamp_source='composition'):
    """生成时间切片（仅Windows）"""
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

    # 加载图片
    try:
        images = load_images(input_dir, sort_by, reverse)
    except Exception as e:
        raise Exception(f"{translator.tr('加载图片失败:')} {str(e)}")

    if not images:
        raise Exception(translator.tr("输入目录中没有找到图片"))

    # 检查尺寸
    base_size = images[0].size
    for img in images:
        if img.size != base_size:
            raise Exception(translator.tr("所有图片必须具有相同的尺寸"))

    # 进度回调
    if progress_callback:
        progress_callback(0)

    # 在 run_timeslice 函数中修改切片生成部分
    # 生成切片
    result = None
    try:
        if slice_type == "vertical":
            result = create_vertical_slice(images, position, linear, progress_callback=progress_callback)
        elif slice_type == "horizontal":
            result = create_horizontal_slice(images, position, linear, progress_callback=progress_callback)
        elif slice_type == "circular_sector":
            result = create_circular_sector_slice(images, linear, progress_callback=progress_callback)
        elif slice_type == "elliptical_sector":
            result = create_elliptical_sector_slice(images, linear, progress_callback=progress_callback)
        elif slice_type == "elliptical_band":
            result = create_elliptical_band_slice(images, progress_callback=progress_callback)
        elif slice_type == "rectangular_band":
            result = create_rectangular_band_slice(images, progress_callback=progress_callback)
        elif slice_type == "circular_band":
            result = create_circular_band_slice(images, progress_callback=progress_callback)
        elif slice_type == "vertical_s":
            result = create_vertical_s_slice(images, position, linear, progress_callback=progress_callback)
        elif slice_type == "horizontal_s":
            result = create_horizontal_s_slice(images, position, linear, progress_callback=progress_callback)
        else:
            raise ValueError(f"{translator.tr('未知切片类型:')} {slice_type}")

        # 检查 result 是否为 None
        if result is None:
            raise Exception(f"{translator.tr('切片生成函数返回了 None，可能是内存不足或算法错误')}")

    except Exception as e:
        # 添加详细错误信息
        import traceback
        error_details = traceback.format_exc()
        raise Exception(f"{translator.tr('生成切片失败:')}\n{str(e)}\n{error_details}")  # 修改这里

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


def main():
    """CLI主函数（仅Windows）"""
    default_translator = get_translator('en')

    # 参数解析
    parser = argparse.ArgumentParser(
        description=default_translator.tr("时间切片照片生成器（Windows版）"),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-i", "--input",
        default="input",
        help=default_translator.tr("输入文件夹路径（默认为\"input\"）")
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help=default_translator.tr("输出文件夹路径（默认为\"output\"）")
    )
    parser.add_argument(
        "-t", "--type",
        required=True,
        choices=["vertical", "horizontal", "circular_sector",
                 "elliptical_sector", "elliptical_band",
                 "rectangular_band", "circular_band",
                 "vertical_s", "horizontal_s"],
        help=default_translator.tr("切片类型（必需）")
    )
    parser.add_argument(
        "-p", "--position",
        default="center",
        help=default_translator.tr("条带位置：left/center/right/top/bottom 或 0.0-1.0")
    )
    parser.add_argument(
        "-l", "--linear",
        action="store_true",
        help=default_translator.tr("启用线性模式（作用因切片类型而异，详见 README）")
    )
    parser.add_argument(
        "-r", "--reverse",
        action="store_true",
        help=default_translator.tr("逆序排序")
    )
    parser.add_argument(
        "--sort-by",
        default="name",
        choices=["name", "created_time", "modified_time"],
        help=default_translator.tr("排序方式：name/created_time/modified_time")
    )
    parser.add_argument(
        "--output-name",
        default="timeslice",
        help=default_translator.tr("输出文件基础名称")
    )
    parser.add_argument(
        "--include-timestamp",
        action="store_true",
        help=default_translator.tr("在文件名中包含时间戳")
    )
    parser.add_argument(
        "--timestamp-source",
        default="composition",
        choices=["composition", "first_capture", "last_capture", "first_modified", "last_modified"],
        help=default_translator.tr("时间戳来源：composition/first_capture/last_capture/first_modified/last_modified")
    )
    parser.add_argument(
        "--include-slice-type",
        action="store_true",
        help=default_translator.tr("在文件名中包含切片类型")
    )
    parser.add_argument(
        "--extension",
        default="jpg",
        choices=["jpg", "jpeg", "png", "webp"],
        help=default_translator.tr("输出文件扩展名")
    )
    parser.add_argument(
        "-lang", "--language",
        default="en",
        choices=["en", "zh_CN"],
        help=default_translator.tr("语言（en/zh_CN）")
    )

    args = parser.parse_args()
    translator = get_translator(args.language)

    try:
        # 生成切片
        output_path = run_timeslice(
            input_dir=args.input,
            output_dir=args.output,
            slice_type=args.type,
            position=args.position,
            linear=args.linear,
            reverse=args.reverse,
            sort_by=args.sort_by,
            output_basename=args.output_name,
            include_timestamp=args.include_timestamp,
            include_slice_type=args.include_slice_type,
            extension=args.extension,
            lang=args.language,
            timestamp_source=args.timestamp_source
        )

        # 输出结果
        print(translator.tr('处理完成!'))
        print(f"{translator.tr('时间切片已保存至:')} {output_path}")

        # Windows自动打开（可选）
        if is_frozen:
            # 在打包环境中，跳过交互式提示
            try:
                os.startfile(output_path)
            except:
                pass
        else:
            response = input(f"{translator.tr('是否打开生成的图片？(y/n)')} ")
            if response.lower() == 'y':
                try:
                    os.startfile(output_path)
                except:
                    print(f"{translator.tr('无法打开图片:')} {output_path}")

    except Exception as e:
        print(f"{translator.tr('错误:')} {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()