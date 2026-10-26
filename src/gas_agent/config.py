"""設定：全部從 .env 讀（DISCORD_TOKEN、CHANNEL_ID、CLAUDE_MODEL、DATA_DIR），上限數字集中在這裡。"""

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TZ = ZoneInfo("Asia/Taipei")

# ---- 上限數字（架構文件第 7、13 節）----
MAX_QUEUE_SIZE = 20  # 佇列總長度
MAX_PENDING_PER_USER = 3  # 每人同時排隊
MAX_IMAGES_PER_MESSAGE = 2  # 一則訊息最多處理幾張（儀表板＋收據）
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 單張 10 MB
MAX_IMAGE_PIXELS = 50_000_000  # 防止超大圖（解壓縮炸彈）
DAILY_LIMIT_PER_USER = 30  # 每人每天最多幾張
CLAUDE_TIMEOUT_SECONDS = 90
EXCEL_RETRY_SECONDS = 5  # Excel 被打開時，每幾秒重試一次
EXCEL_RETRY_TIMES = 12  # 最多重試幾次（約一分鐘）

# ---- 「可疑」門檻（架構文件 8.4）----
SUSPECT_ODOMETER_JUMP_KM = 3000
SUSPECT_FUEL_LITERS = 100
SUSPECT_FUEL_COST = 5000
SUSPECT_MAINTENANCE_COST = 100000
SUSPECT_KML_LOW = 2
SUSPECT_KML_HIGH = 80

PLACEHOLDER_MARKS = ("你的", "YOUR_", "xxx")


class ConfigError(Exception):
    """.env 缺項或格式不對。訊息會直接印給使用者看，所以要寫清楚。"""


@dataclass(frozen=True)
class Config:
    discord_token: str
    channel_id: int
    claude_model: str
    data_dir: Path

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def records_path(self) -> Path:
        return self.data_dir / "records.xlsx"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backup"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


def _require(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise ConfigError(f".env 缺少 {name}")
    if any(mark in value for mark in PLACEHOLDER_MARKS):
        raise ConfigError(f".env 的 {name} 還是範例文字，請換成真正的值")
    return value


def load_config(env_path: Path | None = None) -> Config:
    load_dotenv(env_path or PROJECT_ROOT / ".env")

    token = _require("DISCORD_TOKEN")
    channel_raw = _require("CHANNEL_ID")
    if not channel_raw.isdigit():
        raise ConfigError("CHANNEL_ID 必須是純數字（在 Discord 對頻道按右鍵 → 複製頻道 ID）")
    model = _require("CLAUDE_MODEL")

    data_dir = Path(_require("DATA_DIR")).expanduser()
    if not data_dir.is_absolute():
        # 相對路徑一律以專案資料夾為準，不論從哪裡啟動都指到同一處
        data_dir = PROJECT_ROOT / data_dir
    return Config(token, int(channel_raw), model, data_dir.resolve())
