"""合理性檢查：數字看起來不對就標「可疑」（架構文件 8.4）。門檻在 config.py。"""

from gas_agent import config


def suspicion_reasons(row: dict, previous_odometer: float | None) -> list[str]:
    reasons: list[str] = []
    odo = row.get("odometer")
    if odo is not None and previous_odometer is not None:
        if odo < previous_odometer:
            reasons.append(f"里程 {odo:,.0f} 比上一筆 {previous_odometer:,.0f} 還小")
        elif odo - previous_odometer > config.SUSPECT_ODOMETER_JUMP_KM:
            reasons.append(f"里程比上一筆多了 {odo - previous_odometer:,.0f} km，差太多")

    liters, cost, kind = row.get("liters"), row.get("cost"), row.get("type")
    if liters is not None and liters > config.SUSPECT_FUEL_LITERS:
        reasons.append(f"加油量 {liters:g} L 太大")
    if kind == "加油" and cost is not None and cost > config.SUSPECT_FUEL_COST:
        reasons.append(f"加油金額 {cost:,.0f} 元太大")
    if kind == "保養" and cost is not None and cost > config.SUSPECT_MAINTENANCE_COST:
        reasons.append(f"保養金額 {cost:,.0f} 元太大")

    kml = row.get("kml")
    if kml is not None and not (config.SUSPECT_KML_LOW <= kml <= config.SUSPECT_KML_HIGH):
        reasons.append(f"算出的油耗 {kml:.1f} km/L 不合理")
    return reasons
