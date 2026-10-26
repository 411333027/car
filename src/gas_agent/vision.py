"""用 claude -p 分析一張照片。

這個檔案有兩段防護：
- 防護 1：把 claude -p 能碰到的檔案範圍限制在「只有這一張照片」的暫存資料夾
- 防護 2：上傳者打的字不能接進給 claude -p 的指令

寫法是「先設好沒有防護時的預設值，再由防護段覆蓋成安全的值」。
所以把某一段整段註解掉，程式仍然能跑，只是少了那一層保護（教學對照用）。
"""

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

from gas_agent.config import CLAUDE_TIMEOUT_SECONDS, PROJECT_ROOT
from gas_agent.parse_result import Analysis, AnalysisError, parse_analysis
from gas_agent.prompts import PROMPT_TEMPLATE, SCHEMA_JSON

log = logging.getLogger(__name__)


class ClaudeError(AnalysisError):
    """claude -p 本身出問題（找不到、逾時、非正常結束…）。"""


def _deny_read_rule(path: Path, suffix: str = "") -> str:
    """產生 Claude Code 的「禁止讀取」規則。Windows 絕對路徑寫法：C:/a/b -> //c/a/b。"""
    posix = path.resolve().as_posix()
    if len(posix) > 2 and posix[1] == ":":
        posix = "//" + posix[0].lower() + posix[2:]
    return f"Read({posix}{suffix})"


async def run_claude(image_path: Path, model: str, data_dir: Path, user_text: str = "") -> str:
    """執行一次 claude -p，回傳它的原始輸出（交給 parse_result 解析）。"""
    exe = shutil.which("claude")
    if exe is None:
        raise ClaudeError("找不到 claude 指令，請確認 Claude Code 已安裝並登入")

    # ---- 沒有防護 1 時的預設：直接在照片所在的資料夾（DATA_DIR/inbox）執行，不限制工具 ----
    photo_ref = str(image_path)
    run_cwd = image_path.parent
    extra_args: list[str] = []
    child_env = dict(os.environ)
    sandbox_dir: Path | None = None

    # ===== 防護 1：claude -p 的檔案範圍隔離 開始 =====
    # 每次建一個全新的暫存資料夾（在系統暫存區，不在 DATA_DIR 裡也不是它的上層），
    # 只複製「這一張」照片進去，claude -p 就在那裡面工作。
    sandbox_dir = Path(tempfile.mkdtemp(prefix="gas-agent-"))
    resolved_data = data_dir.resolve()
    if sandbox_dir.resolve() == resolved_data or resolved_data in sandbox_dir.resolve().parents:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
        raise ClaudeError("暫存資料夾不能放在 DATA_DIR 裡面")
    shutil.copyfile(image_path, sandbox_dir / "photo.jpg")
    photo_ref = "photo.jpg"
    run_cwd = sandbox_dir
    extra_args = [
        "--tools", "Read",  # 只開「讀檔」一種工具，不能執行指令、改檔、上網、搜尋資料夾
        "--disallowed-tools",  # 再明確禁止讀 DATA_DIR（別人的照片和紀錄）與 .env（token）
        _deny_read_rule(data_dir, "/**"),
        _deny_read_rule(PROJECT_ROOT / ".env"),
        "--setting-sources", "project",  # 不載入使用者自己的設定、外掛、hook
    ]
    child_env.pop("DISCORD_TOKEN", None)  # 子程序拿不到機器人的 token
    # ===== 防護 1 結束 =====

    # ---- 沒有防護 2 時的預設：使用者打的字原樣接進給 claude -p 的指令 ----
    user_note = user_text

    # ===== 防護 2：上傳者文字只當資料、不進指令 開始 =====
    # 給 claude -p 的指令只有寫死的固定文字加一張圖。使用者打的字（包含
    # 「忽略之前的指令…」這類）完全不放進來；「沒加滿」之類的關鍵字由程式自己判斷。
    user_note = ""
    # ===== 防護 2 結束 =====

    prompt = PROMPT_TEMPLATE.format(photo_ref=photo_ref)
    if user_note:
        prompt += f"\n\n使用者補充說明：{user_note}"

    cmd = [
        exe, "-p",
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--json-schema", SCHEMA_JSON,
        *extra_args,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=run_cwd,
            env=child_env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")), timeout=CLAUDE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise ClaudeError(f"claude -p 超過 {CLAUDE_TIMEOUT_SECONDS} 秒沒有回應") from exc
        if proc.returncode != 0:
            detail = stderr.decode("utf-8", "replace").strip()[:200]
            raise ClaudeError(f"claude -p 異常結束（代碼 {proc.returncode}）：{detail}")
        return stdout.decode("utf-8", "replace")
    except OSError as exc:
        raise ClaudeError(f"無法啟動 claude -p：{exc}") from exc
    finally:
        if sandbox_dir is not None:
            shutil.rmtree(sandbox_dir, ignore_errors=True)


async def analyze_photo(image_path: Path, model: str, data_dir: Path, user_text: str = "") -> Analysis:
    """分析一張照片；失敗時重試一次，仍失敗就丟出 AnalysisError。"""
    last_error: AnalysisError | None = None
    for attempt in (1, 2):
        try:
            return parse_analysis(await run_claude(image_path, model, data_dir, user_text))
        except AnalysisError as exc:
            last_error = exc
            log.warning("照片分析失敗（第 %d 次）：%s", attempt, exc)
    assert last_error is not None
    raise last_error
