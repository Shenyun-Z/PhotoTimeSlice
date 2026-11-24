"""GUI 无头冒烟测试。

未安装 PyQt6 的环境（例如精简 CI）会自动跳过，不影响核心逻辑的测试。
"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


@pytest.fixture
def gui(app, tmp_path):
    import gui as gui_module
    QSettings("TimeslicePhotoGenerator", "Settings").clear()
    w = gui_module.TimesliceGUI()
    w.show()
    yield w
    w.close()
    QSettings("TimeslicePhotoGenerator", "Settings").clear()


def test_window_constructs_with_nine_slice_types(gui):
    assert gui.type_combo.count() == 9
    assert gui.fit_combo.count() == 4
    assert gui.extension_combo.count() == 3


def test_control_state_machine_per_slice_type(gui):
    """位置/线性开关的可用状态应与切片类型匹配。"""
    expect = {0: (True, True), 1: (True, True), 2: (False, True), 3: (False, True),
              4: (False, False), 5: (False, False), 6: (False, False),
              7: (True, True), 8: (True, True)}
    for idx, (pos_enabled, linear_enabled) in expect.items():
        gui.type_combo.setCurrentIndex(idx)
        gui.update_controls_state(idx)
        assert gui.linear_switch.isEnabled() == linear_enabled, f"idx={idx} 线性开关"
        if pos_enabled:
            # 位置在非线性的条带/S 型模式下可用
            gui.linear_switch.setChecked(False)
            gui.update_position_combo_state()
        assert gui.position_combo.isEnabled() == pos_enabled, f"idx={idx} 位置选项"


def test_filename_preview_updates(gui):
    gui.basename_edit.setText("demo")
    gui.update_filename_preview()
    assert gui.filename_preview.text().startswith("demo")


def test_language_switch_rebuilds_ui(gui):
    gui.change_language("en")
    assert gui.current_lang == "en"
    assert gui.type_combo.count() == 9
    gui.change_language("zh_CN")
    assert gui.current_lang == "zh_CN"


def test_end_to_end_generation(gui, make_photos, out_dir, app):
    folder = make_photos(n=4, size=(240, 180))
    gui.input_dir_edit.setText(str(folder))
    gui.output_dir_edit.setText(str(out_dir))
    gui.basename_edit.setText("gui_smoke")
    gui.type_combo.setCurrentIndex(0)

    result = {}
    gui.process_images()
    worker = gui.worker
    assert worker is not None
    worker.finished_signal.connect(lambda p: result.setdefault("out", p))
    worker.error_signal.connect(lambda e: result.setdefault("err", e))

    deadline = time.time() + 15
    while time.time() < deadline and not result:
        app.processEvents()
        time.sleep(0.01)

    assert "err" not in result, result.get("err")
    assert result.get("out", "").endswith(".jpg")
    assert os.path.exists(result["out"])
