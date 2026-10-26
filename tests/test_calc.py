import pytest

from gas_agent import calc
from gas_agent.checks import suspicion_reasons


def fuel(odo, liters, cost, full="是", status="完成", id_=0):
    return {"id": id_, "type": "加油", "odometer": odo, "liters": liters, "cost": cost, "full": full, "status": status}


def test_first_record_has_no_trip_or_economy():
    row = fuel(12000, 30, 900)
    f = calc.compute_fields([], row)
    assert f == {"trip": None, "kml": None, "cost_per_km": None}


def test_trip_economy_and_cost_per_km():
    rows = [fuel(12000, 30, 900)]
    f = calc.compute_fields(rows, fuel(12450, 30, 900))
    assert f["trip"] == 450
    assert f["kml"] == pytest.approx(15.0)
    assert f["cost_per_km"] == pytest.approx(2.0)


def test_not_full_accumulates_into_next_full(tmp_path):
    rows = [fuel(12000, 30, 900), fuel(12200, 10, 300, full="否")]
    skipped = calc.compute_fields(rows[:1], rows[1])
    assert skipped["trip"] == 200 and skipped["kml"] is None  # 沒加滿：不算油耗
    f = calc.compute_fields(rows, fuel(12450, 20.2, 600))
    assert f["trip"] == 250
    assert f["kml"] == pytest.approx(450 / 30.2)  # 基準點到現在的總距離 ÷ 期間總油量


def test_suspicious_rows_are_skipped_as_previous_and_baseline():
    rows = [fuel(12000, 30, 900), fuel(99999, 30, 900, status="可疑")]
    assert calc.previous_valid_odometer(rows) == 12000
    f = calc.compute_fields(rows, fuel(12450, 30, 900))
    assert f["trip"] == 450 and f["kml"] == pytest.approx(15.0)


def test_receipt_without_odometer_has_no_economy_but_counts_fuel_later():
    rows = [fuel(12000, 30, 900), fuel(None, 10, 300, status="待補里程")]
    f = calc.compute_fields(rows, fuel(12450, 20, 600))
    assert f["kml"] == pytest.approx(450 / 30)


def test_cumulative_uses_distance_weighted_average():
    rows = [
        fuel(10000, 30, 900),
        fuel(10300, 20, 600),  # 300 km / 20 L
        fuel(10900, 30, 900),  # 600 km / 30 L
        {"id": 9, "type": "保養", "odometer": None, "liters": None, "cost": 1500, "full": "", "status": "完成"},
    ]
    c = calc.cumulative(rows)
    assert c["avg_kml"] == pytest.approx(900 / 50)  # 不是 (15 + 20) / 2
    assert c["total_km"] == 900
    assert c["total_cost"] == 900 + 600 + 900 + 1500
    assert c["maint_cost"] == 1500 and c["fuel_count"] == 3 and c["maint_count"] == 1


def test_cumulative_is_consistent_with_compute_fields():
    rows = [fuel(1000, 10, 300)]
    for odo, liters in [(1150, 10), (1320, 12)]:
        f = calc.compute_fields(rows, fuel(odo, liters, 300))
        rows.append(fuel(odo, liters, 300))
    assert calc.cumulative(rows)["avg_kml"] == pytest.approx((1320 - 1000) / 22)


def test_empty_history():
    c = calc.cumulative([])
    assert c["has_data"] is False and c["avg_kml"] is None and c["total_cost"] == 0


@pytest.mark.parametrize(
    "row,prev,expect",
    [
        ({"odometer": 100, "type": "加油"}, 200, "比上一筆"),
        ({"odometer": 9000, "type": "加油"}, 100, "差太多"),
        ({"odometer": 100, "liters": 300, "type": "加油"}, 50, "加油量"),
        ({"odometer": None, "cost": 9000, "type": "加油"}, None, "加油金額"),
        ({"odometer": None, "cost": 200000, "type": "保養"}, None, "保養金額"),
        ({"odometer": 100, "kml": 200, "type": "加油"}, 50, "油耗"),
    ],
)
def test_suspicion_reasons(row, prev, expect):
    assert any(expect in r for r in suspicion_reasons(row, prev))


def test_normal_row_is_not_suspicious():
    assert suspicion_reasons({"odometer": 12450, "liters": 30, "cost": 900, "kml": 15, "type": "加油"}, 12000) == []
