"""數值運算與調用歷史（架構文件 8.5）。

【評分：數值運算】本次行駛距離、平均油耗(km/L)、每公里成本(元/km)
【評分：調用歷史】用「這個人」的上一筆有效里程與基準點算；累積統計用全部歷史算

這裡的函式只收「已經是這個人自己的」紀錄列表（由 storage.rows_for_user 依 user_id 取得），
所以不可能算到別人的資料。
"""

SUSPECT = "可疑"


def is_valid(row: dict) -> bool:
    """有效紀錄：不是「可疑」的。可疑的紀錄不當作「上一筆」，也不算進油耗。"""
    return row.get("status") != SUSPECT


def previous_valid_odometer(rows_before: list[dict]) -> float | None:
    """【評分：調用歷史】該使用者上一筆有效里程。"""
    for row in reversed(rows_before):
        if is_valid(row) and row.get("odometer"):
            return row["odometer"]
    return None


def _is_full_fill(row: dict) -> bool:
    return row.get("type") == "加油" and row.get("full") == "是" and bool(row.get("odometer"))


def baseline_index(rows_before: list[dict]) -> int | None:
    """基準點：最近一次「加滿」且有里程的有效加油紀錄。"""
    for i in range(len(rows_before) - 1, -1, -1):
        if is_valid(rows_before[i]) and _is_full_fill(rows_before[i]):
            return i
    return None


def compute_fields(rows_before: list[dict], row: dict) -> dict:
    """【評分：數值運算】算這一筆的 trip、kml、cost_per_km。算不出來的給 None。"""
    odo = row.get("odometer")

    # 本次行駛距離 = 當前里程 - 該使用者上次里程
    prev = previous_valid_odometer(rows_before)
    trip = None
    if odo and prev and odo > prev:
        trip = odo - prev

    # 平均油耗 = 基準點到現在的總距離 ÷ 這段期間的總加油量（沒加滿的會累積進來）
    kml = None
    if _is_full_fill(row) and row.get("liters"):
        base_i = baseline_index(rows_before)
        if base_i is not None and odo > rows_before[base_i]["odometer"]:
            distance = odo - rows_before[base_i]["odometer"]
            liters = row["liters"] + sum(
                r["liters"]
                for r in rows_before[base_i + 1 :]
                if r.get("type") == "加油" and is_valid(r) and r.get("liters")
            )
            if liters > 0:
                kml = distance / liters

    # 每公里成本 = 本次花費 ÷ 本次行駛距離
    cost_per_km = None
    if row.get("type") == "加油" and row.get("cost") and trip:
        cost_per_km = row["cost"] / trip

    return {"trip": trip, "kml": kml, "cost_per_km": cost_per_km}


def cumulative(rows: list[dict]) -> dict:
    """【評分：調用歷史】個人累積統計（rows 必須是同一個人的全部紀錄）。"""
    data_rows = [r for r in rows if r.get("type") in ("加油", "保養", "儀表板")]
    fuel_rows = [r for r in rows if r.get("type") == "加油"]
    maint_rows = [r for r in rows if r.get("type") == "保養"]

    total_cost = sum(r["cost"] for r in fuel_rows + maint_rows if r.get("cost"))
    maint_cost = sum(r["cost"] for r in maint_rows if r.get("cost"))

    odos = [r["odometer"] for r in data_rows if is_valid(r) and r.get("odometer")]
    total_km = odos[-1] - odos[0] if len(odos) >= 2 and odos[-1] > odos[0] else None

    # 歷史總平均油耗 = 各個「加滿區間」的距離加總 ÷ 油量加總（不是把每次油耗再平均）
    base = None
    acc = 0.0
    dist_sum = fuel_sum = 0.0
    for r in fuel_rows:
        if not is_valid(r):
            continue
        if r.get("liters"):
            acc += r["liters"]
        if _is_full_fill(r):
            if base is not None and r["odometer"] > base and acc > 0:
                dist_sum += r["odometer"] - base
                fuel_sum += acc
            base, acc = r["odometer"], 0.0
    avg_kml = dist_sum / fuel_sum if fuel_sum > 0 else None

    return {
        "fuel_count": len(fuel_rows),
        "maint_count": len(maint_rows),
        "total_cost": total_cost,
        "maint_cost": maint_cost,
        "total_km": total_km,
        "avg_kml": avg_kml,
        "suspect_count": sum(1 for r in rows if r.get("status") == SUSPECT),
        "has_data": bool(data_rows),
    }
