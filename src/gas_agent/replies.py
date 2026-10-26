"""所有回覆的文字格式。"""


def num(value: float | None, decimals: int = 0, missing: str = "—") -> str:
    if value is None:
        return missing
    return f"{value:,.{decimals}f}"


def summary_text(stats: dict) -> str:
    """個人累積總統計（一行純文字；Excel 的「個人累積總統計」欄與回覆都用這個）。"""
    if not stats["has_data"]:
        return "累積：目前還沒有可統計的紀錄"
    parts = [
        f"加油 {stats['fuel_count']} 次",
        f"總花費 {num(stats['total_cost'])} 元",
        f"總里程 {num(stats['total_km'])} km" if stats["total_km"] else "總里程 尚無法計算",
        f"歷史平均油耗 {num(stats['avg_kml'], 1)} km/L" if stats["avg_kml"] else "歷史平均油耗 尚無法計算",
    ]
    if stats["maint_count"]:
        parts.append(f"保養 {stats['maint_count']} 次共 {num(stats['maint_cost'])} 元")
    if stats["suspect_count"]:
        parts.append(f"含 {stats['suspect_count']} 筆可疑")
    return "累積：" + "｜".join(parts)


def recognized_line(row: dict) -> str:
    """辨識到的數值。讀不到的欄位明講「讀不到」。"""
    kind = row["type"]
    odo = f"里程 {num(row.get('odometer'))} km" if row.get("odometer") else "里程 讀不到"
    if kind == "加油":
        liters = f"加油量 {num(row.get('liters'), 1)} L" if row.get("liters") else "加油量 讀不到"
        cost = f"金額 {num(row.get('cost'))} 元" if row.get("cost") else "金額 讀不到"
        tag = "（沒加滿）" if row.get("full") == "否" else "（加滿）"
        return f"辨識到：{odo}｜{liters}｜{cost}{tag}"
    if kind == "保養":
        item = f"保養項目 {row['maint_item']}" if row.get("maint_item") else "保養項目 讀不到"
        cost = f"金額 {num(row.get('cost'))} 元" if row.get("cost") else "金額 讀不到"
        parts = [item, cost] + ([odo] if row.get("odometer") else [])
        return "辨識到：" + "｜".join(parts)
    return f"辨識到：{odo}"


def calc_line(row: dict) -> str:
    parts = []
    if row.get("trip"):
        parts.append(f"行駛 {num(row['trip'])} km")
    if row.get("kml"):
        parts.append(f"平均油耗 {num(row['kml'], 1)} km/L")
    if row.get("cost_per_km"):
        parts.append(f"每公里成本 {num(row['cost_per_km'], 2)} 元/km")
    return ("本次計算：" + "｜".join(parts)) if parts else ""


def record_reply(row: dict, stats: dict, notes: list[str], header: str = "✅ 已記錄") -> str:
    lines = [f"{header}（{row['type']}）", recognized_line(row)]
    calc = calc_line(row)
    if calc:
        lines.append(calc)
    lines.extend(notes)
    lines.append("📊 " + summary_text(stats))
    return "\n".join(lines)


def non_target_reply(description: str, stats: dict) -> str:
    what = description or "無法辨識的東西"
    return "\n".join(
        [
            f"🤔 你傳的不是加油收據、儀表板或保養單據照片，是「{what}」。",
            "我還是幫你建了檔、存了照片（紀錄類型：非目標照片）。要記帳的話，請重新傳清楚的儀表板或收據照片。",
            "📊 " + summary_text(stats),
        ]
    )


def stats_reply(username: str, stats: dict) -> str:
    if not stats["has_data"]:
        return "你還沒有任何紀錄。傳一張儀表板或加油收據照片就可以開始記帳了。"
    lines = [
        f"📊 {username} 的養車統計",
        f"總花費：{num(stats['total_cost'])} 元（加油＋保養）",
        f"總行駛里程：{num(stats['total_km'])} km" if stats["total_km"] else "總行駛里程：尚無法計算（至少要 2 筆里程）",
        f"歷史總平均油耗：{num(stats['avg_kml'], 1)} km/L" if stats["avg_kml"] else "歷史總平均油耗：尚無法計算（要有 2 次加滿的加油紀錄）",
        f"加油 {stats['fuel_count']} 次｜保養 {stats['maint_count']} 次（共 {num(stats['maint_cost'])} 元）",
    ]
    if stats["suspect_count"]:
        lines.append(f"⚠️ 其中 {stats['suspect_count']} 筆被標為可疑，不計入油耗與里程，請用 `!fix_last` 確認。")
    return "\n".join(lines)


FIX_USAGE = (
    "用法：`!fix_last 12400`（修正里程），或 `!fix_last 里程 12400`、`!fix_last 加油量 30.5`、`!fix_last 金額 960`。"
    "修正的是你最近一筆紀錄。"
)
