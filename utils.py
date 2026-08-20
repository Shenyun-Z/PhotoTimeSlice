import re
import sys
import os
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union
from PIL import Image
from datetime import datetime
from i18n import Translator

# 判断是否为打包环境
is_frozen = getattr(sys, 'frozen', False)

# 文件名非法字符（Windows：\ / : * ? " < > | 及控制字符）
ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')

# Windows 保留设备名，单独作为文件名时保存会失败（#3）
WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}


def sanitize_filename(name: str) -> str:
    """过滤文件名中的非法字符，返回安全的基础名称（空时回退为 timeslice）"""
    name = ILLEGAL_FILENAME_CHARS.sub('_', (name or '').strip())
    name = name.strip('. ')
    # 过滤 Windows 保留设备名（如 CON/PRN/AUX/NUL/COM1/LPT1 等），避免保存失败（#3）
    stem = name.split('.', 1)[0] if name else ''
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        name = f"{name}_"
    return name or "timeslice"


def get_base_path() -> str:
    """获取正确的基础路径（兼容开发环境和打包环境）"""
    if is_frozen:
        # 如果是打包的exe，使用临时解压目录
        return os.path.dirname(sys.executable)
    else:
        # 如果是开发环境，使用当前文件目录
        return os.path.dirname(os.path.abspath(__file__))


def natural_sort_key(s: str, _nsre=re.compile('([0-9]+)')) -> List[Union[int, str]]:
    """Windows文件自然排序"""
    return [int(text) if text.isdigit() else text.lower()
            for text in _nsre.split(str(s))]


def get_file_creation_time(path: Union[str, Path]) -> float:
    """获取文件创建时间"""
    try:
        return os.path.getctime(path)
    except:
        return os.path.getmtime(path)


def get_file_modification_time(path: Union[str, Path]) -> float:
    """获取文件修改时间"""
    return os.path.getmtime(path)


# 支持的图片格式（glob 通配）
IMAGE_EXTENSIONS = [
    "*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff",
    "*.nef", "*.dng", "*.cr2", "*.cr3", "*.arw", "*.raf", "*.orf", "*.rw2"
]

# RAW 格式后缀（需 rawpy 支持）
RAW_SUFFIXES = {'.nef', '.dng', '.cr2', '.cr3', '.arw', '.raf', '.orf', '.rw2'}

# 尺寸适配策略
FIT_SCALE_CENTER = 'scale_center'   # 保持比例缩放 + 居中补边（默认）
FIT_CROP_CENTER = 'crop_center'     # 保持比例缩放 + 居中裁切
FIT_STRETCH = 'stretch'             # 拉伸铺满
FIT_NONE = 'none'                   # 不自动适配（尺寸必须一致，否则报错）
FIT_STRATEGIES = (FIT_SCALE_CENTER, FIT_CROP_CENTER, FIT_STRETCH, FIT_NONE)


def open_image_single(path: Union[str, Path], lang: str = 'en') -> Image.Image:
    """打开单张图片（支持 RAW），返回 PIL.Image；失败抛出明确异常"""
    translator = Translator(lang)
    path = Path(path)
    if path.suffix.lower() in RAW_SUFFIXES:
        try:
            import rawpy
            with rawpy.imread(str(path)) as raw:
                rgb = raw.postprocess()
            return Image.fromarray(rgb)
        except ImportError:
            raise ImportError(translator.tr("请安装rawpy库以处理RAW格式: pip install rawpy"))
    try:
        img = Image.open(path)
        img.load()  # 强制读取像素数据，尽早暴露损坏文件
        return img
    except Exception as e:
        raise RuntimeError(f"{translator.tr('无法打开图片')} {path}: {e}")


def fit_image(img: Image.Image, target_size: Tuple[int, int], strategy: str = FIT_SCALE_CENTER,
              fill_color: Tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    """
    将图片适配到目标尺寸。

    策略：
      scale_center：保持宽高比缩放并居中，剩余区域填充 fill_color（不失真、不损失内容）
      crop_center ：保持宽高比缩放后居中裁切，覆盖目标尺寸（不失真、损失边缘内容）
      stretch     ：直接拉伸到目标尺寸（可能变形）
      none        ：尺寸不同时抛出 ValueError（严格一致模式）
    """
    if img.size == target_size:
        return img

    tw, th = target_size
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        raise ValueError(f"非法图片尺寸: {img.size}")

    if strategy == FIT_STRETCH:
        return img.resize((tw, th), Image.LANCZOS)

    if strategy == FIT_CROP_CENTER:
        scale = max(tw / iw, th / ih)
        nw, nh = int(round(iw * scale)), int(round(ih * scale))
        scaled = img.resize((nw, nh), Image.LANCZOS)
        left = max(0, (nw - tw) // 2)
        top = max(0, (nh - th) // 2)
        return scaled.crop((left, top, left + tw, top + th))

    if strategy == FIT_SCALE_CENTER:
        scale = min(tw / iw, th / ih)
        nw, nh = int(round(iw * scale)), int(round(ih * scale))
        scaled = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new('RGB', target_size, fill_color)
        canvas.paste(scaled, ((tw - nw) // 2, (th - nh) // 2))
        return canvas

    if strategy == FIT_NONE:
        raise ValueError(f"图片尺寸 {img.size} 与基准 {target_size} 不一致，且未启用自动适配")

    raise ValueError(f"未知适配策略: {strategy}")


def iter_images(input_dir: Union[str, Path], sort_by: str = 'name', reverse: bool = False,
                fit_strategy: str = FIT_SCALE_CENTER,
                fill_color: Tuple[int, int, int] = (0, 0, 0), lang: str = 'en') -> Iterator[Image.Image]:
    """
    流式加载并适配图片（生成器）。

    以第一张图片为基准尺寸，后续图片按 fit_strategy 自动适配。
    逐张打开 / 处理 / 释放，避免一次性将所有图片载入内存。
    """
    translator = Translator(lang)
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"{translator.tr('输入目录不存在:')} {input_dir}")

    paths = get_sorted_image_paths(input_dir, sort_by, reverse)
    if not paths:
        raise FileNotFoundError(f"{translator.tr('在目录中未找到支持的图片文件')} {input_dir}")

    base_size = None
    for i, path in enumerate(paths):
        img = open_image_single(path, lang)
        if base_size is None:
            base_size = img.size
        else:
            try:
                img = fit_image(img, base_size, fit_strategy, fill_color)
            except Exception as e:
                img.close()
                raise RuntimeError(f"{translator.tr('适配图片失败:')} {path}: {e}")
        yield img


def load_images(input_dir: Union[str, Path], sort_by: str = 'name', reverse: bool = False,
                lang: str = 'en') -> List[Image.Image]:
    """加载目录中的全部图片到列表（一次性载入，兼容性接口；大目录请使用 iter_images）"""
    translator = Translator(lang)
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"{translator.tr('输入目录不存在:')} {input_dir}")

    paths = get_sorted_image_paths(input_dir, sort_by, reverse)
    if not paths:
        raise FileNotFoundError(f"{translator.tr('在目录中未找到支持的图片文件')} {input_dir}")

    images = []
    for path in paths:
        images.append(open_image_single(path, lang))
    return images


def get_sorted_image_paths(input_dir: Union[str, Path], sort_by: str = 'name',
                           reverse: bool = False) -> List[Path]:
    """返回排序后的图片路径列表（不加载图像，用于时间戳计算）"""
    image_extensions = list(IMAGE_EXTENSIONS)

    image_paths = []
    for ext in image_extensions:
        image_paths.extend(Path(input_dir).glob(ext))

    if sort_by == 'name':
        image_paths.sort(key=natural_sort_key)
    elif sort_by == 'created_time':
        image_paths.sort(key=get_file_creation_time)
    elif sort_by == 'modified_time':
        image_paths.sort(key=get_file_modification_time)
    else:
        image_paths.sort(key=natural_sort_key)

    if reverse:
        image_paths = list(reversed(image_paths))

    return image_paths


def get_exif_capture_time(path: Union[str, Path]) -> Optional[datetime]:
    """读取照片 EXIF 拍摄时间，失败返回 None"""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            # Exif 子 IFD：DateTimeOriginal / DateTimeDigitized
            exif_ifd = exif.get_ifd(0x8769)
            dt_str = exif_ifd.get(0x9003) or exif_ifd.get(0x9004)
            if not dt_str:
                # 兜底：主 IFD 的 DateTime 字段
                dt_str = exif.get(0x0132)
            if not dt_str:
                return None
            return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def format_timestamp(dt: datetime) -> str:
    """格式化时间戳为 YYYYMMDD_HHMMSS"""
    return dt.strftime("%Y%m%d_%H%M%S")


def compute_timestamp(source: str, input_dir: str, sort_by: str = 'name',
                      reverse: bool = False) -> Optional[str]:
    """
    根据 source 计算文件名时间戳字符串，无可用照片时返回 None。
    source: first_capture / last_capture / first_modified / last_modified / composition
    """
    if source == 'composition':
        return format_timestamp(datetime.now())

    if not input_dir or not os.path.isdir(input_dir):
        return None

    paths = get_sorted_image_paths(input_dir, sort_by, reverse)
    if not paths:
        return None

    if source in ('first_capture', 'first_modified'):
        target = paths[0]
    else:
        target = paths[-1]

    if source in ('first_capture', 'last_capture'):
        dt = get_exif_capture_time(target)
        if dt is None:
            dt = datetime.fromtimestamp(os.path.getmtime(target))
    else:
        dt = datetime.fromtimestamp(os.path.getmtime(target))

    return format_timestamp(dt)