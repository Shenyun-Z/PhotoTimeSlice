# PhotoTimeSlice · 时间切片照片生成器

把一组连续拍下的照片，压缩拼成一张「时间切片」图 —— 比如同一机位拍了一整天，最后得到一张天空从早到晚渐变、人流车流在同一画面里叠在一起的有趣照片。

纯 Python 实现，带 PyQt6 图形界面，同时提供可直接被其他程序调用的 Python API（`cli.py` 模块）。

---

## 它能做什么

- **9 种切片方式**：垂直条带、水平条带、圆形/椭圆形扇形、圆形/椭圆/矩形环带、垂直/水平 S 型曲线。
- **多种排序**：按文件名、创建时间、修改时间排，也支持逆序。
- **尺寸自动适配**：照片尺寸不一致也能处理，提供 4 种策略（缩放居中补边 / 居中裁切 / 拉伸铺满 / 不自动适配）。
- **实时预览**：调整参数（切片类型、位置、线性模式、排序、适配策略）时，界面即时显示基于前 8 张图的预览效果。
- **输出可控**：自定义基础文件名，可选加时间戳、加切片类型，支持 `jpg / png / webp`。
- **图形界面**：选目录、点按钮就能出图，带实时日志和进度条，还能预览文件名。
- **中 / 英双语**，浅色 / 深色两种主题，设置会自动记住。
- **RAW 支持**（可选）：装了 `rawpy` 就能直接喂 `.nef / .cr2 / .arw` 等格式。
- **流式内存优化**：逐张加载、适配并释放图片，不再一次性把所有照片载入内存，适合大批量高分辨率素材。

---

## 环境要求

- Windows 10 / 11
- Python 3.9+
- 依赖：`PyQt6`、`Pillow`（>= 12，需支持 PyQt6）、`numpy`、`tqdm`，RAW 支持另需 `rawpy`

```bash
pip install pyqt6 pillow numpy tqdm rawpy
```

> 小提示：输入目录里的照片尺寸不一时会按所选策略自动适配（以第一张图为基准）。延时摄影 / 固定机位连拍效果最好。

---

## 图形界面（推荐）

```bash
python gui.py
```

界面自上而下：选输入/输出目录 → 选尺寸适配策略 → 选切片类型和位置 → 选排序和命名规则 → 点「生成时间切片」。右下角有文件名预览，中部有实时效果预览，底部有进度条和错误日志，生成完还能自动帮你打开图片。

---

## 作为 Python 模块调用

核心 API 位于 `cli.py`（注意：本项目不再提供命令行入口，请以模块方式调用）：

```python
import cli

output = cli.run_timeslice(
    input_dir="./photos",
    output_dir="./output",
    slice_type="vertical",        # 切片类型（必填）
    position="center",            # 条带位置：left/center/right/top/bottom
    linear=False,                 # 线性模式
    reverse=False,                # 逆序排序
    sort_by="name",               # name / created_time / modified_time
    output_basename="timeslice",  # 输出文件基础名
    include_timestamp=False,
    include_slice_type=False,
    extension="jpg",              # jpg / jpeg / png / webp
    fit_strategy="scale_center",  # 尺寸适配策略
)
print(output)  # 输出文件完整路径
```

### 尺寸适配策略（`fit_strategy`）

| 值 | 说明 |
|------|------|
| `scale_center`（默认） | 保持宽高比缩放并居中，剩余区域填充纯色（不失真、不损失内容） |
| `crop_center` | 保持宽高比缩放后居中裁切，覆盖目标尺寸（不失真、损失边缘内容） |
| `stretch` | 直接拉伸到目标尺寸（可能变形） |
| `none` | 不自动适配，尺寸不一致时抛出错误 |

常量位于 `utils`：`FIT_SCALE_CENTER` / `FIT_CROP_CENTER` / `FIT_STRETCH` / `FIT_NONE`。

### 流式加载

`utils.iter_images()` 提供逐张加载的生成器，配合切片函数使用（需传入 `num_images`）：

```python
from utils import iter_images, get_sorted_image_paths, FIT_SCALE_CENTER
from slices import create_vertical_slice

paths = get_sorted_image_paths("./photos", sort_by="name", reverse=False)
result = create_vertical_slice(
    iter_images("./photos", fit_strategy=FIT_SCALE_CENTER),  # 生成器
    position="center",
    num_images=len(paths)                                     # 流式模式需提供总数
)
```

切片函数同时兼容列表输入（此时可不传 `num_images`）：

```python
from slices import create_vertical_slice, create_circular_sector_slice
result = create_vertical_slice(images_list, position="center")          # list 输入
result = create_circular_sector_slice(images_list, linear=True)          # list 输入
```

### 完整参数

`cli.run_timeslice()` 的完整签名：

```python
run_timeslice(
    input_dir,            # 输入文件夹
    output_dir,           # 输出文件夹
    slice_type,           # 切片类型（必填）
    position="center",    # 条带位置：left/center/right/top/bottom
    linear=False,         # 线性模式
    reverse=False,        # 逆序排序
    sort_by="name",       # name / created_time / modified_time
    output_basename="timeslice",
    include_timestamp=False,
    include_slice_type=False,
    extension="jpg",      # jpg / jpeg / png / webp
    progress_callback=None,          # 可选：def cb(current: int) -> None
    lang="en",            # en / zh_CN
    timestamp_source="composition",  # composition / first_capture / last_capture / first_modified / last_modified
    fit_strategy="scale_center",
    fill_color=(0, 0, 0), # 补边颜色（仅 scale_center 生效）
)
```

---

## 切片类型一览

`slice_type` 可填的值：

| 类型 | 含义 | 位置选项 | 线性模式 |
|------|------|----------|----------|
| `vertical` | 垂直条带，每张取一条竖条 | 左 / 中 / 右 | 竖条位置随图片顺序从左到右渐变（关闭则固定在所选位置） |
| `horizontal` | 水平条带，每张取一条横条 | 上 / 中 / 下 | 横条位置随图片顺序从上到下渐变（关闭则固定在所选位置） |
| `circular_sector` | 圆形 360° 等分扇形 | 居中（固定） | 扇形半径随图片顺序由小到大（第 1 张最小） |
| `elliptical_sector` | 椭圆形 360° 等分扇形 | 居中（固定） | 椭圆半轴随图片顺序由小到大（第 1 张最小） |
| `elliptical_band` | 同心椭圆环带，由内向外 | 居中（固定） | 不支持 |
| `rectangular_band` | 同心矩形环带，由内向外 | 居中（固定） | 不支持 |
| `circular_band` | 同心圆环带，由内向外 | 居中（固定） | 不支持 |
| `vertical_s` | 沿垂直方向的 S 形曲线拼接 | 左 / 中 / 右 | 关闭时每张照片都从同一横向位置裁切；开启时每张照片从各自竖向条带位置裁切（经典 S 形过渡） |
| `horizontal_s` | 沿水平方向的 S 形曲线拼接 | 上 / 中 / 下 | 关闭时每张照片都从同一纵向位置裁切；开启时每张照片从各自横向条带位置裁切（经典 S 形过渡） |

---

## 项目结构

```
PhotoTimeSlice/
├── cli.py              # 纯 API 模块：run_timeslice() 核心调度（无命令行入口）
├── gui.py              # PyQt6 图形界面（菜单 / 主题 / 语言 / 进度 / 日志 / 实时预览）
├── i18n.py             # 翻译器，加载 languages/*.locpak
├── utils.py            # 图片加载 / 尺寸适配 / 排序（含 RAW、自然排序、流式加载）
├── slices/             # 9 个切片算法 + 统一导出 __init__.py
│   ├── _common.py      # 共享辅助：列表 / 生成器输入归一化
│   ├── vertical_slice.py
│   ├── horizontal_slice.py
│   ├── circular_sector_slice.py
│   ├── elliptical_sector_slice.py
│   ├── elliptical_band_slice.py
│   ├── rectangular_band_slice.py
│   ├── circular_band_slice.py
│   ├── vertical_s_slice.py
│   └── horizontal_s_slice.py
├── languages/          # 翻译字典（JSON 格式）
│   ├── zh_CN.locpak
│   └── en.locpak
├── README.md
└── LICENSE
```

处理流程大致是：

```
输入目录 → get_sorted_image_paths() 取路径 → iter_images() 流式加载 + 适配
        → create_xxx_slice() 合成（逐张处理释放）→ 按格式保存
```

---

## 实时预览说明

- 选择输入目录后，界面会自动基于**前 8 张图片**生成预览图。
- 调整切片类型、位置、线性模式、排序或尺寸适配策略时，预览会在 0.3 秒防抖后自动刷新。
- 预览使用缩略图渲染，速度快，且能即时反映尺寸适配策略的效果。
- 预览图为效果示意，最终输出会基于全部图片按原始分辨率合成。
