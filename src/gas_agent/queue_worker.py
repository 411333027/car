"""佇列與單一工人（架構文件第 7 節）：所有會碰 Excel、會呼叫 claude -p 的事都排在這裡，一次只做一件。"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from gas_agent import config

log = logging.getLogger(__name__)


class QueueRejected(Exception):
    """排隊被拒絕，訊息可以直接回覆給使用者。"""


class JobQueue:
    def __init__(self, max_size: int = config.MAX_QUEUE_SIZE, max_per_user: int = config.MAX_PENDING_PER_USER):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.max_size = max_size
        self.max_per_user = max_per_user
        self._pending: dict[str, int] = defaultdict(int)
        self._running = False

    def submit(self, user_id: str, job: Callable[[], Awaitable[None]]) -> int:
        """加入佇列，回傳「前面還有幾件」。太多就丟 QueueRejected。"""
        if self._queue.qsize() >= self.max_size:
            raise QueueRejected("目前排隊的人太多了，請稍後再傳")
        if self._pending[user_id] >= self.max_per_user:
            raise QueueRejected(f"你同時最多只能排 {self.max_per_user} 件，請等前面的處理完")
        ahead = self._queue.qsize() + (1 if self._running else 0)
        self._pending[user_id] += 1
        self._queue.put_nowait((user_id, job))
        return ahead

    async def worker(self) -> None:
        """永遠跑的工人。每一件都包在 try/except 裡：一件出錯，只影響那一件。"""
        while True:
            user_id, job = await self._queue.get()
            self._running = True
            try:
                await job()
            except Exception:
                log.exception("處理工作時發生未預期的錯誤（已略過，繼續下一件）")
            finally:
                self._running = False
                self._pending[user_id] -= 1
                self._queue.task_done()
