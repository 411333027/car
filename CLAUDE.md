# CLAUDE.md

## 專案

一支跑在本機的 Discord 機器人（agent）：指定頻道有人傳汽機車儀表板、加油收據或保養單照片，它用 `claude -p` 看圖解析，依 Discord `user_id` 分人記帳到 Excel，計算油耗與花費並私訊回覆。

## 開始任何工作前

先讀 `docs/architecture0.md`（架構文件），再讀 `docs/requirements0.md`（需求）。實作要照架構文件；要偏離時先跟使用者說明。

## 四段防護

架構文件第 12 節定義了四段防護。程式裡每一段都要用註解明確框起來，格式如下：

```python
# ===== 防護 1：claude -p 的檔案範圍隔離 開始 =====
...
# ===== 防護 1 結束 =====
```

| 編號 | 內容 | 位置 |
|---|---|---|
| 防護 1 | `claude -p` 只能讀到暫時資料夾裡的那一張照片，讀不到 `DATA_DIR` | `vision.py` |
| 防護 2 | 使用者打的字只當資料，不接進給 `claude -p` 的指令 | `vision.py` |
| 防護 3 | AI 回傳的說明拿去組檔名前，要清掉 `/ \ .. :` 等會讓路徑亂跑的字 | `photos.py`（清洗函式在 `sanitize.py`） |
| 防護 4 | 寫進 Excel 的文字若以 `= + - @` 開頭，要處理成純文字 | `storage.py`（處理函式在 `sanitize.py`） |

- **一開始全部開啟。** 之後教學／評分時才會逐段關掉對照，不要自己先關。
- 不要把四段防護合併、打散，或移到標記範圍之外；教學時是靠這些註解逐段開關。
- 寫法是「先設沒有防護時的預設值，再由防護段覆蓋成安全的值」，所以**把某一段整段註解掉，程式仍要能跑**。防護段不能是某個 `if` / `for` 的唯一內容，否則註解掉會變成語法錯誤。
- 其他程式碼改動不可以讓防護範圍失效（例如繞過 `sanitize.py` 直接寫 Excel 或組檔名）。
- 改動防護相關程式後，跑 `uv run python scripts/check_defence_toggle.py` 確認四段仍可各自關掉；行號變了就更新 README 的表格（`grep -n "===== 防護" src/gas_agent/*.py`）。

## 常用指令

- 啟動：`uv run gas-agent`
- 測試：`uv run pytest`（真的呼叫 `claude -p` 的測試要加 `GAS_LIVE=1`）

## 不可以 commit 的東西

- **`.env`**（內含 `DISCORD_TOKEN`）絕對不能 commit。repo 只放不含真值的 `.env.example`。
- **`DATA_DIR` 裡的所有東西**（使用者上傳的照片、`records.xlsx`、備份、log）也不能 commit。
- 要 commit 前先跑 `git status`，確認沒有上面這些檔案被加入。
- 萬一 token 已經被 commit 或貼出去，要通知使用者到 Discord Developer Portal 按 Reset Token，不要只是刪檔。
