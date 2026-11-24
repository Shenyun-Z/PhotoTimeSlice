"""i18n 一致性测试：语言包 key 对齐、代码里用到的 key 必须存在、无空翻译。"""
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    with open(os.path.join(ROOT, "languages", name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def packs():
    return load("zh_CN.locpak"), load("en.locpak")


def test_pack_key_parity(packs):
    zh, en = packs
    assert set(zh) == set(en), "中英文语言包 key 不一致"


def test_no_empty_translation(packs):
    for name, pack in zip(("zh_CN", "en"), packs):
        empty = [k for k, v in pack.items() if not str(v).strip()]
        assert not empty, f"{name} 存在空翻译: {empty[:5]}"


def test_all_tr_literals_have_keys(packs):
    """代码里 tr("...") 出现的字面量都要在语言包里有对应条目。"""
    zh, en = packs
    used = set()
    pattern = re.compile(r'(?:self\.|translator\.)?tr\(\s*"((?:[^"\\]|\\.)*)"')
    for fname in ("gui.py", "cli.py", "utils.py"):
        src = open(os.path.join(ROOT, fname), encoding="utf-8").read()
        used |= set(pattern.findall(src))
    # 代码中的转义引号还原
    used = {u.replace('\\"', '"') for u in used}
    missing = sorted(u for u in used if u not in zh or u not in en)
    assert not missing, f"缺少翻译键: {missing[:8]}"


def test_translator_falls_back_to_key():
    from i18n import Translator
    t = Translator("zh_CN")
    assert t.tr("这个键一定不存在") == "这个键一定不存在"


def test_translator_cached_per_language():
    from i18n import get_translator
    a = get_translator("zh_CN")
    b = get_translator("zh_CN")
    assert a is b
    assert get_translator("en").tr("张图片") == "images"
