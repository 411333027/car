"""文字清洗工具。

檔名清洗（防護 3）與 Excel 公式處理（防護 4）的「做法」寫在這裡，
但「有沒有被套用」是由 photos.py、storage.py 裡標了防護註解的那一段決定。
"""

import re
import unicodedata

_CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f" + chr(0x2028) + chr(0x2029) + "]")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "\n")


def clean_text(value: object, max_len: int = 100) -> str:
    """一般文字：去掉控制字元、頭尾空白、限制長度。不改變內容的意思。"""
    if value is None:
        return ""
    text = _CONTROL_CHARS.sub(" ", str(value))
    return " ".join(text.split())[:max_len]


def safe_filename_part(value: object, max_len: int = 10) -> str:
    """把 AI 回傳的說明清成可以放進檔名的一小段（防護 3 使用）。

    只留中文、英數、底線、減號；斜線、反斜線、兩個點、冒號以及所有 Windows 不允許的字都會被換掉或移除。
    """
    # 全形的斜線、反斜線、冒號等會被 NFKC 轉成真的半形字元，所以要先轉再清
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("..", "")
    text = re.sub("[^0-9A-Za-z_\\-" + chr(0x4E00) + "-" + chr(0x9FFF) + "]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_.- ")
    text = text[:max_len].strip("_.- ")
    if not text:
        return "other"
    if text.upper() in _WINDOWS_RESERVED:
        text = "_" + text
    return text


def neutralize_formula(value: str) -> str:
    """Excel 公式注入處理（防護 4 使用）：以 = + - @ 開頭的文字前面加單引號。"""
    if value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value
