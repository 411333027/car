# 汽機車油耗與保養記帳 Agent

一支跑在你自己電腦上的 Discord 機器人：指定頻道裡有人傳**儀表板、加油收據或保養單**照片，它用 `claude -p` 看圖，讀出里程、加油量、金額，依 Discord 帳號（`user_id`）分人記帳到 Excel，計算油耗與每公里成本，並**在頻道回覆該則訊息**。它開著才會動，關掉就不處理。

設計細節見 [`docs/architecture0.md`](docs/architecture0.md)，需求見 [`docs/requirements0.md`](docs/requirements0.md)。

## 第一次設定

1. 照 [`docs/discord-server-setup.md`](docs/discord-server-setup.md) 建 Server 與頻道，拿到 `CHANNEL_ID`。
2. 照 [`docs/discord-bot-setup.md`](docs/discord-bot-setup.md) 建 bot、打開 **Message Content Intent**、拿到 token，並把 bot 邀進 Server。
   bot 需要的權限：檢視頻道、傳送訊息、讀取訊息歷史、新增反應、**附加檔案**（`!chart` 要貼圖）。
3. 把 `.env.example` 複製成 `.env`，填入真正的值（**`.env` 不會被 commit**）：

   | 項目 | 說明 |
   |---|---|
   | `DISCORD_TOKEN` | bot 的密碼，**絕對不能公開** |
   | `CHANNEL_ID` | 要聽的那個頻道的 ID（只聽這一個） |
   | `CLAUDE_MODEL` | 看圖用的模型，例如 `haiku` |
   | `DATA_DIR` | 紀錄與照片放哪裡；相對路徑以專案資料夾為準 |

4. 這台電腦要裝好並登入 Claude Code（在終端機輸入 `claude` 能用）。

## 啟動

```
uv run gas-agent
```

第一次執行 uv 會自動建立環境並裝好套件。看到「已上線」就代表連上 Discord 了；按 `Ctrl + C` 關掉。

## 使用方式

在指定頻道：

- **加油**：同一則訊息傳「儀表板 + 加油收據」兩張照片。沒加滿就在訊息裡寫「沒加滿」。
- **只有儀表板**：記錄里程與行駛距離。
- **保養單**：記錄保養項目與金額。
- **只傳收據、沒有里程**：照樣存，之後用 `!fix_last 里程 數字` 補上就會重算。
- **不是目標的照片**：一樣建檔存照片，並告訴你它判斷是什麼東西。

收到照片先加 ⏳；處理完換成 ✅（失敗是 ❌），並回覆該則訊息。

| 指令 | 作用 |
|---|---|
| `!stats` / `!養車總計` | 你的累計總花費、總行駛里程、歷史總平均油耗 |
| `!chart` / `!趨勢圖` | 你的歷史油耗折線圖（需要至少 2 筆算得出油耗的加油紀錄） |
| `!fix_last 12400` | 把你最近一筆的里程改成 12400 |
| `!fix_last 加油量 30.5`、`!fix_last 金額 960` | 修正最近一筆的加油量或金額 |

## 資料放哪裡（`DATA_DIR`，預設 `./data`，已被 `.gitignore` 擋住）

- `records.xlsx`：所有紀錄，一直往下加。**要看的話請先另存副本再開**；Excel 開著原檔時 agent 寫不進去，會在終端機印警告、每 5 秒重試約 1 分鐘，仍失敗就請使用者關掉 Excel 後重傳。
- `photos/`：照片，檔名 `2026-10-26 15-30-12 使用者ID 類型簡稱.jpg`，同一秒撞名會加 `-2`、`-3`。
- `backup/`：每天第一次寫入前自動備份（留最近 7 份）。`logs/`：執行紀錄。

## 四段防護（教學用，一開始全部開著）

每一段都用 `# ===== 防護 N：... 開始 =====` 到 `# ===== 防護 N 結束 =====` 框起來。**要關掉某一段，就把這兩行之間的程式整段註解掉**（程式照樣能跑，只是少了那層保護）。

| 防護 | 內容 | 位置（行號會隨修改變動，以下為目前位置） |
|---|---|---|
| 防護 1 | `claude -p` 的檔案範圍隔離：只能讀暫存資料夾裡那一張照片，讀不到 `DATA_DIR` | `src/gas_agent/vision.py` 第 50～69 行 |
| 防護 2 | 上傳者文字只當資料，不接進給 `claude -p` 的指令 | `src/gas_agent/vision.py` 第 74～78 行 |
| 防護 3 | AI 回傳的說明拿去當檔名前，先清掉 `/ \ ..` 冒號等 | `src/gas_agent/photos.py` 第 76～81 行 |
| 防護 4 | 寫進 Excel 的文字若以 `= + - @` 開頭，處理成純文字 | `src/gas_agent/storage.py` 第 63～71 行 |

行號過期時，用這個指令重新找：

```
grep -n "===== 防護" src/gas_agent/*.py
```

檢查「每段都能單獨關掉，而且關掉就有差」：

```
uv run python scripts/check_defence_toggle.py
```

## 測試

```
uv run pytest                    # 自動測試（不會呼叫 Discord 或 claude）
GAS_LIVE=1 uv run pytest -k live # 真的呼叫一次 claude -p（會用掉一點額度）
```

## 注意

- 每張照片都會用掉**你自己的 Claude 額度**，頻道裡的人可以一直傳。程式有每人每天 30 張、一則訊息最多 2 張、佇列上限等保護（數字在 `src/gas_agent/config.py`），也請只邀請信任的人。
- 照片會送到 Anthropic 的服務去讀，請提醒大家不要傳含個資的照片。
- 回覆直接發在頻道，**所有人都看得到彼此的油耗與花費**。
