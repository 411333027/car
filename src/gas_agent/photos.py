"""照片：下載後驗證並轉成 JPEG，分析完再依規則命名、存進 DATA_DIR/photos。

這個檔案有一段防護：
- 防護 3：AI 回傳的說明拿去當檔名前，先清掉斜線、反斜線、兩個點、冒號等會讓路徑亂跑的字
"""

import io
import os
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from gas_agent.config import MAX_IMAGE_PIXELS
from gas_agent.parse_result import TYPE_LABELS, Analysis
from gas_agent.sanitize import safe_filename_part

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ImageRejected(Exception):
    """檔案不是可用的圖片。"""


def save_inbox_image(data: bytes, inbox_dir: Path) -> Path:
    """確認真的是圖片，縮到合理大小，轉成 JPEG 放進 inbox。檔名用亂數，不用使用者原檔名。"""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > MAX_IMAGE_PIXELS:
                raise ImageRejected("圖片的像素太大")
            im = ImageOps.exif_transpose(im)  # 手機照片常靠 EXIF 記錄方向
            im = im.convert("RGB")
            im.thumbnail((2048, 2048))  # 夠看清楚數字，又不會讓分析太慢
            inbox_dir.mkdir(parents=True, exist_ok=True)
            path = inbox_dir / f"{uuid.uuid4().hex}.jpg"
            im.save(path, "JPEG", quality=90)
            return path
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageRejected("這個檔案不是可以讀的圖片") from exc


def _type_abbr(analysis: Analysis, description: str) -> str:
    """類型簡稱：儀表板/加油/保養用固定對照表；非目標照片用「other-清洗過的說明」。"""
    abbr = TYPE_LABELS[analysis.photo_type][1]
    if analysis.photo_type == "other":
        return f"other-{description}" if description else "other"
    return abbr


def _reserve_path(photos_dir: Path, stem: str) -> Path:
    """用「只在檔案不存在時才建立」的方式佔一個檔名；撞名就加 -2、-3，絕不覆蓋既有照片。"""
    photos_dir.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        name = f"{stem}.jpg" if n == 1 else f"{stem}-{n}.jpg"
        path = photos_dir / name
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1
            continue
        os.close(fd)
        return path


def store_photo(inbox_path: Path, photos_dir: Path, when: datetime, user_id: str, analysis: Analysis) -> Path:
    """把 inbox 裡的照片搬進 photos/，檔名：YYYY-MM-DD hh-mm-ss 使用者ID 類型簡稱.jpg"""
    description = analysis.description
    path_must_stay_inside = False

    # ===== 防護 3：檔名清洗 開始 =====
    # 說明是 AI 看圖後回的字，照片上的人可以故意寫成 ../../evil 之類，所以先清乾淨：
    # 只留中文、英數、_、-，最多 10 個字；清完再確認最後的路徑真的落在 photos/ 底下。
    description = safe_filename_part(description)
    path_must_stay_inside = True
    # ===== 防護 3 結束 =====

    stem = f"{when:%Y-%m-%d %H-%M-%S} {int(user_id)} {_type_abbr(analysis, description)}"
    dest = _reserve_path(photos_dir, stem)
    if path_must_stay_inside:
        if Path(os.path.commonpath([photos_dir.resolve(), dest.resolve()])) != photos_dir.resolve():
            dest.unlink(missing_ok=True)
            raise ValueError("照片路徑跑到 photos 資料夾外面")
    os.replace(inbox_path, dest)
    return dest
