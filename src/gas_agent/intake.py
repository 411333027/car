"""收件檢查：還沒花到 AI 額度之前，先擋掉不合格的（架構文件第 4、7、13 節）。

訊息文字在這裡只用來認「沒加滿」這個關鍵字，其他文字一律忽略，也不會被存起來或傳給 claude -p。
"""

from collections import defaultdict
from datetime import date

from gas_agent import config

NOT_FULL_WORDS = ("沒加滿", "未加滿", "沒有加滿")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic")


def is_not_full(text: str) -> bool:
    return any(word in (text or "") for word in NOT_FULL_WORDS)


def looks_like_image(filename: str, content_type: str | None) -> bool:
    if content_type and content_type.lower().startswith("image/"):
        return True
    return (filename or "").lower().endswith(IMAGE_SUFFIXES)


class DailyLimiter:
    """每人每天最多處理幾張（只記在記憶體，重啟後歸零）。"""

    def __init__(self, limit: int = config.DAILY_LIMIT_PER_USER):
        self.limit = limit
        self._counts: dict[tuple[str, date], int] = defaultdict(int)

    def try_consume(self, user_id: str, today: date, n: int) -> bool:
        key = (user_id, today)
        if self._counts[key] + n > self.limit:
            return False
        self._counts[key] += n
        return True

    def refund(self, user_id: str, today: date, n: int) -> None:
        key = (user_id, today)
        self._counts[key] = max(0, self._counts[key] - n)
