import re
import sys
import os
from pathlib import Path
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


def sanitize_filename(name):
    """过滤文件名中的非法字符，返回安全的基础名称（空时回退为 timeslice）"""
    name = ILLEGAL_FILENAME_CHARS.sub('_', (name or '').strip())
    name = name.strip('. ')
    # 过滤 Windows 保留设备名（如 CON/PRN/AUX/NUL/COM1/LPT1 等），避免保存失败（#3）
    stem = name.split('.', 1)[0] if name else ''
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        name = f"{name}_"
    return name or "timeslice"


def get_base_path():
    """获取正确的基础路径（兼容开发环境和打包环境）"""
    if is_frozen:
        # 如果是打包的exe，使用临时解压目录
        return os.path.dirname(sys.executable)
    else:
        # 如果是开发环境，使用当前文件目录
        return os.path.dirname(os.path.abspath(__file__))


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    """Windows文件自然排序"""
    return [int(text) if text.isdigit() else text.lower()
            for text in _nsre.split(str(s))]


def get_file_creation_time(path):
    """获取文件创建时间"""
    try:
        return os.path.getctime(path)
    except:
        return os.path.getmtime(path)


def get_file_modification_time(path):
    """获取文件修改时间"""
    return os.path.getmtime(path)


def load_images(input_dir, sort_by='name', reverse=False, lang='en'):
    """加载Windows目录中的图片，支持多种排序方式"""
    translator = Translator(lang)
    # 确保输入目录存在
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"{translator.tr('输入目录不存在:')} {input_dir}")

    # 支持的图片格式
    image_extensions = [
        "*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff",
        "*.nef", "*.dng", "*.cr2", "*.cr3", "*.arw", "*.raf", "*.orf", "*.rw2"
    ]

    # 遍历目录
    image_paths = []
    for ext in image_extensions:
        image_paths.extend(Path(input_dir).glob(ext))

    if not image_paths:
        raise FileNotFoundError(f"{translator.tr('在目录中未找到支持的图片文件')} {input_dir}")

    # 根据排序规则排序
    if sort_by == 'name':
        image_paths.sort(key=natural_sort_key)
    elif sort_by == 'created_time':
        image_paths.sort(key=get_file_creation_time)
    elif sort_by == 'modified_time':
        image_paths.sort(key=get_file_modification_time)
    else:
        image_paths.sort(key=natural_sort_key)  # 默认按名称

    if reverse:
        image_paths = list(reversed(image_paths))

    # 加载图片
    images = []

    for path in image_paths:
        if path.suffix.lower() in ['.nef', '.dng', '.cr2', '.cr3', '.arw', '.raf', '.orf', '.rw2']:
            try:
                import rawpy
                with rawpy.imread(str(path)) as raw:
                    rgb = raw.postprocess()
                img = Image.fromarray(rgb)
                images.append(img)
            except ImportError:
                raise ImportError(translator.tr("请安装rawpy库以处理RAW格式: pip install rawpy"))
        else:
            try:
                img = Image.open(path)
                img.load()  # 强制读取像素数据，尽早暴露损坏文件
                images.append(img)
            except Exception as e:
                raise RuntimeError(f"{translator.tr('无法打开图片')} {path}: {e}")

    return images


def get_sorted_image_paths(input_dir, sort_by='name', reverse=False):
    """返回排序后的图片路径列表（不加载图像，用于时间戳计算）"""
    image_extensions = [
        "*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff",
        "*.nef", "*.dng", "*.cr2", "*.cr3", "*.arw", "*.raf", "*.orf", "*.rw2"
    ]

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


def get_exif_capture_time(path):
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


def format_timestamp(dt):
    """格式化时间戳为 YYYYMMDD_HHMMSS"""
    return dt.strftime("%Y%m%d_%H%M%S")


def compute_timestamp(source, input_dir, sort_by='name', reverse=False):
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