import json
import os
import sys
from functools import lru_cache
from pathlib import Path


def get_base_path():
    """获取正确的基础路径（兼容开发环境和打包环境）"""
    if getattr(sys, 'frozen', False):
        # 如果是打包的exe，使用临时解压目录
        base_path = sys._MEIPASS
    else:
        # 如果是开发环境，使用当前文件目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return base_path


class Translator:
    def __init__(self, lang='en'):
        self.translations = {}
        self.load_translations(lang)

    def load_translations(self, lang):
        """加载Windows系统的翻译文件"""
        try:
            base_path = get_base_path()
            lang_file = os.path.join(base_path, "languages", f"{lang}.locpak")

            # 如果找不到语言文件，尝试使用相对路径
            if not os.path.exists(lang_file):
                # 尝试在当前目录下查找
                current_dir = os.path.dirname(os.path.abspath(__file__))
                lang_file = os.path.join(current_dir, "languages", f"{lang}.locpak")

            if os.path.exists(lang_file):
                with open(lang_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
            else:
                # 尝试加载英文作为后备
                en_file = os.path.join(base_path, "languages", "en.locpak")
                if os.path.exists(en_file):
                    with open(en_file, 'r', encoding='utf-8') as f:
                        self.translations = json.load(f)
                else:
                    self.translations = {}
        except Exception:
            self.translations = {}

    def tr(self, text):
        """翻译文本"""
        return self.translations.get(text, text)


@lru_cache(maxsize=8)
def get_translator(lang: str = 'en') -> Translator:
    """获取按语言缓存的翻译器。

    语言包是静态 JSON，每张图片重复构造 Translator 会造成大量冗余磁盘 I/O
    （实测 150 张图约 58% 的耗时）。按 lang 缓存后只解析一次。
    """
    return Translator(lang)