"""啟動入口與 Discord 串接：Gateway 連線、只聽 CHANNEL_ID、⏳ 反應、排隊、回覆該則訊息。"""

import asyncio
import io
import logging
import shutil
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

from gas_agent import config as cfg
from gas_agent.core import AgentCore, Reply
from gas_agent.intake import DailyLimiter, looks_like_image
from gas_agent.queue_worker import JobQueue, QueueRejected
from gas_agent.storage import RecordStore

log = logging.getLogger("gas_agent")

# 回覆時關掉 @everyone 等提及，只讓「回覆」本身通知上傳者
NO_MASS_MENTIONS = discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=True)
WAIT, DONE, FAIL = "⏳", "✅", "❌"
MAX_MESSAGE_LEN = 1900


class GasBot(commands.Bot):
    def __init__(self, config: cfg.Config, core: AgentCore):
        intents = discord.Intents.default()
        intents.message_content = True  # 要在 Developer Portal 打開 Message Content Intent
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.config = config
        self.core = core
        self.queue = JobQueue()
        self.limiter = DailyLimiter()

    async def setup_hook(self) -> None:
        self.worker_task = asyncio.create_task(self.queue.worker())
        await self.add_cog(GasCommands(self))

    async def on_ready(self) -> None:
        log.info("已上線：%s，只聽頻道 %s", self.user, self.config.channel_id)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return  # 別人打的其他驚嘆號訊息，不理它
        log.warning("指令錯誤：%s", error)

    # ---------------------------------------------------------------- 收訊息
    async def on_message(self, message: discord.Message) -> None:
        # 只聽指定頻道；機器人（包含自己）的訊息一律忽略
        if message.author.bot or message.channel.id != self.config.channel_id:
            return
        images = [a for a in message.attachments if looks_like_image(a.filename, a.content_type)]
        if images:
            await self.on_photo_message(message, images)
            return
        await self.process_commands(message)

    async def on_photo_message(self, message: discord.Message, images: list[discord.Attachment]) -> None:
        uid = str(message.author.id)
        extra_note = ""
        if len(images) > cfg.MAX_IMAGES_PER_MESSAGE:
            images = images[: cfg.MAX_IMAGES_PER_MESSAGE]
            extra_note = f"（一則訊息最多處理 {cfg.MAX_IMAGES_PER_MESSAGE} 張，多的我先忽略）"
        if any(a.size > cfg.MAX_IMAGE_BYTES for a in images):
            await self.safe_reply(message, f"照片太大了，每張請小於 {cfg.MAX_IMAGE_BYTES // 1024 // 1024} MB")
            return
        today = datetime.now(cfg.TZ).date()
        if not self.limiter.try_consume(uid, today, len(images)):
            await self.safe_reply(message, f"你今天已經傳到上限（{cfg.DAILY_LIMIT_PER_USER} 張）了，明天再來吧")
            return

        text = message.content or ""
        when = message.created_at.astimezone(cfg.TZ)
        username = message.author.display_name

        async def job() -> None:
            reply = Reply("處理時發生錯誤，請再傳一次", ok=False)
            try:
                data = [await a.read() for a in images]
                reply = await self.core.handle_photos(message.author.id, username, when, data, text)
            except Exception:
                log.exception("處理照片時出錯")
            if extra_note:
                reply.text += "\n" + extra_note
            await self.finish(message, reply)

        await self.submit(message, uid, job, refund=(today, len(images)))

    # ---------------------------------------------------------------- 共用
    async def submit(self, message: discord.Message, uid: str, job: Callable[[], Awaitable[None]],
                     refund: tuple | None = None) -> None:
        """加上 ⏳ 並排隊。佇列滿了就直接回覆原因。"""
        try:
            self.queue.submit(uid, job)
        except QueueRejected as exc:
            if refund:
                self.limiter.refund(uid, *refund)
            await self.safe_reply(message, str(exc))
            return
        try:
            await message.add_reaction(WAIT)
        except discord.HTTPException:
            log.warning("加 ⏳ 反應失敗（請確認 bot 有 Add Reactions 權限）")

    async def finish(self, message: discord.Message, reply: Reply) -> None:
        """回覆該則訊息，並把 ⏳ 換成 ✅ 或 ❌。"""
        await self.safe_reply(message, reply.text, image=reply.image)
        try:
            await message.remove_reaction(WAIT, self.user)
            await message.add_reaction(DONE if reply.ok else FAIL)
        except discord.HTTPException:
            pass

    async def safe_reply(self, message: discord.Message, text: str, image: bytes | None = None) -> None:
        text = text[:MAX_MESSAGE_LEN]
        files = [discord.File(io.BytesIO(image), filename="chart.png")] if image else []
        try:
            await message.reply(text, files=files, allowed_mentions=NO_MASS_MENTIONS)
        except discord.HTTPException as exc:
            log.warning("回覆失敗：%s（可能缺少權限，或原訊息已被刪除）", exc)
            try:
                files = [discord.File(io.BytesIO(image), filename="chart.png")] if image else []
                await message.channel.send(text, files=files, allowed_mentions=NO_MASS_MENTIONS)
            except discord.HTTPException:
                log.error("送出訊息也失敗，放棄這則回覆")


class GasCommands(commands.Cog):
    """!stats、!chart、!fix_last。每個指令都只用「發指令的人」的 user_id。"""

    def __init__(self, bot: GasBot):
        self.bot = bot

    async def _run(self, ctx: commands.Context, make_reply: Callable[[], Awaitable[Reply]]) -> None:
        message = ctx.message

        async def job() -> None:
            reply = Reply("處理時發生錯誤，請再試一次", ok=False)
            try:
                reply = await make_reply()
            except Exception:
                log.exception("處理指令時出錯")
            await self.bot.finish(message, reply)

        await self.bot.submit(message, str(ctx.author.id), job)

    @commands.command(name="stats", aliases=["養車總計"])
    async def stats(self, ctx: commands.Context) -> None:
        await self._run(ctx, lambda: self.bot.core.handle_stats(ctx.author.id, ctx.author.display_name))

    @commands.command(name="chart", aliases=["趨勢圖"])
    async def chart(self, ctx: commands.Context) -> None:
        await self._run(ctx, lambda: self.bot.core.handle_chart(ctx.author.id, ctx.author.display_name))

    @commands.command(name="fix_last")
    async def fix_last(self, ctx: commands.Context, *, args: str = "") -> None:
        when = ctx.message.created_at.astimezone(cfg.TZ)
        await self._run(ctx, lambda: self.bot.core.handle_fix_last(ctx.author.id, args, when))


def setup_logging(config: cfg.Config) -> None:
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    file = RotatingFileHandler(config.logs_dir / "agent.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    root.addHandler(stream)
    root.addHandler(file)
    logging.getLogger("discord").setLevel(logging.WARNING)


def main() -> None:
    try:
        config = cfg.load_config()
    except cfg.ConfigError as exc:
        print(f"設定有問題：{exc}\n請檢查專案資料夾裡的 .env（範本見 docs/discord-bot-setup.md）", file=sys.stderr)
        raise SystemExit(1) from exc
    if shutil.which("claude") is None:
        print("找不到 claude 指令。請先安裝 Claude Code 並登入（在終端機輸入 claude 試試）。", file=sys.stderr)
        raise SystemExit(1)

    for folder in (config.data_dir, config.inbox_dir, config.photos_dir):
        folder.mkdir(parents=True, exist_ok=True)
    for leftover in config.inbox_dir.glob("*"):  # 上次沒處理完留下的暫存照片
        leftover.unlink(missing_ok=True)
    setup_logging(config)

    store = RecordStore(
        config.records_path, config.backup_dir,
        retry_seconds=cfg.EXCEL_RETRY_SECONDS, retry_times=cfg.EXCEL_RETRY_TIMES,
    )
    bot = GasBot(config, AgentCore(config, store))
    log.info("資料資料夾：%s", config.data_dir)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
