from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from gas_agent.parse_result import Analysis
from gas_agent.photos import ImageRejected, save_inbox_image, store_photo
from gas_agent.sanitize import clean_text, neutralize_formula, safe_filename_part
import io


def make_analysis(photo_type="other", description=""):
    return Analysis(photo_type != "other", photo_type, None, None, None, "", description)


@pytest.mark.parametrize(
    "dirty",
    ["../../evil", "..\\..\\evil", "C:\\x\\y", "a:b", "a/b", "ａ／ｂ", "CON", "nul", "a*b?c", "\n\t", "...", "/etc/passwd"],
)
def test_safe_filename_part_removes_path_characters(dirty):
    cleaned = safe_filename_part(dirty)
    for bad in ("/", "\\", "..", ":", "*", "?", '"', "<", ">", "|", "\n"):
        assert bad not in cleaned
    assert cleaned and len(cleaned) <= 11
    assert cleaned.upper() not in {"CON", "NUL"}


def test_safe_filename_part_keeps_chinese():
    assert safe_filename_part("馬克杯") == "馬克杯"
    assert safe_filename_part("a" * 50) == "a" * 10


@pytest.mark.parametrize("text", ["=1+1", "+cmd", "-2+3", "@SUM(1)", "\t=1"])
def test_neutralize_formula(text):
    assert neutralize_formula(text).startswith("'")


def test_neutralize_leaves_normal_text():
    assert neutralize_formula("grace") == "grace"
    assert neutralize_formula("換機油") == "換機油"


def test_clean_text_strips_controls_and_truncates():
    assert clean_text("a\nb\x00c", 100) == "a b c"
    assert len(clean_text("x" * 500, 100)) == 100


def png_bytes(size=(50, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_save_inbox_image_converts_to_jpeg(tmp_path):
    path = save_inbox_image(png_bytes(), tmp_path / "inbox")
    assert path.suffix == ".jpg"
    with Image.open(path) as im:
        assert im.format == "JPEG"


def test_save_inbox_image_rejects_non_image(tmp_path):
    with pytest.raises(ImageRejected):
        save_inbox_image(b"this is not an image", tmp_path / "inbox")


def test_store_photo_name_format_and_collision(tmp_path):
    when = datetime(2026, 10, 26, 15, 30, 12)
    photos = tmp_path / "photos"
    names = []
    for _ in range(3):
        src = save_inbox_image(png_bytes(), tmp_path / "inbox")
        dest = store_photo(src, photos, when, "123456789012345678", make_analysis("fuel_receipt"))
        names.append(dest.name)
    assert names == [
        "2026-10-26 15-30-12 123456789012345678 fuel.jpg",
        "2026-10-26 15-30-12 123456789012345678 fuel-2.jpg",
        "2026-10-26 15-30-12 123456789012345678 fuel-3.jpg",
    ]
    assert not any(":" in n for n in names)


def test_store_photo_non_target_description_cannot_escape(tmp_path):
    when = datetime(2026, 10, 26, 15, 30, 12)
    photos = tmp_path / "photos"
    src = save_inbox_image(png_bytes(), tmp_path / "inbox")
    dest = store_photo(src, photos, when, "42", make_analysis("other", "../../evil:x\\y"))
    assert dest.parent == photos.resolve() or dest.parent == photos
    assert dest.exists()
    assert not (tmp_path / "evil").exists()
    assert list(tmp_path.glob("*.jpg")) == []
