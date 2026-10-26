"""agent 的核心邏輯（不碰 Discord）：處理照片、!stats、!chart、!fix_last。

和 Discord 的串接在 main.py；這樣核心可以用假資料直接測試。
"""

import asyncio
import logging
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from gas_agent import calc, replies
from gas_agent.charts import render_chart
from gas_agent.checks import suspicion_reasons
from gas_agent.config import Config
from gas_agent.intake import is_not_full
from gas_agent.parse_result import TYPE_LABELS, Analysis, AnalysisError
from gas_agent.photos import ImageRejected, save_inbox_image, store_photo
from gas_agent.sanitize import clean_text
from gas_agent.storage import RecordStore, StorageBusy, StorageError
from gas_agent.vision import analyze_photo

log = logging.getLogger(__name__)

Analyzer = Callable[[Path, str], Awaitable[Analysis]]

ANALYSIS_FAILED = "分析失敗，請再傳一次"
STORAGE_BUSY = "紀錄檔正被占用（可能開著 Excel），這筆沒有存。請關閉 Excel 後再傳一次。"
STORAGE_FAILED = "存檔時出了問題，這筆沒有存。請再傳一次。"

FIX_FIELDS = {
    "里程": "odometer", "odo": "odometer", "odometer": "odometer",
    "加油量": "liters", "油量": "liters", "liters": "liters",
    "金額": "cost", "花費": "cost", "cost": "cost",
}
FIX_LABELS = {"odometer": "里程", "liters": "加油量", "cost": "金額"}
FIX_ALLOWED = {
    "加油": {"odometer", "liters", "cost"},
    "儀表板": {"odometer"},
    "保養": {"odometer", "cost"},
}


@dataclass
class Reply:
    text: str
    ok: bool = True
    image: bytes | None = None


@dataclass
class Spec:
    """一筆要建立的紀錄（可能由 1～2 張照片合成）。"""

    kind: str
    items: list[tuple[Path, Analysis]]
    odometer: float | None = None
    liters: float | None = None
    cost: float | None = None
    maint_item: str = ""
    note: str = ""
    warnings: list[str] = field(default_factory=list)


def merge_photos(paths: list[Path], analyses: list[Analysis]) -> list[Spec]:
    """同一則訊息「儀表板＋加油收據」合成一筆加油；其他情況一張照片一筆。"""
    items = list(zip(paths, analyses))
    fuel = [i for i in items if i[1].photo_type == "fuel_receipt"]
    dash = [i for i in items if i[1].photo_type == "dashboard"]
    if len(items) == 2 and len(fuel) == 1 and len(dash) == 1:
        (_, fuel_a), (_, dash_a) = fuel[0], dash[0]
        return [
            Spec("加油", [dash[0], fuel[0]], dash_a.odometer_km or fuel_a.odometer_km, fuel_a.fuel_liters, fuel_a.cost)
        ]

    specs = []
    for path, a in items:
        kind = TYPE_LABELS[a.photo_type][0]
        if kind == "儀表板":
            specs.append(Spec(kind, [(path, a)], odometer=a.odometer_km))
        elif kind == "加油":
            specs.append(Spec(kind, [(path, a)], a.odometer_km, a.fuel_liters, a.cost))
        elif kind == "保養":
            specs.append(Spec(kind, [(path, a)], a.odometer_km, None, a.cost, a.maintenance_item))
        else:
            specs.append(Spec(kind, [(path, a)], note=a.description))
    return specs


def parse_fix_args(args: str) -> tuple[str, float]:
    """!fix_last 的參數：「12400」或「里程 12400」。不合格就丟 ValueError。"""
    tokens = (args or "").split()
    if len(tokens) == 1:
        field_key, number = "odometer", tokens[0]
    elif len(tokens) == 2 and tokens[0].lower() in FIX_FIELDS:
        field_key, number = FIX_FIELDS[tokens[0].lower()], tokens[1]
    else:
        raise ValueError(replies.FIX_USAGE)
    try:
        value = float(number.replace(",", ""))
    except ValueError as exc:
        raise ValueError(replies.FIX_USAGE) from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError("數字必須是大於 0 的數字。\n" + replies.FIX_USAGE)
    return field_key, value


class AgentCore:
    def __init__(self, config: Config, store: RecordStore, analyzer: Analyzer | None = None):
        self.config = config
        self.store = store
        self.analyzer = analyzer or self._default_analyzer

    async def _default_analyzer(self, path: Path, user_text: str) -> Analysis:
        return await analyze_photo(path, self.config.claude_model, self.config.data_dir, user_text)

    # ------------------------------------------------------------------ 照片
    async def handle_photos(
        self, user_id: str | int, username: str, when: datetime, images: list[bytes], text: str
    ) -> Reply:
        uid = str(int(user_id))
        inbox_paths: list[Path] = []
        try:
            try:
                for data in images:
                    inbox_paths.append(await asyncio.to_thread(save_inbox_image, data, self.config.inbox_dir))
            except ImageRejected:
                return Reply("這個檔案不是可以讀的圖片，請傳照片檔（jpg、png）", ok=False)

            try:
                analyses = [await self.analyzer(path, text) for path in inbox_paths]
            except AnalysisError as exc:
                log.warning("使用者 %s 的照片分析失敗：%s", uid, exc)
                return Reply(ANALYSIS_FAILED, ok=False)

            not_full = is_not_full(text)  # 訊息文字只在這裡被程式拿來認「沒加滿」
            parts: list[str] = []
            ok = True
            for spec in merge_photos(inbox_paths, analyses):
                try:
                    parts.append(await self._record(spec, uid, username, when, not_full))
                except StorageBusy:
                    parts.append(STORAGE_BUSY)
                    ok = False
                    break
                except (StorageError, OSError, ValueError) as exc:
                    log.error("存檔失敗：%s", exc)
                    parts.append(STORAGE_FAILED)
                    ok = False
                    break
            return Reply("\n\n".join(parts), ok=ok)
        finally:
            for path in inbox_paths:
                path.unlink(missing_ok=True)

    async def _record(self, spec: Spec, uid: str, username: str, when: datetime, not_full: bool) -> str:
        """建檔一筆：計算（調用這個人的歷史）→ 存照片 → 寫 Excel → 組回覆。"""
        rows = await asyncio.to_thread(self.store.rows_for_user, uid)  # 只取這個 user_id 的紀錄
        row = {
            "time": when.strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": uid,
            "username": clean_text(username, 40) or "(未命名)",
            "type": spec.kind,
            "odometer": spec.odometer,
            "liters": spec.liters,
            "cost": spec.cost,
            "full": ("否" if not_full else "是") if spec.kind == "加油" else "",
            "maint_item": spec.maint_item,
            "status": "完成",
            "note": clean_text(spec.note, 200),
        }
        notes: list[str] = []

        if spec.kind != "非目標照片":
            row.update(calc.compute_fields(rows, row))
            prev = calc.previous_valid_odometer(rows)
            notes = self._explain(row, prev, rows)
            reasons = suspicion_reasons(row, prev)
            if reasons:
                row["status"] = calc.SUSPECT
                row["note"] = clean_text("；".join(reasons), 200)
                notes.append(
                    "⚠️ 這筆數字看起來不太對：" + "；".join(reasons)
                    + "。暫不計入平均油耗與圖表，請用 `!fix_last` 確認。"
                )
            elif spec.kind == "加油" and not row["odometer"]:
                row["status"] = "待補里程"
                row["note"] = "缺里程，請用 !fix_last 里程 數字 補上"

        stats_after = calc.cumulative(rows + [row])
        row["summary"] = replies.summary_text(stats_after)

        saved: list[Path] = []
        try:
            for path, analysis in spec.items:
                saved.append(await asyncio.to_thread(
                    store_photo, path, self.config.photos_dir, when, uid, analysis))
            row["photo"] = " | ".join(
                os.path.relpath(p, self.config.data_dir).replace("\\", "/") for p in saved
            )
            await asyncio.to_thread(self.store.append_row, row)
        except Exception:
            for p in saved:  # 這筆沒存成，就不留下沒有對應紀錄的照片
                p.unlink(missing_ok=True)
            raise

        if spec.kind == "非目標照片":
            return replies.non_target_reply(row["note"], stats_after)
        return replies.record_reply(row, stats_after, notes)

    @staticmethod
    def _explain(row: dict, prev: float | None, rows_before: list[dict]) -> list[str]:
        """用白話說明「為什麼有些數字沒算出來」。"""
        notes: list[str] = []
        kind = row["type"]
        if not row["odometer"]:
            notes.append("里程讀不到，所以沒辦法算行駛距離和油耗。請用 `!fix_last 里程 數字` 補上。")
        elif prev is None:
            notes.append("這是你的第一筆里程紀錄，下次加油或傳儀表板就能算出行駛距離與油耗。")
        if kind == "加油":
            if not row["liters"]:
                notes.append("加油量讀不到，請用 `!fix_last 加油量 數字` 補上。")
            if not row["cost"]:
                notes.append("金額讀不到，請用 `!fix_last 金額 數字` 補上。")
            if row["full"] == "否":
                notes.append("這筆沒加滿，油耗會等下次加滿時一起算。")
            elif row["odometer"] and prev is not None and not row["kml"] and calc.baseline_index(rows_before) is None:
                notes.append("還沒有「加滿」的基準點，下次加滿就能算出油耗。")
        if kind == "保養":
            if not row["maint_item"]:
                notes.append("保養項目讀不到。")
            if not row["cost"]:
                notes.append("金額讀不到，請用 `!fix_last 金額 數字` 補上。")
        return notes

    # ------------------------------------------------------------------ 指令
    async def handle_stats(self, user_id: str | int, username: str) -> Reply:
        rows = await asyncio.to_thread(self.store.rows_for_user, str(int(user_id)))
        return Reply(replies.stats_reply(username, calc.cumulative(rows)))

    async def handle_chart(self, user_id: str | int, username: str) -> Reply:
        rows = await asyncio.to_thread(self.store.rows_for_user, str(int(user_id)))
        png = await asyncio.to_thread(render_chart, rows, username)
        if png is None:
            return Reply("資料還不夠畫圖。要有至少 2 筆算得出油耗的加油紀錄（每次都要加滿，並附上里程）。")
        return Reply("📈 你的歷史油耗趨勢", image=png)

    async def handle_fix_last(self, user_id: str | int, args: str, when: datetime) -> Reply:
        try:
            field_key, value = parse_fix_args(args)
        except ValueError as exc:
            return Reply(str(exc), ok=False)

        uid = str(int(user_id))
        rows = await asyncio.to_thread(self.store.rows_for_user, uid)
        idx = next((i for i in range(len(rows) - 1, -1, -1) if rows[i]["type"] != "非目標照片"), None)
        if idx is None:
            return Reply("你還沒有可以修正的紀錄。", ok=False)
        target, rows_before = rows[idx], rows[:idx]

        label = FIX_LABELS[field_key]
        if field_key not in FIX_ALLOWED[target["type"]]:
            return Reply(f"你最近一筆是「{target['type']}」，沒有「{label}」可以修。", ok=False)

        old = target[field_key]
        row = {**target, field_key: value}
        row.update(calc.compute_fields(rows_before, row))
        prev = calc.previous_valid_odometer(rows_before)
        reasons = suspicion_reasons(row, prev)

        change = f"{label}由 {replies.num(old, 1 if field_key == 'liters' else 0, '空白')} 改為 {value:g}（{when:%m-%d %H:%M}）"
        note = "；".join(filter(None, [target["note"], change]))
        if reasons:
            row["status"] = calc.SUSPECT
            note += "；仍可疑：" + "；".join(reasons)
        else:
            row["status"] = "已修正"
        row["note"] = clean_text(note, 300)
        row["summary"] = replies.summary_text(calc.cumulative(rows_before + [row] + rows[idx + 1 :]))

        updates = {k: row[k] for k in ("odometer", "liters", "cost", "trip", "kml", "cost_per_km", "status", "note", "summary")}
        try:
            await asyncio.to_thread(self.store.update_row, target["id"], updates)
        except StorageBusy:
            return Reply(STORAGE_BUSY.replace("這筆沒有存", "沒有修改成功"), ok=False)
        except StorageError as exc:
            log.error("修正失敗：%s", exc)
            return Reply("修改時出了問題，沒有修改成功。", ok=False)

        notes = [f"修改內容：{change}"]
        if reasons:
            notes.append("⚠️ 修正後數字看起來仍不太對：" + "；".join(reasons) + "。暫不計入平均油耗與圖表。")
        stats = calc.cumulative(rows_before + [row] + rows[idx + 1 :])
        return Reply(replies.record_reply(row, stats, notes, header="✅ 已修正最近一筆"))
