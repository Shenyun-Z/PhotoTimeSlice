# PhotoTimeSlice · 时间切片照片生成器

把一组连续拍下的照片，压缩拼成一张「时间切片」图 —— 比如同一机位拍了一整天，最后得到一张天空从早到晚渐变、人流车流在同一画面里叠在一起的有趣照片。

这是我自己写来玩的一个小工具，纯 Python，带命令行和图形界面两种用法。最初只是想给延时摄影做个不一样的合成分享，后来慢慢加了好几种切片玩法，就变成现在这样了。

---

## 它能做什么

- **9 种切片方式**：垂直条带、水平条带、圆形/椭圆形扇形、圆形/椭圆/矩形环带、垂直/水平 S 型曲线。
- **多种排序**：按文件名、创建时间、修改时间排，也支持逆序。
- **输出可控**：自定义基础文件名，可选加时间戳、加切片类型，支持 `jpg / png / webp`。
- **图形界面**：选目录、点按钮就能出图，带实时日志和进度条，还能预览文件名。
- **中 / 英双语**，浅色 / 深色两种主题，设置会自动记住。
- **RAW 支持**（可选）：装了 `rawpy` 就能直接喂 `.nef / .cr2 / .arw` 等格式。

---

## 环境要求

- Windows 10 / 11
- Python 3.7+
- 依赖：`PyQt5`、`Pillow`、`numpy`、`tqdm`，RAW 支持另需 `rawpy`

```bash
pip install pyqt5 pillow numpy tqdm rawpy
```

> 小提示：输入目录里的照片**尺寸要一致**，否则会报错。延时摄影 / 固定机位连拍效果最好。

---

## 快速上手

### 图形界面（推荐）

```bash
python gui.py
```

界面自上而下：选输入/输出目录 → 选切片类型和位置 → 选排序和命名规则 → 点「生成时间切片」。右下角有文件名预览，底部有进度条和错误日志，生成完还能自动帮你打开图片。

### 命令行

最基础的用法，指定输入目录、输出目录和切片类型即可：

```bash
python cli.py -i 输入目录 -o 输出目录 -t 切片类型
```

完整一点：

```bash
python cli.py -i ./input_photos -o ./output -t vertical \
    -p center --sort-by name --output-name vacation \
    --include-timestamp --include-slice-type --extension jpg
```

常用参数：

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--input` | `-i` | 输入文件夹 | `input` |
| `--output` | `-o` | 输出文件夹 | `output` |
| `--type` | `-t` | 切片类型（必填） | — |
| `--position` | `-p` | 条带位置：left/center/right/top/bottom，或 0.0–1.0 | `center` |
| `--linear` | `-l` | 启用线性模式 | 关闭 |
| `--reverse` | `-r` | 逆序排序 | 关闭 |
| `--sort-by` | — | `name` / `created_time` / `modified_time` | `name` |
| `--output-name` | — | 输出文件基础名 | `timeslice` |
| `--include-timestamp` | — | 文件名加时间戳 | 关闭 |
| `--include-slice-type` | — | 文件名加切片类型 | 关闭 |
| `--extension` | — | `jpg` / `jpeg` / `png` / `webp` | `jpg` |
| `--language` | `-lang` | `en` / `zh_CN` | `en` |

---

## 切片类型一览

`--type` 可填的值：

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

直观一点理解：

- **条带类**（垂直/水平）：把每张图切一条，按顺序拼成整图；线性模式让这一条随时间「滑动」。
- **扇形类**（圆形/椭圆）：整图按角度分成若干扇区，每张图负责其中一扇；线性模式让扇区大小随图片序号变化。
- **环带类**：像年轮一样，每张图负责一圈，从中心一圈圈往外铺。
- **S 型曲线**：用贝塞尔曲线算出一条 S 形边界，每张图沿这条曲线「蜿蜒」拼进画面，整体更柔和。线性模式关闭时，所有照片都从同一个固定位置（左/中/右 或 上/中/下）裁切后拼接；开启时则回到经典 S 形时间切片——每张照片从自身对应的条带位置裁切，形成随图片顺序渐变的 S 形过渡。

---

## 项目结构

```
PhotoTimeSlice/
├── cli.py              # 命令行入口 + 核心调度 run_timeslice()
├── gui.py              # PyQt5 图形界面（菜单 / 主题 / 语言 / 进度 / 日志）
├── i18n.py             # 翻译器，加载 languages/*.locpak
├── utils.py            # 图片加载与排序（含 RAW、自然排序）
├── slices/             # 9 个切片算法 + 统一导出 __init__.py
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
输入目录 → load_images() 排序加载 → 尺寸检查 → create_xxx_slice() 合成 → 按格式保存
```

`cli.py` 里的 `run_timeslice()` 是 GUI 和命令行共用的执行核心。

