"""!chart：用 matplotlib 畫該使用者的歷史油耗趨勢折線圖。

【評分：圖表】只畫「有算出油耗、而且不是可疑」的資料點。
"""

import io
from datetime import datetime

from matplotlib import rc_context
from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure

from gas_agent.calc import is_valid

# 依序找電腦上有的中文字型，找不到會變成方塊字
CJK_FONTS = ["Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "Noto Sans CJK TC", "SimHei", "DejaVu Sans"]


def chart_points(rows: list[dict]) -> list[tuple[datetime, float]]:
    points = []
    for r in rows:
        if r.get("kml") and is_valid(r) and r.get("type") == "加油":
            try:
                points.append((datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S"), float(r["kml"])))
            except ValueError:
                continue
    return points


def render_chart(rows: list[dict], username: str = "") -> bytes | None:
    """回傳 PNG 圖片的 bytes；資料不到 2 個點就回 None。"""
    points = chart_points(rows)
    if len(points) < 2:
        return None

    # 直接用 Figure（不經過 pyplot），在背景執行緒畫圖才安全
    with rc_context({"font.sans-serif": CJK_FONTS, "axes.unicode_minus": False}):
        fig = Figure(figsize=(8, 4.5), dpi=120)
        ax = fig.subplots()
        xs, ys = zip(*points)
        ax.plot(xs, ys, marker="o", color="#2a6fdb")
        for x, y in points:
            ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
        ax.set_title("歷史油耗變化" + (f"（{username}）" if username else ""))
        ax.set_ylabel("平均油耗 (km/L)")
        ax.xaxis.set_major_formatter(DateFormatter("%m/%d"))
        ax.grid(alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
    return buf.getvalue()
