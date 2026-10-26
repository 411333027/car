import json

import pytest

from gas_agent.parse_result import AnalysisError, parse_analysis


def envelope(payload=None, *, result=None, is_error=False):
    body = {"type": "result", "is_error": is_error}
    if payload is not None:
        body["structured_output"] = payload
    if result is not None:
        body["result"] = result
    return json.dumps(body)


GOOD = {
    "is_target": True,
    "photo_type": "fuel_receipt",
    "odometer_km": None,
    "fuel_liters": 30.2,
    "cost": 960,
    "maintenance_item": None,
    "description": "加油收據",
}


def test_parses_structured_output():
    a = parse_analysis(envelope(GOOD))
    assert a.photo_type == "fuel_receipt"
    assert a.fuel_liters == 30.2 and a.cost == 960 and a.odometer_km is None


def test_parses_json_inside_text_with_fences():
    text = "好的，結果如下：\n```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```"
    assert parse_analysis(envelope(result=text)).cost == 960


def test_numeric_strings_are_accepted():
    a = parse_analysis(envelope({**GOOD, "cost": "1,200", "odometer_km": "12345"}))
    assert a.cost == 1200 and a.odometer_km == 12345


@pytest.mark.parametrize("bad", ["約300", "N/A", "", -5, 0, True, [1], {"a": 1}, float("inf")])
def test_non_numeric_numbers_fail(bad):
    payload = {**GOOD, "cost": bad}
    raw = envelope(result=json.dumps(payload).replace("Infinity", "1e999")) if bad == float("inf") else envelope(payload)
    with pytest.raises(AnalysisError):
        parse_analysis(raw)


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", "null", envelope(result="沒有 JSON"), envelope(result="{壞掉"), envelope(is_error=True, result="boom"), "{}"],
)
def test_garbage_raises_analysis_error_not_crash(raw):
    with pytest.raises(AnalysisError):
        parse_analysis(raw)


def test_inconsistent_target_flag_fails():
    with pytest.raises(AnalysisError):
        parse_analysis(envelope({**GOOD, "is_target": False}))
    with pytest.raises(AnalysisError):
        parse_analysis(envelope({**GOOD, "photo_type": "other"}))


def test_unknown_photo_type_fails():
    with pytest.raises(AnalysisError):
        parse_analysis(envelope({**GOOD, "photo_type": "../../x"}))


def test_non_target_with_nulls_is_fine():
    a = parse_analysis(envelope({
        "is_target": False, "photo_type": "other", "odometer_km": None, "fuel_liters": None,
        "cost": None, "maintenance_item": None, "description": "馬克杯",
    }))
    assert not a.is_target and a.description == "馬克杯"
