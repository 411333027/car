"""解析並驗證 claude -p 回傳的結果（架構文件第 5 節）。

任何不合格的狀況都只會丟出 AnalysisError，由呼叫的人決定怎麼回覆，程式本身不會因此當掉。
"""

import json
import math
from dataclasses import dataclass

from gas_agent.sanitize import clean_text

PHOTO_TYPES = ("dashboard", "fuel_receipt", "maintenance_receipt", "other")

# photo_type -> (紀錄類型, 檔名簡稱)
TYPE_LABELS = {
    "dashboard": ("儀表板", "dash"),
    "fuel_receipt": ("加油", "fuel"),
    "maintenance_receipt": ("保養", "maint"),
    "other": ("非目標照片", "other"),
}


class AnalysisError(Exception):
    """分析結果不能用（不是合法 JSON、欄位型別不對、數字不是數字…）。"""


@dataclass(frozen=True)
class Analysis:
    is_target: bool
    photo_type: str
    odometer_km: float | None
    fuel_liters: float | None
    cost: float | None
    maintenance_item: str
    description: str


def _extract_payload(stdout: str) -> dict:
    """從 claude -p 的外殼取出模型回答的那個 JSON 物件。"""
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AnalysisError("claude -p 的輸出不是 JSON") from exc
    if not isinstance(envelope, dict):
        raise AnalysisError("claude -p 的輸出格式不對")
    if envelope.get("is_error"):
        raise AnalysisError(f"claude -p 回報錯誤：{clean_text(envelope.get('result'), 200)}")

    structured = envelope.get("structured_output")
    if isinstance(structured, dict):
        return structured

    text = envelope.get("result")
    if not isinstance(text, str):
        raise AnalysisError("claude -p 沒有給出結果")
    # 模型可能多包了 ``` 或客套話：只截第一個 { 到最後一個 } 之間
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AnalysisError("結果裡找不到 JSON")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AnalysisError("結果不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise AnalysisError("結果不是 JSON 物件")
    return payload


def _number(payload: dict, key: str) -> float | None:
    """null 代表「照片上沒有／讀不到」，是正常的；給了值卻不是正數就是分析失敗。"""
    if key not in payload:
        raise AnalysisError(f"缺少欄位 {key}")
    value = payload[key]
    if value is None:
        return None
    if isinstance(value, bool):
        raise AnalysisError(f"{key} 不是數字")
    if isinstance(value, str):
        stripped = value.replace(",", "").strip()
        try:
            value = float(stripped)
        except ValueError as exc:
            raise AnalysisError(f"{key} 不是數字：{clean_text(value, 20)}") from exc
    if not isinstance(value, (int, float)):
        raise AnalysisError(f"{key} 不是數字")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise AnalysisError(f"{key} 不是合理的正數")
    return value


def parse_analysis(stdout: str) -> Analysis:
    payload = _extract_payload(stdout)

    photo_type = payload.get("photo_type")
    if photo_type not in PHOTO_TYPES:
        raise AnalysisError("photo_type 不在允許的類型內")
    is_target = payload.get("is_target")
    if not isinstance(is_target, bool):
        raise AnalysisError("is_target 不是真/假")
    if is_target != (photo_type != "other"):
        raise AnalysisError("is_target 與 photo_type 不一致")

    item = payload.get("maintenance_item")
    description = payload.get("description")
    return Analysis(
        is_target=is_target,
        photo_type=photo_type,
        odometer_km=_number(payload, "odometer_km"),
        fuel_liters=_number(payload, "fuel_liters"),
        cost=_number(payload, "cost"),
        maintenance_item=clean_text(item, 60) if isinstance(item, str) else "",
        description=clean_text(description, 100) if isinstance(description, str) else "",
    )
