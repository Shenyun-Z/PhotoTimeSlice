import os
import sys
import logging
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QComboBox, QLineEdit, QCheckBox, QFileDialog, QProgressBar,
                             QGroupBox, QMessageBox, QTextEdit, QMenuBar, QMenu, QAction)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QSettings, QTimer
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QMouseEvent

# 配置调试日志（可选）
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# 添加当前目录到系统路径
if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, application_path)

from cli import run_timeslice
from i18n import Translator  # 导入翻译器


class LogEvent(QEvent):
    """用于线程安全日志更新的自定义事件"""
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, text, is_error=False):
        super().__init__(LogEvent.EVENT_TYPE)
        self.text = text
        self.is_error = is_error


class TimesliceWorker(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        try:
            from utils import load_images
            images = load_images(self.params['input_dir'],
                                 self.params['sort_by'],
                                 self.params['reverse'],
                                 self.params.get('lang', 'en'))
            total_images = len(images)

            if total_images == 0:
                raise Exception(self.tr("输入目录中没有找到图片"))

            self.log_signal.emit(f"找到 {total_images} 张图片，开始处理...")

            def progress_callback(current):
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
                progress_callback=progress_callback
            )

            self.progress_signal.emit(total_images)
            self.finished_signal.emit(output_path)
        except Exception as e:
            self.error_signal.emit(str(e))

    def tr(self, text):
        """翻译方法（线程内）"""
        translator = Translator()
        return translator.tr(text)


class VerticalModeSwitch(QWidget):
    """竖向滑动开关：上下滑动切换两种模式"""
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._top_text = ""
        self._bottom_text = ""
        self._dragging = False
        self._press_pos = 0
        self.setFixedSize(40, 90)
        self.setCursor(Qt.PointingHandCursor)

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

    def mousePressEvent(self, event: QMouseEvent):
        if not self.isEnabled():
            return
        self._dragging = True
        self._press_pos = event.pos().y()
        mid = self.height() // 2
        self.setChecked(event.pos().y() > mid)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        palette = self.palette()
        w = self.width()
        track_w = 22
        track_h = 70
        track_x = (w - track_w) // 2
        track_y = 10

        # 轨道背景
        track_color = QColor("#e0e0e0") if self.isEnabled() else QColor("#b0b0b0")
        painter.setBrush(track_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_x, track_y, track_w, track_h, track_w // 2, track_w // 2)

        # 滑块
        knob_d = 18
        if self._checked:
            knob_y = track_y + track_h - knob_d - 2
        else:
            knob_y = track_y + 2
        knob_x = track_x + (track_w - knob_d) // 2

        if self.isEnabled():
            knob_color = palette.color(QPalette.Highlight)
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

        self.app = QApplication.instance()
        # 移除跟随系统，无需主题检测定时器
        self.theme_check_timer = QTimer()

        # 初始化主题 - 默认使用浅色
        self.current_theme = self.settings.value("theme", "light")

        self.init_ui()
        self.load_theme()

        self.setWindowTitle(self.tr("时间切片照片生成器"))
        self.setGeometry(100, 100, 800, 650)  # 增加高度以容纳新的UI元素

        self.current_output_path = ""
        self.total_images = 0
        self.worker = None

    def tr(self, text):
        """翻译方法"""
        return self.translator.tr(text)

    def apply_theme_style(self, theme_type):
        """应用Windows主题样式"""
        palette = QPalette()

        if theme_type == "dark":
            # Windows深色模式样式
            self.app.setStyle("Fusion")
            dark_color = QColor(45, 45, 45)
            light_color = QColor(180, 180, 180)

            # 主界面调色板
            palette.setColor(QPalette.Window, dark_color)
            palette.setColor(QPalette.WindowText, light_color)
            palette.setColor(QPalette.Base, QColor(30, 30, 30))
            palette.setColor(QPalette.AlternateBase, dark_color)
            palette.setColor(QPalette.ToolTipBase, light_color)
            palette.setColor(QPalette.ToolTipText, light_color)
            palette.setColor(QPalette.Text, light_color)
            palette.setColor(QPalette.Button, dark_color)
            palette.setColor(QPalette.ButtonText, light_color)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)

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
        logging.debug(f"加载主题设置：{theme}")

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
        logging.debug(f"切换主题到：{theme}")

        self.apply_theme_style(theme)
        # 更新菜单选中状态
        self.update_menu_check_state()

    def change_language(self, lang):
        """切换语言并更新菜单标记"""
        self.current_lang = lang
        self.settings.setValue("language", lang)
        self.translator.load_translations(lang)

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
        self.linear_switch.setChecked(state['linear'])
        self.reverse_check.setChecked(state['reverse'])
        self.auto_open_check.setChecked(state['auto_open'])
        self.timestamp_check.setChecked(state['timestamp'])
        self.slice_type_check.setChecked(state['slice_type'])
        self.timestamp_source_combo.setCurrentIndex(state['timestamp_source_index'])

        # 刷新依赖状态与文件名预览
        self.update_timestamp_source_state()
        self.update_filename_preview()

    def update_menu_check_state(self):
        """更新菜单选中标记（✓）"""
        # 更新主题菜单
        if hasattr(self, 'light_theme_action'):
            self.light_theme_action.setChecked(self.current_theme == "light")
            self.dark_theme_action.setChecked(self.current_theme == "dark")

        # 更新语言菜单
        if hasattr(self, 'chinese_action'):
            self.chinese_action.setChecked(self.current_lang == "zh_CN")
            self.english_action.setChecked(self.current_lang == "en")

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
        self.title_label.setAlignment(Qt.AlignCenter)
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

        # 生成按钮
        button_layout = QHBoxLayout()
        self.process_btn = QPushButton(self.tr("生成时间切片"))
        self.process_btn.clicked.connect(self.process_images)
        self.process_btn.setMinimumHeight(40)
        button_layout.addWidget(self.process_btn)
        main_layout.addLayout(button_layout)

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage(self.tr("准备就绪"))

        # 初始化控件状态
        self.update_controls_state(0)

        # 连接预览更新信号
        self.basename_edit.textChanged.connect(self.update_filename_preview)
        self.extension_combo.currentTextChanged.connect(self.update_filename_preview)
        self.timestamp_check.stateChanged.connect(self.update_timestamp_source_state)
        self.timestamp_source_combo.currentTextChanged.connect(self.update_filename_preview)
        self.slice_type_check.stateChanged.connect(self.update_filename_preview)
        self.type_combo.currentIndexChanged.connect(self.update_filename_preview)
        self.sort_combo.currentIndexChanged.connect(self.update_filename_preview)
        self.reverse_check.stateChanged.connect(self.update_filename_preview)
        self.input_dir_edit.textChanged.connect(self.update_filename_preview)

        # 初始化菜单选中状态 - 启动时自动选中中文和浅色模式
        self.update_menu_check_state()

    def update_filename_preview(self):
        """更新文件名预览（含真实时间戳来源）"""
        from utils import compute_timestamp

        # 获取当前设置
        basename = self.basename_edit.text().strip() or "timeslice"
        extension = self.extension_combo.currentText().lower()
        include_timestamp = self.timestamp_check.isChecked()
        include_slice_type = self.slice_type_check.isChecked()

        # 获取切片类型（文件名简称随语言切换）
        slice_type_map = {
            self.tr("垂直切片"): self.tr("垂直"),
            self.tr("水平切片"): self.tr("水平"),
            self.tr("圆形扇形切片"): self.tr("圆形扇形"),
            self.tr("椭圆形扇形切片"): self.tr("椭圆形扇形"),
            self.tr("椭圆形环带切片"): self.tr("椭圆形环带"),
            self.tr("矩形环带切片"): self.tr("矩形环带"),
            self.tr("圆形环带切片"): self.tr("圆形环带"),
            self.tr("垂直S型曲线"): self.tr("垂直S型"),
            self.tr("水平S型曲线"): self.tr("水平S型")
        }
        slice_type_text = slice_type_map.get(self.type_combo.currentText(), "")

        # 排序映射
        sort_map = {
            self.tr("按文件名"): "name",
            self.tr("按创建时间"): "created_time",
            self.tr("按修改时间"): "modified_time"
        }
        sort_by = sort_map.get(self.sort_combo.currentText(), "name")

        # 构建文件名部分
        parts = [basename]

        if include_timestamp:
            source_map = {
                self.tr("第一张照片拍摄时间"): "first_capture",
                self.tr("最后一张照片拍摄时间"): "last_capture",
                self.tr("第一张照片修改时间"): "first_modified",
                self.tr("最后一张照片修改时间"): "last_modified",
                self.tr("时间切片合成时间"): "composition"
            }
            source = source_map.get(self.timestamp_source_combo.currentText(), "composition")
            ts = compute_timestamp(source, self.input_dir_edit.text(), sort_by, self.reverse_check.isChecked())
            if ts is None:
                ts = "YYYYMMDD_HHMMSS"
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
        highlight = palette.color(QPalette.Highlight).name()
        normal = palette.color(QPalette.WindowText).name()
        disabled = palette.color(QPalette.Disabled, QPalette.WindowText).name()

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

    def process_images(self):
        """处理图片"""
        input_dir = self.input_dir_edit.text()
        output_dir = self.output_dir_edit.text()

        if not input_dir:
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择输入目录"))
            return

        if not output_dir:
            QMessageBox.warning(self, self.tr("警告"), self.tr("请选择输出目录"))
            return

        # 映射切片类型
        slice_type_map = {
            self.tr("垂直切片"): "vertical",
            self.tr("水平切片"): "horizontal",
            self.tr("圆形扇形切片"): "circular_sector",
            self.tr("椭圆形扇形切片"): "elliptical_sector",
            self.tr("椭圆形环带切片"): "elliptical_band",
            self.tr("矩形环带切片"): "rectangular_band",
            self.tr("圆形环带切片"): "circular_band",
            self.tr("垂直S型曲线"): "vertical_s",
            self.tr("水平S型曲线"): "horizontal_s"
        }

        slice_type = slice_type_map.get(self.type_combo.currentText(), "vertical")

        # 映射位置
        position_map = {
            self.tr("左侧"): "left",
            self.tr("居中"): "center",
            self.tr("右侧"): "right",
            self.tr("顶部"): "top",
            self.tr("底部"): "bottom"
        }
        position = position_map.get(self.position_combo.currentText(), "center")

        # 映射排序规则
        sort_map = {
            self.tr("按文件名"): "name",
            self.tr("按创建时间"): "created_time",
            self.tr("按修改时间"): "modified_time"
        }
        sort_by = sort_map.get(self.sort_combo.currentText(), "name")

        # 映射时间戳来源
        timestamp_source_map = {
            self.tr("第一张照片拍摄时间"): "first_capture",
            self.tr("最后一张照片拍摄时间"): "last_capture",
            self.tr("第一张照片修改时间"): "first_modified",
            self.tr("最后一张照片修改时间"): "last_modified",
            self.tr("时间切片合成时间"): "composition"
        }
        timestamp_source = timestamp_source_map.get(self.timestamp_source_combo.currentText(), "composition")

        # 获取文件扩展名
        extension_map = {
            "JPG": "jpg",
            "PNG": "png",
            "WebP": "webp"
        }
        extension = extension_map.get(self.extension_combo.currentText(), "jpg")

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
            'timestamp_source': timestamp_source
        }

        # 重置状态
        self.error_log.clear()
        self.process_btn.setEnabled(False)
        # 读取目录完成前，进度条显示静止的 0%，不播放动画
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(self.tr("已处理 %v 张"))

        # 加载图片
        from utils import load_images
        try:
            images = load_images(input_dir, sort_by, self.reverse_check.isChecked(), self.current_lang)
            self.total_images = len(images)
            # 目录读取完成后才显示总照片数
            self.progress_bar.setRange(0, self.total_images)
            self.progress_bar.setFormat(self.tr("已处理 %v/%m 张"))
            self.progress_bar.setValue(0)

            if self.total_images == 0:
                QMessageBox.warning(self, self.tr("警告"), self.tr("输入目录中没有找到图片"))
                self.process_btn.setEnabled(True)
                return
        except Exception as e:
            self.error_log.append(f"{self.tr('错误:')} {str(e)}")
            self.process_btn.setEnabled(True)
            return

        # 启动线程
        self.worker = TimesliceWorker(params)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.process_finished)
        self.worker.error_signal.connect(self.process_error)
        self.worker.log_signal.connect(self.log_message)
        self.worker.start()

    def update_progress(self, value):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.status_bar.showMessage(f"{self.tr('已处理')} {value}/{self.total_images} {self.tr('张图片')}")

    def log_message(self, message):
        """日志消息"""
        self.status_bar.showMessage(message)

    def process_error(self, error_msg):
        """处理错误"""
        self.error_log.append(f"{self.tr('错误:')} {error_msg}")
        self.process_btn.setEnabled(True)
        self.status_bar.showMessage(self.tr("处理出错"))

    def process_finished(self, output_path):
        """处理完成"""
        self.status_bar.showMessage(f"{self.tr('时间切片已保存至:')} {output_path}")
        self.process_btn.setEnabled(True)

        # Windows自动打开图片
        if self.auto_open_check.isChecked():
            try:
                os.startfile(output_path)
            except Exception as e:
                self.error_log.append(f"{self.tr('无法打开图片:')} {str(e)}")

    def closeEvent(self, event):
        """关闭窗口"""
        self.theme_check_timer.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
    app.setStyle("Fusion")
    window = TimesliceGUI()
    window.show()
    sys.exit(app.exec_())