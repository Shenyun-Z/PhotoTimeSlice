import os
import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QLineEdit, QCheckBox, QFileDialog, QProgressBar,
                             QGroupBox, QMessageBox, QTextEdit, QMenuBar, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QSettings, QTimer
from PyQt6.QtGui import QPalette, QColor, QFont, QPainter, QMouseEvent, QPixmap, QAction
from PIL import Image
from PIL.ImageQt import toqpixmap

# 添加当前目录到系统路径
if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, application_path)

from cli import run_timeslice
from i18n import Translator  # 导入翻译器
from utils import (
    FIT_SCALE_CENTER, FIT_CROP_CENTER, FIT_STRETCH, FIT_NONE,
    fit_image, get_sorted_image_paths, open_image_single
)


# ===================== 本地化映射常量（i18n key -> 内部值） =====================
# 运行时通过 self.tr(key) 转换为当前语言的显示文本 -> 内部值，避免各处重复定义。
# key 使用 i18n 语言包中的翻译键，value 为内部稳定值（不随语言变化）。

# 切片类型: 显示文本 -> 内部类型 key
SLICE_TYPE_MAP = {
    "垂直切片": "vertical",
    "水平切片": "horizontal",
    "圆形扇形切片": "circular_sector",
    "椭圆形扇形切片": "elliptical_sector",
    "椭圆形环带切片": "elliptical_band",
    "矩形环带切片": "rectangular_band",
    "圆形环带切片": "circular_band",
    "垂直S型曲线": "vertical_s",
    "水平S型曲线": "horizontal_s",
}

# 切片类型文件名简称（key 与 value 均为 i18n key，用于 update_filename_preview）
SLICE_TYPE_SHORT_MAP = {
    "垂直切片": "垂直",
    "水平切片": "水平",
    "圆形扇形切片": "圆形扇形",
    "椭圆形扇形切片": "椭圆形扇形",
    "椭圆形环带切片": "椭圆形环带",
    "矩形环带切片": "矩形环带",
    "圆形环带切片": "圆形环带",
    "垂直S型曲线": "垂直S型",
    "水平S型曲线": "水平S型",
}

# 位置: 显示文本 -> 内部位置 key
POSITION_MAP = {
    "左侧": "left",
    "居中": "center",
    "右侧": "right",
    "顶部": "top",
    "底部": "bottom",
}

# 排序: 显示文本 -> 内部排序 key
SORT_MAP = {
    "按文件名": "name",
    "按创建时间": "created_time",
    "按修改时间": "modified_time",
}

# 时间戳来源: 显示文本 -> 内部来源 key
TIMESTAMP_SOURCE_MAP = {
    "第一张照片拍摄时间": "first_capture",
    "最后一张照片拍摄时间": "last_capture",
    "第一张照片修改时间": "first_modified",
    "最后一张照片修改时间": "last_modified",
    "时间切片合成时间": "composition",
}

# 输出扩展名（固定英文，无需翻译）
EXTENSION_MAP = {
    "JPG": "jpg",
    "PNG": "png",
    "WebP": "webp",
}

# 尺寸适配策略: 显示文本 -> 内部策略值
FIT_MAP = {
    "缩放居中补边": FIT_SCALE_CENTER,
    "居中裁切": FIT_CROP_CENTER,
    "拉伸铺满": FIT_STRETCH,
    "不自动适配": FIT_NONE,
}


class LogEvent(QEvent):
    """用于线程安全日志更新的自定义事件"""
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, text, is_error=False):
        super().__init__(LogEvent.EVENT_TYPE)
        self.text = text
        self.is_error = is_error


class TimesliceWorker(QThread):
    progress_signal = pyqtSignal(int)
    total_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    cancelled_signal = pyqtSignal()

    def __init__(self, params):
        super().__init__()
        self.params = params
        # 缓存 Translator，避免每次 tr() 重新加载 JSON 翻译文件（磁盘 I/O）
        self._translator = Translator(self.params.get('lang', 'en'))
        # 取消标志：由 GUI 主线程调用 cancel() 置位，工作线程在进度回调中检查
        self._cancel_requested = False

    def cancel(self):
        """请求取消当前任务（线程安全，仅置标志位）"""
        self._cancel_requested = True

    def run(self):
        try:
            from utils import get_sorted_image_paths
            # 仅列举路径统计总数，不加载像素；加载交由 run_timeslice 单次完成（#1）
            image_paths = get_sorted_image_paths(
                self.params['input_dir'],
                self.params['sort_by'],
                self.params['reverse'])
            total_images = len(image_paths)
            self.total_signal.emit(total_images)

            if total_images == 0:
                raise Exception(self.tr("输入目录中没有找到图片"))

            self.log_signal.emit(f"找到 {total_images} 张图片，开始处理...")

            def progress_callback(current):
                if self._cancel_requested:
                    from cli import OperationCancelled
                    raise OperationCancelled("任务已被用户取消")
                self.progress_signal.emit(current)

            output_path = run_timeslice(
                input_dir=self.params['input_dir'],
                output_dir=self.params['output_dir'],
                slice_type=self.params['slice_type'],
                position=self.params['position'],
                linear=self.params['linear'],
                reverse=self.params['reverse'],
                sort_by=self.params['sort_by'],
                output_basename=self.params['output_basename'],
                include_timestamp=self.params['include_timestamp'],
                include_slice_type=self.params['include_slice_type'],
                extension=self.params['extension'],
                lang=self.params.get('lang', 'en'),
                timestamp_source=self.params.get('timestamp_source', 'composition'),
                fit_strategy=self.params.get('fit_strategy', FIT_SCALE_CENTER),
                progress_callback=progress_callback
            )

            self.progress_signal.emit(total_images)
            self.finished_signal.emit(output_path)
        except Exception as e:
            from cli import OperationCancelled
            if isinstance(e, OperationCancelled):
                self.cancelled_signal.emit()
            else:
                self.error_signal.emit(str(e))

    def tr(self, text):
        """翻译方法（线程内），使用用户选择的语言（Translator 已缓存）"""
        return self._translator.tr(text)


class PreviewWorker(QThread):
    """实时预览线程：加载少量缩略图并按当前参数快速合成预览图"""
    preview_ready = pyqtSignal(object, int)  # (QPixmap, request_seq)
    preview_failed = pyqtSignal(str, int)

    def __init__(self, params, request_seq, parent=None):
        super().__init__(parent)
        self.params = params
        self.request_seq = request_seq

    def run(self):
        try:
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
            input_dir = self.params['input_dir']
            sort_by = self.params['sort_by']
            reverse = self.params['reverse']
            fit_strategy = self.params.get('fit_strategy', FIT_SCALE_CENTER)
            max_images = self.params.get('max_images', 8)
            preview_max_side = self.params.get('preview_max_side', 320)

            paths = get_sorted_image_paths(input_dir, sort_by, reverse)
            paths = paths[:max_images]
            if not paths:
                raise Exception("no images")

            # 流式加载缩略图并统一尺寸（支持中断请求，避免语言切换/关窗时阻塞）
            thumbs = []
            base_size = None
            for path in paths:
                if self.isInterruptionRequested():
                    return
                img = open_image_single(path, 'en')
                img.thumbnail((preview_max_side, preview_max_side), Image.LANCZOS)
                img = img.convert('RGB')
                if base_size is None:
                    base_size = img.size
                else:
                    img = fit_image(img, base_size, fit_strategy)
                thumbs.append(img)

            slice_type = self.params['slice_type']
            position = self.params.get('position', 'center')
            linear = self.params.get('linear', False)
            num_images = len(thumbs)

            if slice_type == "vertical":
                result = create_vertical_slice(thumbs, position, linear, num_images=num_images)
            elif slice_type == "horizontal":
                result = create_horizontal_slice(thumbs, position, linear, num_images=num_images)
            elif slice_type == "circular_sector":
                result = create_circular_sector_slice(thumbs, linear, num_images=num_images)
            elif slice_type == "elliptical_sector":
                result = create_elliptical_sector_slice(thumbs, linear, num_images=num_images)
            elif slice_type == "elliptical_band":
                result = create_elliptical_band_slice(thumbs, num_images=num_images)
            elif slice_type == "rectangular_band":
                result = create_rectangular_band_slice(thumbs, num_images=num_images)
            elif slice_type == "circular_band":
                result = create_circular_band_slice(thumbs, num_images=num_images)
            elif slice_type == "vertical_s":
                result = create_vertical_s_slice(thumbs, position, linear, num_images=num_images)
            elif slice_type == "horizontal_s":
                result = create_horizontal_s_slice(thumbs, position, linear, num_images=num_images)
            else:
                raise ValueError(f"未知切片类型: {slice_type}")

            if result is None:
                raise Exception("slice returned None")

            # 转换为 QPixmap（Pillow 官方 toqpixmap，需 PyQt6）
            pixmap = toqpixmap(result)
            self.preview_ready.emit(pixmap, self.request_seq)
        except Exception as e:
            self.preview_failed.emit(str(e), self.request_seq)


class TimestampComputeWorker(QThread):
    """后台时间戳计算线程：扫描目录读 EXIF 属 I/O 操作，移出主线程避免阻塞 GUI"""
    computed = pyqtSignal(tuple, object)  # (cache_key, timestamp_str or None)

    def __init__(self, source, input_dir, sort_by, reverse, parent=None):
        super().__init__(parent)
        self.source = source
        self.input_dir = input_dir
        self.sort_by = sort_by
        self.reverse = reverse
        self.cache_key = (source, input_dir, sort_by, reverse)

    def run(self):
        try:
            from utils import compute_timestamp
            ts = compute_timestamp(self.source, self.input_dir, self.sort_by, self.reverse)
            self.computed.emit(self.cache_key, ts)
        except Exception:
            # 计算失败不阻断 UI，交回主线程显示占位符
            self.computed.emit(self.cache_key, None)


class VerticalModeSwitch(QWidget):
    """竖向模式开关：只有上下两个状态，点击整个控件切换一次模式（不随拖动频繁发射信号）"""
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._top_text = ""
        self._bottom_text = ""
        self.setFixedSize(40, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_top_text(self, text):
        self._top_text = text
        self.update()

    def set_bottom_text(self, text):
        self._bottom_text = text
        self.update()

    def top_text(self):
        return self._top_text

    def bottom_text(self):
        return self._bottom_text

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.update()
            self.toggled.emit(self._checked)

    def isChecked(self):
        return self._checked

    def mouseReleaseEvent(self, event: QMouseEvent):
        # 点击切换：仅左键且控件可用时切换一次（上下两个状态互斥）
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setChecked(not self._checked)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = self.palette()
        w = self.width()
        track_w = 22
        track_h = 70
        track_x = (w - track_w) // 2
        track_y = 10

        # 轨道背景
        track_color = QColor("#e0e0e0") if self.isEnabled() else QColor("#b0b0b0")
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_x, track_y, track_w, track_h, track_w // 2, track_w // 2)

        # 滑块
        knob_d = 18
        if self._checked:
            knob_y = track_y + track_h - knob_d - 2
        else:
            knob_y = track_y + 2
        knob_x = track_x + (track_w - knob_d) // 2

        if self.isEnabled():
            knob_color = palette.color(QPalette.ColorRole.Highlight)
        else:
            knob_color = QColor("#bdbdbd")
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_x, knob_y, knob_d, knob_d)

        painter.end()


class TimesliceGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("TimeslicePhotoGenerator", "Settings")

        # 初始化翻译器 - 默认使用中文
        self.translator = Translator()
        self.current_lang = self.settings.value("language", "zh_CN")
        self.translator.load_translations(self.current_lang)
        self._build_localized_maps()

        self.app = QApplication.instance()

        # 初始化主题 - 默认使用浅色
        self.current_theme = self.settings.value("theme", "light")

        self.init_ui()
        self.load_theme()

        self.setWindowTitle(self.tr("时间切片照片生成器"))
        self.setGeometry(100, 100, 860, 760)  # 增加高度以容纳实时预览

        self.current_output_path = ""
        self.total_images = 0
        self.worker = None

        # 实时预览相关状态
        self.preview_worker = None
        self._preview_pending = False          # 跳过模式下记录待刷新的最新参数
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)  # 防抖：参数连续变化时延迟刷新
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_request_seq = 0

        # 时间戳异步计算状态（避免主线程扫描目录/读 EXIF 阻塞）
        self._timestamp_cache = {}            # cache_key -> 已计算的时间戳
        self._ts_worker = None                # 当前运行中的时间戳计算线程
        self._ts_pending_key = None           # 待计算的最新 key（合并连续请求）
        self._ts_timer = QTimer(self)
        self._ts_timer.setSingleShot(True)
        self._ts_timer.setInterval(300)       # 防抖：合并连续输入产生的计算请求
        self._ts_timer.timeout.connect(self._start_timestamp_worker)

    def tr(self, text):
        """翻译方法"""
        return self.translator.tr(text)

    def _build_localized_maps(self):
        """按当前语言构建本地化映射缓存（语言切换时重建）"""
        self._l_slice_type = {self.tr(k): v for k, v in SLICE_TYPE_MAP.items()}
        self._l_slice_type_short = {self.tr(k): self.tr(v) for k, v in SLICE_TYPE_SHORT_MAP.items()}
        self._l_position = {self.tr(k): v for k, v in POSITION_MAP.items()}
        self._l_sort = {self.tr(k): v for k, v in SORT_MAP.items()}
        self._l_timestamp_source = {self.tr(k): v for k, v in TIMESTAMP_SOURCE_MAP.items()}
        self._l_fit = {self.tr(k): v for k, v in FIT_MAP.items()}

    def apply_theme_style(self, theme_type):
        """应用Windows主题样式"""
        palette = QPalette()

        if theme_type == "dark":
            # Windows深色模式样式
            self.app.setStyle("Fusion")
            dark_color = QColor(45, 45, 45)
            light_color = QColor(180, 180, 180)

            # 主界面调色板
            palette.setColor(QPalette.ColorRole.Window, dark_color)
            palette.setColor(QPalette.ColorRole.WindowText, light_color)
            palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.ColorRole.AlternateBase, dark_color)
            palette.setColor(QPalette.ColorRole.ToolTipBase, light_color)
            palette.setColor(QPalette.ColorRole.ToolTipText, light_color)
            palette.setColor(QPalette.ColorRole.Text, light_color)
            palette.setColor(QPalette.ColorRole.Button, dark_color)
            palette.setColor(QPalette.ColorRole.ButtonText, light_color)
            palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
            palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

            # 统一样式表
            menu_style = """
                QMenuBar {
                    background-color: #2d2d2d;
                    color: #b4b4b4;
                    border: none;
                }
                QMenuBar::item {
                    background-color: #2d2d2d;
                    color: #b4b4b4;
                    padding: 4px 8px;
                }
                QMenuBar::item:selected {
                    background-color: #2a82da;
                    color: black;
                }
                QMenu {
                    background-color: #2d2d2d;
                    color: #b4b4b4;
                    border: 1px solid #555;
                }
                QMenu::item {
                    padding: 4px 20px;
                }
                QMenu::item:selected {
                    background-color: #2a82da;
                    color: black;
                }
                QGroupBox {
                    color: #b4b4b4;
                    border: 1px solid #555;
                    margin-top: 10px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 4px;
                }
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #ff6b6b;
                    border: 1px solid #555;
                }
                QProgressBar {
                    background-color: #333;
                    border: 1px solid #555;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #2a82da;
                }
                QLineEdit {
                    background-color: #333;
                    color: #b4b4b4;
                    border: 1px solid #555;
                    padding: 2px;
                }
                QComboBox {
                    background-color: #333;
                    color: #b4b4b4;
                    border: 1px solid #555;
                }
                QComboBox::drop-down {
                    border-left: 1px solid #555;
                }
                QCheckBox {
                    color: #b4b4b4;
                }
                QCheckBox:disabled {
                    color: #666;
                }
                QPushButton {
                    background-color: #333;
                    color: #b4b4b4;
                    border: 1px solid #555;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #444;
                }
                QPushButton:pressed {
                    background-color: #1e1e1e;
                }
            """
            self.error_log.setStyleSheet("background-color: #1e1e1e; color: #ff6b6b; border: 1px solid #555;")

        else:
            # Windows浅色模式样式（默认）
            self.app.setStyle("Fusion")
            palette = QPalette()

            menu_style = """
                QMenuBar {
                    background-color: #f0f0f0;
                    color: #333;
                    border: none;
                }
                QMenuBar::item {
                    background-color: #f0f0f0;
                    color: #333;
                    padding: 4px 8px;
                }
                QMenuBar::item:selected {
                    background-color: #d0d0d0;
                    color: #000;
                }
                QMenu {
                    background-color: #ffffff;
                    color: #333;
                    border: 1px solid #ccc;
                }
                QMenu::item:selected {
                    background-color: #e0e0e0;
                    color: #000;
                }
                QGroupBox {
                    color: #333;
                    border: 1px solid #ccc;
                    margin-top: 10px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 4px;
                }
                QTextEdit {
                    background-color: #ffffff;
                    color: #d32f2f;
                    border: 1px solid #ccc;
                }
                QProgressBar {
                    background-color: #f0f0f0;
                    border: 1px solid #ccc;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #2196f3;
                }
                QLineEdit {
                    background-color: #fff;
                    color: #333;
                    border: 1px solid #ccc;
                    padding: 2px;
                }
                QComboBox {
                    background-color: #fff;
                    color: #333;
                    border: 1px solid #ccc;
                }
                QComboBox:disabled {
                    background-color: #f5f5f5;
                    color: #999;
                }
                QCheckBox {
                    color: #333;
                }
                QCheckBox:disabled {
                    color: #999;
                }
                QPushButton {
                    background-color: #f0f0f0;
                    color: #333;
                    border: 1px solid #ccc;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
            """
            self.error_log.setStyleSheet("background-color: #ffffff; color: #d32f2f; border: 1px solid #ccc;")

        # 应用样式
        self.app.setPalette(palette)
        if hasattr(self, 'menu_bar'):
            self.menu_bar.setStyleSheet(menu_style)
        self.setStyleSheet(menu_style)

        # 主题切换后刷新线性模式选项文字的高亮颜色
        if hasattr(self, 'linear_switch'):
            self.refresh_linear_labels()

    def load_theme(self):
        """加载主题设置（默认浅色）"""
        theme = self.current_theme

        if theme == "dark":
            self.apply_theme_style("dark")
        else:
            self.apply_theme_style("light")

        # 更新主题菜单选中标记
        self.update_menu_check_state()

    def change_theme(self, theme):
        """切换主题（仅浅色/深色）"""
        self.current_theme = theme
        self.settings.setValue("theme", theme)

        self.apply_theme_style(theme)
        # 更新菜单选中状态
        self.update_menu_check_state()

    def change_language(self, lang):
        """切换语言并更新菜单标记。

        重建 UI 前先确保后台线程已安全停止：
        - 切片任务（worker）在跑时禁止切换（菜单已置灰，此处双保险返回）
        - 预览/时间戳线程通过 requestInterruption + 短等待自然结束
        避免信号发送到已销毁控件导致段错误。
        """
        # 切片任务运行中禁止切换（菜单已置灰，双保险）
        if self.worker is not None and self.worker.isRunning():
            self.status_bar.showMessage(self.tr("正在处理中，请等待完成或取消"))
            return

        # 停止定时器
        self._preview_timer.stop()
        self._ts_timer.stop()

        # 停止后台线程：断开信号 + 中断 + 等待完全结束。
        # 若线程未能及时停止（极端情况：卡在切片计算/EXIF 读取），放弃本次切换，
        # 避免旧线程完成后的信号发送到已重建控件导致段错误。
        if not self._stop_background_threads(timeout_ms=3000):
            self.status_bar.showMessage(self.tr("后台任务仍在运行，请稍后再切换语言"))
            return
        # 线程已全部停止并断开信号，可安全重建 UI
        self.preview_worker = None
        self._ts_worker = None

        self.current_lang = lang
        self.settings.setValue("language", lang)
        self.translator.load_translations(lang)
        self._build_localized_maps()

        # 重建前先保存用户已填写的设置（路径、选项等）
        state = self._capture_ui_state()
        # 重新初始化UI并更新菜单标记
        self.init_ui()
        self.load_theme()
        # 重建后恢复设置，避免语言切换导致清空
        self._restore_ui_state(state)

    def _capture_ui_state(self):
        """重建UI前保存用户已设置的各项值"""
        return {
            'input_dir': self.input_dir_edit.text(),
            'output_dir': self.output_dir_edit.text(),
            'basename': self.basename_edit.text(),
            'type_index': self.type_combo.currentIndex(),
            'position_index': self.position_combo.currentIndex(),
            'sort_index': self.sort_combo.currentIndex(),
            'extension_index': self.extension_combo.currentIndex(),
            'timestamp_source_index': self.timestamp_source_combo.currentIndex(),
            'fit_index': self.fit_combo.currentIndex(),
            'linear': self.linear_switch.isChecked(),
            'reverse': self.reverse_check.isChecked(),
            'auto_open': self.auto_open_check.isChecked(),
            'timestamp': self.timestamp_check.isChecked(),
            'slice_type': self.slice_type_check.isChecked(),
        }

    def _restore_ui_state(self, state):
        """重建UI后恢复用户设置"""
        self.input_dir_edit.setText(state['input_dir'])
        self.output_dir_edit.setText(state['output_dir'])
        self.basename_edit.setText(state['basename'])

        # 先恢复切片类型（会触发 update_controls_state 重建位置/线性选项）
        self.type_combo.setCurrentIndex(state['type_index'])
        # 再恢复位置索引（与类型选项顺序一致）
        self.position_combo.setCurrentIndex(state['position_index'])

        self.sort_combo.setCurrentIndex(state['sort_index'])
        self.extension_combo.setCurrentIndex(state['extension_index'])
        self.fit_combo.setCurrentIndex(state['fit_index'])
        self.linear_switch.setChecked(state['linear'])
        self.reverse_check.setChecked(state['reverse'])
        self.auto_open_check.setChecked(state['auto_open'])
        self.timestamp_check.setChecked(state['timestamp'])
        self.slice_type_check.setChecked(state['slice_type'])
        self.timestamp_source_combo.setCurrentIndex(state['timestamp_source_index'])

        # 刷新依赖状态与文件名预览
        self.update_timestamp_source_state()
        self.update_filename_preview()
        # 语言切换重建后重新生成实时预览
        self._schedule_preview()

    def update_menu_check_state(self):
        """更新菜单选中标记（✓）与可用状态"""
        # 更新主题菜单
        if hasattr(self, 'light_theme_action'):
            self.light_theme_action.setChecked(self.current_theme == "light")
            self.dark_theme_action.setChecked(self.current_theme == "dark")

        # 更新语言菜单（任务在跑时置灰，禁止切换避免重建 UI 时线程信号指向已销毁控件）
        if hasattr(self, 'chinese_action'):
            self.chinese_action.setChecked(self.current_lang == "zh_CN")
            self.english_action.setChecked(self.current_lang == "en")
            # worker 属性在 __init__ 中 init_ui() 之后才初始化，需安全访问
            worker = getattr(self, 'worker', None)
            worker_busy = worker is not None and worker.isRunning()
            self.chinese_action.setEnabled(not worker_busy)
            self.english_action.setEnabled(not worker_busy)

    def init_ui(self):
        """初始化Windows界面（移除跟随系统+添加选中标记）"""
        # 设置Windows字体
        font = QFont()
        font.setFamily("SimHei")
        self.setFont(font)

        # 窗口标题（随语言切换刷新）
        self.setWindowTitle(self.tr("时间切片照片生成器"))

        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)

        # 视图菜单（移除跟随系统）
        self.view_menu = QMenu(self.tr("视图(&V)"))
        self.menu_bar.addMenu(self.view_menu)

        # 主题选项（仅浅色/深色）
        self.theme_menu = QMenu(self.tr("主题"))
        self.view_menu.addMenu(self.theme_menu)

        # 浅色模式（添加选中标记）
        self.light_theme_action = QAction(self.tr("浅色模式"), self)
        self.light_theme_action.setCheckable(True)  # 可选中
        self.light_theme_action.triggered.connect(lambda: self.change_theme('light'))
        self.theme_menu.addAction(self.light_theme_action)

        # 深色模式（添加选中标记）
        self.dark_theme_action = QAction(self.tr("深色模式"), self)
        self.dark_theme_action.setCheckable(True)  # 可选中
        self.dark_theme_action.triggered.connect(lambda: self.change_theme('dark'))
        self.theme_menu.addAction(self.dark_theme_action)

        # 语言菜单（添加选中标记）
        self.lang_menu = QMenu(self.tr("语言(&L)"))
        self.menu_bar.addMenu(self.lang_menu)

        self.chinese_action = QAction("中文", self)
        self.chinese_action.setCheckable(True)  # 可选中
        self.chinese_action.triggered.connect(lambda: self.change_language('zh_CN'))
        self.lang_menu.addAction(self.chinese_action)

        self.english_action = QAction("English", self)
        self.english_action.setCheckable(True)  # 可选中
        self.english_action.triggered.connect(lambda: self.change_language('en'))
        self.lang_menu.addAction(self.english_action)

        # 主布局
        main_layout = QVBoxLayout()

        self.title_label = QLabel(self.tr("时间切片照片生成器"))
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        # 输入设置
        self.input_group = QGroupBox(self.tr("输入设置"))
        input_layout = QVBoxLayout()

        input_dir_layout = QHBoxLayout()
        self.input_dir_label = QLabel(self.tr("输入目录:"))
        self.input_dir_edit = QLineEdit()
        self.input_dir_edit.setPlaceholderText(self.tr("选择包含照片的目录"))
        self.input_dir_btn = QPushButton(self.tr("浏览..."))
        self.input_dir_btn.clicked.connect(self.select_input_dir)
        input_dir_layout.addWidget(self.input_dir_label)
        input_dir_layout.addWidget(self.input_dir_edit)
        input_dir_layout.addWidget(self.input_dir_btn)
        input_layout.addLayout(input_dir_layout)

        output_dir_layout = QHBoxLayout()
        self.output_dir_label = QLabel(self.tr("输出目录:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText(self.tr("选择结果保存目录"))
        self.output_dir_btn = QPushButton(self.tr("浏览..."))
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_dir_layout.addWidget(self.output_dir_label)
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.output_dir_btn)
        input_layout.addLayout(output_dir_layout)

        fit_layout = QHBoxLayout()
        self.fit_label = QLabel(self.tr("尺寸适配:"))
        self.fit_combo = QComboBox()
        self.fit_combo.addItems([
            self.tr("缩放居中补边"),
            self.tr("居中裁切"),
            self.tr("拉伸铺满"),
            self.tr("不自动适配")
        ])
        self.fit_combo.setToolTip(self.tr("图片尺寸不一致时的处理方式（以第一张图为基准）"))
        fit_layout.addWidget(self.fit_label)
        fit_layout.addWidget(self.fit_combo)
        fit_layout.addStretch()
        input_layout.addLayout(fit_layout)

        self.input_group.setLayout(input_layout)
        main_layout.addWidget(self.input_group)

        # 切片设置
        self.slice_group = QGroupBox(self.tr("切片设置"))
        slice_layout = QVBoxLayout()

        type_layout = QHBoxLayout()
        self.type_label = QLabel(self.tr("切片类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            self.tr("垂直切片"),
            self.tr("水平切片"),
            self.tr("圆形扇形切片"),
            self.tr("椭圆形扇形切片"),
            self.tr("椭圆形环带切片"),
            self.tr("矩形环带切片"),
            self.tr("圆形环带切片"),
            self.tr("垂直S型曲线"),
            self.tr("水平S型曲线")
        ])
        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_combo)
        slice_layout.addLayout(type_layout)

        position_layout = QHBoxLayout()
        self.position_label = QLabel(self.tr("位置设置:"))
        self.position_combo = QComboBox()
        # 默认设置为垂直切片的位置选项
        self.position_combo.addItems([
            self.tr("左侧"),
            self.tr("居中"),
            self.tr("右侧")
        ])
        self.position_combo.setEnabled(True)
        self.type_combo.currentIndexChanged.connect(self.update_controls_state)
        position_layout.addWidget(self.position_label)
        position_layout.addWidget(self.position_combo)
        slice_layout.addLayout(position_layout)

        # 新增：排序规则
        sort_layout = QHBoxLayout()
        self.sort_label = QLabel(self.tr("排序规则:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            self.tr("按文件名"),
            self.tr("按创建时间"),
            self.tr("按修改时间")
        ])
        sort_layout.addWidget(self.sort_label)
        sort_layout.addWidget(self.sort_combo)
        slice_layout.addLayout(sort_layout)

        # 拼接模式（竖向滑动开关 + 右侧选项文字）
        linear_layout = QHBoxLayout()
        linear_layout.setSpacing(8)
        self.linear_mode_label = QLabel(self.tr("拼接模式:"))
        self.linear_switch = VerticalModeSwitch()
        self.linear_switch.toggled.connect(self.update_linear_mode_state)

        # 右侧选项文字容器
        labels_widget = QWidget()
        labels_layout = QVBoxLayout(labels_widget)
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(0)
        self.linear_top_label = QLabel()
        self.linear_top_label.setWordWrap(True)
        self.linear_bottom_label = QLabel()
        self.linear_bottom_label.setWordWrap(True)
        labels_layout.addWidget(self.linear_top_label)
        labels_layout.addStretch()
        labels_layout.addWidget(self.linear_bottom_label)

        linear_layout.addWidget(self.linear_mode_label)
        linear_layout.addWidget(self.linear_switch)
        linear_layout.addWidget(labels_widget)
        linear_layout.addStretch()
        slice_layout.addLayout(linear_layout)

        # 其他选项
        options_layout = QHBoxLayout()
        self.reverse_check = QCheckBox(self.tr("逆序排序"))
        self.auto_open_check = QCheckBox(self.tr("完成后自动打开图片"))

        options_layout.addWidget(self.reverse_check)
        options_layout.addWidget(self.auto_open_check)
        options_layout.addStretch()
        slice_layout.addLayout(options_layout)

        self.slice_group.setLayout(slice_layout)
        main_layout.addWidget(self.slice_group)

        # 新增：输出文件命名设置
        self.output_naming_group = QGroupBox(self.tr("输出文件命名"))
        naming_layout = QVBoxLayout()

        # 基础文件名
        name_layout = QHBoxLayout()
        self.basename_label = QLabel(self.tr("基础名称:"))
        self.basename_edit = QLineEdit()
        self.basename_edit.setText("timeslice")
        self.basename_edit.setPlaceholderText(self.tr("输入文件基础名称"))
        name_layout.addWidget(self.basename_label)
        name_layout.addWidget(self.basename_edit)
        naming_layout.addLayout(name_layout)

        # 扩展名选择
        extension_layout = QHBoxLayout()
        self.extension_label = QLabel(self.tr("文件格式:"))
        self.extension_combo = QComboBox()
        self.extension_combo.addItems(["JPG", "PNG", "WebP"])
        extension_layout.addWidget(self.extension_label)
        extension_layout.addWidget(self.extension_combo)
        naming_layout.addLayout(extension_layout)

        # 可选后缀
        suffix_layout = QHBoxLayout()
        self.timestamp_check = QCheckBox(self.tr("添加时间戳"))
        self.slice_type_check = QCheckBox(self.tr("添加切片类型"))
        suffix_layout.addWidget(self.timestamp_check)
        suffix_layout.addWidget(self.slice_type_check)
        naming_layout.addLayout(suffix_layout)

        # 时间戳来源
        timestamp_source_layout = QHBoxLayout()
        self.timestamp_source_label = QLabel(self.tr("时间戳来源:"))
        self.timestamp_source_combo = QComboBox()
        self.timestamp_source_combo.addItems([
            self.tr("第一张照片拍摄时间"),
            self.tr("最后一张照片拍摄时间"),
            self.tr("第一张照片修改时间"),
            self.tr("最后一张照片修改时间"),
            self.tr("时间切片合成时间")
        ])
        self.timestamp_source_combo.setEnabled(False)
        timestamp_source_layout.addWidget(self.timestamp_source_label)
        timestamp_source_layout.addWidget(self.timestamp_source_combo)
        timestamp_source_layout.addStretch()
        naming_layout.addLayout(timestamp_source_layout)

        # 文件名预览
        preview_layout = QHBoxLayout()
        self.preview_label = QLabel(self.tr("预览:"))
        self.filename_preview = QLabel("timeslice.jpg")
        self.filename_preview.setStyleSheet("color: #666; font-style: italic;")
        preview_layout.addWidget(self.preview_label)
        preview_layout.addWidget(self.filename_preview)
        preview_layout.addStretch()
        naming_layout.addLayout(preview_layout)

        self.output_naming_group.setLayout(naming_layout)
        main_layout.addWidget(self.output_naming_group)

        # 实时预览
        self.preview_group = QGroupBox(self.tr("实时预览"))
        preview_layout = QVBoxLayout()
        self.preview_canvas = QLabel()
        self.preview_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_canvas.setMinimumHeight(180)
        self.preview_canvas.setStyleSheet("border: 1px solid #ccc; background-color: #1e1e1e; color: #888;")
        self.preview_canvas.setText(self.tr("选择输入目录后自动预览"))
        preview_layout.addWidget(self.preview_canvas)
        self.preview_status_label = QLabel()
        self.preview_status_label.setStyleSheet("color: #888;")
        preview_layout.addWidget(self.preview_status_label)
        self.preview_group.setLayout(preview_layout)
        main_layout.addWidget(self.preview_group)

        # 进度信息
        self.progress_group = QGroupBox(self.tr("进度信息"))
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)  # 导入前显示静止的 0%，无动画
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(self.tr("已处理 %v 张"))
        progress_layout.addWidget(self.progress_bar)

        self.error_log = QTextEdit()
        self.error_log.setReadOnly(True)
        self.error_log.setPlaceholderText(self.tr("错误日志将显示在这里..."))
        progress_layout.addWidget(self.error_log)

        self.progress_group.setLayout(progress_layout)
        main_layout.addWidget(self.progress_group)

        # 生成 / 取消按钮
        button_layout = QHBoxLayout()
        self.process_btn = QPushButton(self.tr("生成时间切片"))
        self.process_btn.clicked.connect(self.process_images)
        self.process_btn.setMinimumHeight(40)
        button_layout.addWidget(self.process_btn)

        self.cancel_btn = QPushButton(self.tr("取消处理"))
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(button_layout)

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage(self.tr("准备就绪"))

        # 初始化控件状态
        self.update_controls_state(0)

        # 连接文件名预览更新信号
        self.basename_edit.textChanged.connect(self.update_filename_preview)
        self.extension_combo.currentTextChanged.connect(self.update_filename_preview)
        self.timestamp_check.stateChanged.connect(self.update_timestamp_source_state)
        self.timestamp_source_combo.currentTextChanged.connect(self.update_filename_preview)
        self.slice_type_check.stateChanged.connect(self.update_filename_preview)
        self.type_combo.currentIndexChanged.connect(self.update_filename_preview)
        self.sort_combo.currentIndexChanged.connect(self.update_filename_preview)
        self.reverse_check.stateChanged.connect(self.update_filename_preview)
        self.input_dir_edit.textChanged.connect(self.update_filename_preview)

        # 连接实时预览刷新信号（参数变化时触发，带防抖）
        self.type_combo.currentIndexChanged.connect(self._schedule_preview)
        self.position_combo.currentIndexChanged.connect(self._schedule_preview)
        self.sort_combo.currentIndexChanged.connect(self._schedule_preview)
        self.reverse_check.stateChanged.connect(self._schedule_preview)
        self.fit_combo.currentIndexChanged.connect(self._schedule_preview)
        self.linear_switch.toggled.connect(self._schedule_preview)
        self.input_dir_edit.textChanged.connect(self._schedule_preview)

        # 初始化菜单选中状态 - 启动时自动选中中文和浅色模式
        self.update_menu_check_state()

    def update_filename_preview(self):
        """更新文件名预览（时间戳后台异步计算，避免主线程扫描目录阻塞）"""
        from utils import sanitize_filename

        # 获取当前设置
        basename = sanitize_filename(self.basename_edit.text() or "timeslice")
        extension = self.extension_combo.currentText().lower()
        include_timestamp = self.timestamp_check.isChecked()
        include_slice_type = self.slice_type_check.isChecked()

        # 获取切片类型（文件名简称随语言切换）
        slice_type_text = self._l_slice_type_short.get(self.type_combo.currentText(), "")

        # 排序映射
        sort_by = self._l_sort.get(self.sort_combo.currentText(), "name")

        # 构建文件名部分
        parts = [basename]

        if include_timestamp:
            source = self._l_timestamp_source.get(self.timestamp_source_combo.currentText(), "composition")
            # 时间戳完全异步化：先查缓存，未命中则显示占位符并调度后台计算
            cache_key = (source, self.input_dir_edit.text(), sort_by, self.reverse_check.isChecked())
            ts = self._timestamp_cache.get(cache_key)
            if ts is None:
                ts = "YYYYMMDD_HHMMSS"  # 占位符，后台算完后自动刷新
                self._schedule_timestamp_compute(source, cache_key)
            parts.append(ts)

        if include_slice_type and slice_type_text:
            parts.append(slice_type_text)

        # 组合文件名
        filename = "-".join(parts)

        # 添加扩展名
        if extension == "jpg":
            extension = "jpg"
        elif extension == "webp":
            extension = "webp"
        else:
            extension = "png"

        preview_text = f"{filename}.{extension}"
        self.filename_preview.setText(preview_text)

    # ---------- 后台线程安全停止 ----------
    def _stop_background_threads(self, timeout_ms=3000):
        """停止预览/时间戳线程：断开信号连接 + 请求中断 + 等待线程结束。

        关键：先 disconnect() 断掉所有信号槽连接。这样即使线程稍后完成并
        emit 信号，也不会调用到已失效/已重建的槽函数（从根本上杜绝野指针
        段错误）。之后请求中断并等待线程自然结束。

        返回 True 表示全部线程已停止；False 表示有线程超时仍在运行
        （此时信号已断开，仍安全，仅线程对象仍在后台）。
        """
        ok = True
        workers = (
            (self.preview_worker, ('preview_ready', 'preview_failed')),
            (self._ts_worker, ('computed',)),
        )
        for worker, signal_names in workers:
            if worker is None or not worker.isRunning():
                continue
            # 1. 断开所有信号连接：线程完成后的 emit 不再触发任何槽
            for name in signal_names:
                try:
                    getattr(worker, name).disconnect()
                except (TypeError, RuntimeError):
                    pass
            # 2. 请求中断并等待自然结束
            worker.requestInterruption()
            if not worker.wait(timeout_ms):
                ok = False
        return ok

    # ---------- 时间戳异步计算 ----------
    def _schedule_timestamp_compute(self, source, cache_key):
        """调度时间戳后台计算（合并连续请求，防抖 300ms 后启动）"""
        if cache_key in self._timestamp_cache:
            return
        self._ts_pending_key = (source, cache_key)
        self._ts_timer.start()

    def _start_timestamp_worker(self):
        """启动时间戳计算线程（仅计算最新待处理请求，跳过模式不阻塞主线程）"""
        if self._ts_pending_key is None:
            return
        # 跳过模式：若旧线程仍在运行，放弃本次启动；旧线程完成后的
        # update_filename_preview 会发现缓存未命中而重新调度，最终必算到
        if self._ts_worker is not None and self._ts_worker.isRunning():
            return
        source, cache_key = self._ts_pending_key
        self._ts_pending_key = None
        input_dir, sort_by, reverse = cache_key[1], cache_key[2], cache_key[3]
        self._ts_worker = TimestampComputeWorker(source, input_dir, sort_by, reverse, self)
        self._ts_worker.computed.connect(self._on_timestamp_computed)
        self._ts_worker.start()

    def _on_timestamp_computed(self, cache_key, ts):
        """时间戳计算完成：更新缓存并刷新预览（sender 防御：忽略旧线程残留信号）"""
        if self.sender() is not self._ts_worker:
            return
        if ts is not None:
            self._timestamp_cache[cache_key] = ts
        # 无论成功与否都刷新预览（失败时保持占位符）
        self.update_filename_preview()

    def update_timestamp_source_state(self):
        """时间戳复选框切换时启用/禁用来源下拉框并刷新预览"""
        enabled = self.timestamp_check.isChecked()
        self.timestamp_source_combo.setEnabled(enabled)
        self.update_filename_preview()

    def update_controls_state(self, index):
        """更新控件状态"""
        slice_type = self.type_combo.currentText()

        # 保存当前选中的位置（如果有）
        current_position = self.position_combo.currentText()

        # 根据切片类型更新位置选项和线性模式设置
        if slice_type == self.tr("垂直切片"):
            # 垂直切片：左侧、居中、右侧
            self.position_combo.clear()
            self.position_combo.addItems([
                self.tr("左侧"),
                self.tr("居中"),
                self.tr("右侧")
            ])
            # 恢复之前选择的位置（如果存在）
            position_index = self.position_combo.findText(current_position)
            if position_index >= 0:
                self.position_combo.setCurrentIndex(position_index)
            else:
                self.position_combo.setCurrentIndex(1)  # 默认居中

            # 垂直切片：线性模式控制是否从同一竖条位置裁切
            self.linear_switch.setEnabled(True)
            self.linear_top_label.setText(self.tr("取每张照片的同一位置后拼接"))
            self.linear_bottom_label.setText(self.tr("取每张照片的不同位置后拼接"))
            self.linear_switch.setChecked(False)
            self.refresh_linear_labels()

        elif slice_type == self.tr("水平切片"):
            # 水平切片：顶部、居中、底部
            self.position_combo.clear()
            self.position_combo.addItems([
                self.tr("顶部"),
                self.tr("居中"),
                self.tr("底部")
            ])
            # 恢复之前选择的位置（如果存在）
            position_index = self.position_combo.findText(current_position)
            if position_index >= 0:
                self.position_combo.setCurrentIndex(position_index)
            else:
                self.position_combo.setCurrentIndex(1)  # 默认居中

            # 水平切片：线性模式控制是否从同一横条位置裁切
            self.linear_switch.setEnabled(True)
            self.linear_top_label.setText(self.tr("取每张照片的同一位置后拼接"))
            self.linear_bottom_label.setText(self.tr("取每张照片的不同位置后拼接"))
            self.linear_switch.setChecked(False)
            self.refresh_linear_labels()

        elif slice_type == self.tr("圆形扇形切片"):
            # 位置选项不可用
            self.position_combo.clear()
            self.position_combo.addItem(self.tr("居中"))
            self.position_combo.setCurrentIndex(0)
            self.position_combo.setEnabled(False)

            # 圆形扇形切片：线性模式控制是否从同一扇形大小裁切
            self.linear_switch.setEnabled(True)
            self.linear_top_label.setText(self.tr("取每张照片的同一大小后拼接"))
            self.linear_bottom_label.setText(self.tr("取每张照片的不同大小后拼接"))
            self.linear_switch.setChecked(False)
            self.refresh_linear_labels()

        elif slice_type == self.tr("椭圆形扇形切片"):
            # 位置选项不可用
            self.position_combo.clear()
            self.position_combo.addItem(self.tr("居中"))
            self.position_combo.setCurrentIndex(0)
            self.position_combo.setEnabled(False)

            # 椭圆形扇形切片：线性模式控制是否从同一椭圆大小裁切
            self.linear_switch.setEnabled(True)
            self.linear_top_label.setText(self.tr("取每张照片的同一大小后拼接"))
            self.linear_bottom_label.setText(self.tr("取每张照片的不同大小后拼接"))
            self.linear_switch.setChecked(False)
            self.refresh_linear_labels()

        elif slice_type == self.tr("垂直S型曲线"):
            # 垂直S型曲线：同一位置模式下可选左侧/居中/右侧；不同位置模式禁用
            self.position_combo.clear()
            self.position_combo.addItems([
                self.tr("左侧"),
                self.tr("居中"),
                self.tr("右侧")
            ])
            # 恢复之前选择的位置（如果存在）
            position_index = self.position_combo.findText(current_position)
            if position_index >= 0:
                self.position_combo.setCurrentIndex(position_index)
            else:
                self.position_combo.setCurrentIndex(1)  # 默认居中

            # 垂直S型曲线：线性模式控制是否从同一竖向位置裁切
            self.linear_switch.setEnabled(True)
            self.linear_top_label.setText(self.tr("取每张照片的同一位置后拼接"))
            self.linear_bottom_label.setText(self.tr("取每张照片的不同位置后拼接"))
            self.linear_switch.setChecked(False)
            self.refresh_linear_labels()

        elif slice_type == self.tr("水平S型曲线"):
            # 水平S型曲线：同一位置模式下可选顶部/居中/底部；不同位置模式禁用
            self.position_combo.clear()
            self.position_combo.addItems([
                self.tr("顶部"),
                self.tr("居中"),
                self.tr("底部")
            ])
            # 恢复之前选择的位置（如果存在）
            position_index = self.position_combo.findText(current_position)
            if position_index >= 0:
                self.position_combo.setCurrentIndex(position_index)
            else:
                self.position_combo.setCurrentIndex(1)  # 默认居中

            # 水平S型曲线：线性模式控制是否从同一横向位置裁切
            self.linear_switch.setEnabled(True)
            self.linear_top_label.setText(self.tr("取每张照片的同一位置后拼接"))
            self.linear_bottom_label.setText(self.tr("取每张照片的不同位置后拼接"))
            self.linear_switch.setChecked(False)
            self.refresh_linear_labels()

        else:
            # 其他切片类型：位置选项不可用
            self.position_combo.clear()
            self.position_combo.addItem(self.tr("居中"))
            self.position_combo.setCurrentIndex(0)
            self.position_combo.setEnabled(False)

            # 环带类型不支持线性模式
            self.linear_switch.setChecked(False)
            self.linear_switch.setEnabled(False)
            self.linear_top_label.setText("")
            self.linear_bottom_label.setText(self.tr("该切片类型不使用此选项"))
            self.refresh_linear_labels()

        # 更新位置选项的启用状态（考虑线性模式）
        self.update_position_combo_state()

    def update_linear_mode_state(self):
        """更新线性模式开关状态变化时的控件状态"""
        # 更新位置组合框的启用状态
        self.update_position_combo_state()
        # 更新右侧选项文字的高亮状态
        self.refresh_linear_labels()

    def update_position_combo_state(self):
        """更新位置组合框的启用状态"""
        slice_type = self.type_combo.currentText()
        is_linear = self.linear_switch.isChecked()

        # 垂直/水平切片以及垂直/水平 S 型曲线，在未启用线性模式时，位置选项才可用
        if slice_type in [self.tr("垂直切片"), self.tr("水平切片"),
                          self.tr("垂直S型曲线"), self.tr("水平S型曲线")] and not is_linear:
            self.position_combo.setEnabled(True)
        else:
            self.position_combo.setEnabled(False)

    def refresh_linear_labels(self):
        """根据开关状态高亮右侧对应的选项文字"""
        palette = self.palette()
        highlight = palette.color(QPalette.ColorRole.Highlight).name()
        normal = palette.color(QPalette.ColorRole.WindowText).name()
        disabled = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText).name()

        if not self.linear_switch.isEnabled():
            self.linear_top_label.setStyleSheet(f"color: {disabled}; font-weight: normal;")
            self.linear_bottom_label.setStyleSheet(f"color: {disabled}; font-weight: normal;")
            return

        if self.linear_switch.isChecked():
            self.linear_top_label.setStyleSheet(f"color: {normal}; font-weight: normal;")
            self.linear_bottom_label.setStyleSheet(f"color: {highlight}; font-weight: bold;")
        else:
            self.linear_top_label.setStyleSheet(f"color: {highlight}; font-weight: bold;")
            self.linear_bottom_label.setStyleSheet(f"color: {normal}; font-weight: normal;")

    def select_input_dir(self):
        """选择输入目录"""
        dir_path = QFileDialog.getExistingDirectory(self, self.tr("选择输入目录"))
        if dir_path:
            self.input_dir_edit.setText(dir_path)
            self.update_filename_preview()

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(self, self.tr("选择输出目录"))
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    # ---------- 实时预览 ----------
    def _get_current_preview_params(self):
        """收集当前参数用于预览"""
        return {
            'input_dir': self.input_dir_edit.text(),
            'slice_type': self._l_slice_type.get(self.type_combo.currentText(), "vertical"),
            'position': self._l_position.get(self.position_combo.currentText(), "center"),
            'linear': self.linear_switch.isChecked(),
            'sort_by': self._l_sort.get(self.sort_combo.currentText(), "name"),
            'reverse': self.reverse_check.isChecked(),
            'fit_strategy': self._l_fit.get(self.fit_combo.currentText(), FIT_SCALE_CENTER),
        }

    def _schedule_preview(self):
        """参数变化时调度预览刷新（防抖）"""
        if not self.input_dir_edit.text():
            return
        self._preview_timer.start()

    def _refresh_preview(self):
        """执行预览刷新（跳过模式：旧线程运行中则放弃本次，不 terminate、不堆积）"""
        input_dir = self.input_dir_edit.text()
        if not input_dir:
            self.preview_canvas.setText(self.tr("请选择输入目录"))
            self.preview_status_label.setText("")
            return

        # 跳过模式：旧预览线程仍在运行则放弃本次刷新（防抖 300ms 会在
        # 下次参数变化时重新触发；旧线程完成后由 _on_preview_ready 检查
        # _preview_pending 自动补刷，不丢最终结果）
        if self.preview_worker is not None and self.preview_worker.isRunning():
            self._preview_pending = True
            return

        self._preview_pending = False
        # 用请求序号淘汰过期的预览结果
        self._preview_request_seq += 1
        params = self._get_current_preview_params()
        params['max_images'] = 8
        params['preview_max_side'] = 320

        self.preview_status_label.setText(self.tr("正在生成预览..."))
        self.preview_worker = PreviewWorker(params, self._preview_request_seq, self)
        self.preview_worker.preview_ready.connect(self._on_preview_ready)
        self.preview_worker.preview_failed.connect(self._on_preview_failed)
        self.preview_worker.start()

    def _on_preview_ready(self, pixmap, seq):
        """预览生成完成（仅接受当前 worker + 最新一次请求的结果）"""
        # sender 防御：旧线程（重建 UI 前的实例）的信号即使漏到此处也直接忽略
        if self.sender() is not self.preview_worker:
            return
        if seq != self._preview_request_seq:
            return
        self.preview_status_label.setText(self.tr("实时预览（使用前 8 张图片）"))
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.preview_canvas.width(), self.preview_canvas.height(),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_canvas.setPixmap(scaled)
        self._flush_preview_pending()

    def _on_preview_failed(self, error_msg, seq):
        """预览生成失败（仅接受当前 worker + 最新一次请求的结果），记录详细错误到日志"""
        if self.sender() is not self.preview_worker:
            return
        if seq != self._preview_request_seq:
            return
        self.preview_status_label.setText("")
        self.preview_canvas.setText(self.tr("预览失败"))
        self.error_log.append(f"{self.tr('预览失败:')} {error_msg}")
        self._flush_preview_pending()

    def _flush_preview_pending(self):
        """跳过模式下，旧线程完成后再补刷最新一次被跳过的参数"""
        if self._preview_pending:
            self._preview_pending = False
            self._refresh_preview()

    def process_images(self):
        """处理图片"""
        # 守卫：工作线程仍在运行时禁止重复启动（防止多实例并发写同一输出目录）
        if self.worker is not None and self.worker.isRunning():
            self.status_bar.showMessage(self.tr("正在处理中，请等待完成或取消"))
            return

        input_dir = self.input_dir_edit.text()
        output_dir = self.output_dir_edit.text()

        if not input_dir:
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择输入目录"))
            return

        if not output_dir:
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择输出目录"))
            return

        # 映射切片类型 / 位置 / 排序 / 时间戳来源 / 扩展名 / 尺寸适配（使用本地化映射缓存）
        slice_type = self._l_slice_type.get(self.type_combo.currentText(), "vertical")
        position = self._l_position.get(self.position_combo.currentText(), "center")
        sort_by = self._l_sort.get(self.sort_combo.currentText(), "name")
        timestamp_source = self._l_timestamp_source.get(self.timestamp_source_combo.currentText(), "composition")
        extension = EXTENSION_MAP.get(self.extension_combo.currentText(), "jpg")
        fit_strategy = self._l_fit.get(self.fit_combo.currentText(), FIT_SCALE_CENTER)

        # 准备参数
        params = {
            'input_dir': input_dir,
            'output_dir': output_dir,
            'slice_type': slice_type,
            'position': position,
            'linear': self.linear_switch.isChecked(),
            'reverse': self.reverse_check.isChecked(),
            'sort_by': sort_by,
            'output_basename': self.basename_edit.text().strip() or "timeslice",
            'include_timestamp': self.timestamp_check.isChecked(),
            'include_slice_type': self.slice_type_check.isChecked(),
            'extension': extension,
            'lang': self.current_lang,
            'timestamp_source': timestamp_source,
            'fit_strategy': fit_strategy
        }

        # 重置状态
        self.error_log.clear()
        self.process_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        # 读取目录完成前，进度条显示静止的 0%，不播放动画
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(self.tr("已处理 %v 张"))

        # 启动工作线程：图片加载与切片处理均在子线程完成。
        # 目录扫描由 Worker 内的 get_sorted_image_paths 单次完成（GUI 不再预扫描，避免双倍 I/O）；
        # 空目录/目录不存在等错误由 Worker 通过 error_signal 上报。
        self.worker = TimesliceWorker(params)
        self.worker.total_signal.connect(self.on_total_images)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.process_finished)
        self.worker.error_signal.connect(self.process_error)
        self.worker.log_signal.connect(self.log_message)
        self.worker.cancelled_signal.connect(self.process_cancelled)
        self.worker.start()
        # 任务在跑时语言菜单置灰（禁止切换重建 UI）
        self.update_menu_check_state()

    def update_progress(self, value):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.status_bar.showMessage(f"{self.tr('已处理')} {value}/{self.total_images} {self.tr('张图片')}")

    def on_total_images(self, total):
        """工作线程加载完成后刷新总数与进度条范围（#5）"""
        self.total_images = total
        self.progress_bar.setRange(0, total)
        self.progress_bar.setFormat(self.tr("已处理 %v/%m 张"))
        self.progress_bar.setValue(0)

    def log_message(self, message):
        """日志消息"""
        self.status_bar.showMessage(message)

    def cancel_processing(self):
        """请求取消当前处理任务"""
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_bar.showMessage(self.tr("正在取消..."))

    def process_cancelled(self):
        """任务被用户取消"""
        self.error_log.append(self.tr("任务已被取消"))
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_bar.showMessage(self.tr("任务已取消"))
        # 任务结束，恢复语言菜单可用
        self.update_menu_check_state()

    def process_error(self, error_msg):
        """处理错误"""
        self.error_log.append(f"{self.tr('错误:')} {error_msg}")
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_bar.showMessage(self.tr("处理出错"))
        # 任务结束，恢复语言菜单可用
        self.update_menu_check_state()

    def process_finished(self, output_path):
        """处理完成"""
        self.status_bar.showMessage(f"{self.tr('时间切片已保存至:')} {output_path}")
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        # 任务结束，恢复语言菜单可用
        self.update_menu_check_state()

        # Windows自动打开图片
        if self.auto_open_check.isChecked():
            try:
                os.startfile(output_path)
            except Exception as e:
                self.error_log.append(f"{self.tr('无法打开图片:')} {str(e)}")

    def closeEvent(self, event):
        """关闭窗口时优雅退出后台线程，保证输出文件完整性（#4）

        策略：
        - 切片任务：先请求取消（进度回调逐张检查，很快退出）；save 阶段不打断；
          等待 10s 仍未结束则拒绝关闭（event.ignore）并提示用户先取消，避免
          QThread.terminate() 中断 PIL 写入造成文件损坏或进程崩溃。
        - 预览/时间戳线程：requestInterruption + 短等待自然结束（不强制终止）。
        """
        self._preview_timer.stop()
        self._ts_timer.stop()

        # 切片任务：优雅取消，超时拒绝关闭
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(10000):
                # 保存阶段或极端情况无法及时退出：拒绝关闭，保护文件完整性
                QMessageBox.warning(self, self.tr("警告"),
                                    self.tr("图片正在生成中，请先点击\"取消处理\"后再关闭程序"))
                event.ignore()
                return

        # 预览/时间戳线程：断开信号连接 + 请求中断 + 等待自然结束。
        # 窗口即将销毁，必须确保线程完全停止，否则 QThread 对象随窗口销毁
        # 时若仍在运行会触发崩溃；信号已断开保证中途 emit 不会访问已销毁控件。
        self._stop_background_threads(timeout_ms=3000)
        # 极端情况仍运行：继续等待直到结束（预览/时间戳任务量小，通常不会发生）
        if self.preview_worker is not None and self.preview_worker.isRunning():
            self.preview_worker.wait()
        if self._ts_worker is not None and self._ts_worker.isRunning():
            self._ts_worker.wait()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    app.setStyle("Fusion")
    window = TimesliceGUI()
    window.show()
    sys.exit(app.exec())
