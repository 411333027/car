# 建立 Discord Bot、拿到 token、邀進你的 Server

- 適用電腦：Windows 11（你的電腦）
- 前置：已完成 `docs/discord-server-setup.md`（你已經有自己的 Server 和 `gas-tracker` 頻道）
- 要花的時間：約 15 分鐘
- 做完會拿到：一個在你 Server 裡（目前離線）的 bot、一個 `DISCORD_TOKEN`

> **名詞：**
> - **Application（應用程式）**：你在 Discord 開發者網站上登記的一個「專案」。
> - **Bot（機器人）**：Application 底下的一個「程式帳號」，可以自己收發訊息。我們的 agent 就是用這個帳號在 Discord 裡說話。
> - **Token**：這個 bot 的**密碼**。誰拿到它，誰就能完全控制你的 bot。
> - **Developer Portal（開發者後台）**：Discord 管理 Application 和 Bot 的網站。
>
> 畫面名稱可能會改版，所以每個按鈕都用英文寫（開發者後台只有英文介面，比較不會找錯）。

---

## ⚠️ 先看這一段：bot token 的規則

> **bot token 絕對不能：**
> - 貼給任何人（同學、朋友、老師、網路論壇、GitHub、Discord 任何頻道）
> - **貼進跟 Claude 的這個對話**（對話內容會被記錄；需要我協助時，我也不需要看到 token）
> - 截圖（畫面上有 token 就別截）
> - **commit 進 git**（也不能 push 到 GitHub）
>
> **token 只放在一個地方：** 你電腦上專案資料夾裡的 `.env` 檔（這個檔案已經被 `.gitignore` 擋住，不會被 commit）。
>
> **萬一不小心貼出去了：**
> 1. 立刻回到 Developer Portal 的 Bot 頁面按 **Reset Token**，舊的 token 馬上失效。
> 2. 用新的 token 取代 `.env` 裡的舊值。
> 3. 如果已經被 commit 或 push，**只刪檔是沒用的**（git 歷史還在），請告訴我，我們另外處理。

---

## 第一部分：登入 Developer Portal

1. 打開瀏覽器（Chrome 或 Edge）。
2. 在網址列輸入 `https://discord.com/developers/applications` 按 Enter。
3. 用你的 Discord 帳號登入（跟你開 Server 的是同一個帳號）。
4. 你會看到「Applications」頁面（可能是空的）。

---

## 第二部分：建立 Application

1. 按右上角的 **New Application**。
2. 在「Name」欄位輸入 bot 的名字，例如 `gas-tracker-bot`。
3. 勾選同意條款的核取方塊（Discord Developer Terms of Service 與 Developer Policy）。
4. 按 **Create**。（可能出現「我不是機器人」的驗證，照著點完。）
5. 你會進入這個 Application 的設定頁，左邊有一排選單（General Information、Installation、OAuth2、Bot…）。

> 頁面上有一個 **Application ID**，它**不是** token，貼給別人不會有危險。但別混淆：後面要的是 Bot 頁面的 **Token**。

---

## 第三部分：設定 Bot

1. 點左邊選單的 **Bot**。
2. 往下找到 **Public Bot**，把它**關閉**（開關變灰）。
   - 原因：關閉後，只有你自己能把這個 bot 邀進 Server，別人不能自己拿去用。
3. 找到 **Requires OAuth2 Code Grant**，確認它是**關閉**的（預設就是關）。

---

## 第四部分：打開 Message Content Intent（一定要做）

### 為什麼一定要打開

**Intent** 是 Discord 的「資料存取開關」。Discord 預設**不讓 bot 看到別人訊息的文字內容**（為了保護隱私），bot 只知道「有一則訊息出現」。

我們的 agent 需要看訊息文字，因為：
- `!stats`、`!chart`、`!fix_last`、`!add_car` 這些**指令都是訊息文字**，看不到文字就等於收不到指令。
- 使用者在照片旁邊打的**車名**和「**沒加滿**」，也是訊息文字。

沒打開的話：agent 啟動時會出現類似 `PrivilegedIntentsRequired` 的錯誤，或者 bot 上線了卻對所有指令沒反應。

### 怎麼打開

1. 還在 **Bot** 頁面，往下捲到 **Privileged Gateway Intents** 區塊。
2. 找到 **Message Content Intent**，把右邊的開關**打開**（變成藍色／綠色）。
3. **其他兩個**（Presence Intent、Server Members Intent）**不用打開**，保持關閉。
4. 頁面下方（或上方）會跳出一條提示，按 **Save Changes**。
   - 沒按 Save 就離開，設定不會生效。
5. 重新整理頁面（按 `F5`），確認 Message Content Intent 還是打開的。

---

## 第五部分：取得 bot token

> 再提醒一次：**token 只會顯示一次，不能貼給任何人，也不能貼進跟 Claude 的對話。**

1. 還在 **Bot** 頁面，往上找到 **Token** 區塊。
2. 按 **Reset Token**。
3. 跳出確認視窗，按 **Yes, do it!**（可能要你輸入 Discord 密碼或二階段驗證碼）。
4. 畫面上會出現一長串亂碼，這就是 token。
5. 立刻按旁邊的 **Copy**。
6. **馬上**照下面的步驟放進 `.env`，放好之後再離開這個頁面。
   - 如果沒複製到：沒關係，再按一次 **Reset Token** 重新產生就好（舊的會失效）。

### 把 token 放進 `.env`

這個檔案要你自己手動建立，**不需要經過我**。

1. 打開 **檔案總管**，進入 `C:\Users\Grace\car` 資料夾。
2. 在空白處按右鍵 → **新增** → **文字文件**，隨便取名（之後會改）。
3. 打開這個文字文件（記事本），貼上以下內容（等號後面的文字替換成你自己的）：

   ```
   DISCORD_TOKEN=把剛剛複製的 token 貼在這裡
   CHANNEL_ID=把 server-setup 文件裡的頻道 ID 貼在這裡
   CLAUDE_MODEL=claude-haiku-5-5
   DATA_DIR=C:\Users\Grace\car\data
   ```

   - 等號兩邊**不要有空格**，也不要加引號。
   - `CLAUDE_MODEL` 先用上面這個，之後可以換。
4. 按 **檔案** → **另存新檔**。
5. 「存檔類型」選 **所有檔案 (\*.\*)**（這一步沒選，檔名會被偷偷加上 `.txt`）。
6. 「檔名」輸入 `.env`（前面有一個點），存到 `C:\Users\Grace\car`。
7. 回到檔案總管，如果看到的是 `.env.txt`，在檔案上按 F2 改名，把 `.txt` 拿掉。（要先在檔案總管上方「檢視」→「顯示」→ 勾「檔案副檔名」才看得到。）
8. 關掉記事本。**不要**把這份檔案寄給任何人。

### 確認 `.env` 不會被 commit

1. 在檔案總管，進入 `C:\Users\Grace\car`。
2. 在資料夾上方的網址列輸入 `powershell` 按 Enter（會開一個藍色的 PowerShell 視窗）。
3. 輸入 `git status` 按 Enter。
4. **檢查：** 輸出裡**不能出現** `.env`。出現的話，立刻告訴我，**先不要 commit**。

---

## 第六部分：決定權限，產生邀請連結，把 bot 邀進你的 Server

### 我們要給 bot 哪些權限

**原則：只給它真的需要的。** 不要給 Administrator（管理員）。

| 權限（English） | 中文 | 為什麼需要 |
|---|---|---|
| View Channels | 檢視頻道 | 才看得到 `gas-tracker` |
| Send Messages | 傳送訊息 | 回「處理中」「已完成」 |
| Read Message History | 讀取訊息歷史 | 讀取訊息與照片附件 |
| Add Reactions | 新增反應 | 在訊息上加 ⏳ 和 ✅ |
| Attach Files | 附加檔案 | `!chart` 要把折線圖圖片貼在頻道裡 |

**不用給的：** Administrator、Manage Server、Manage Messages、Mention Everyone。
（agent 的回覆是直接回在頻道，所以不需要私訊。）

### 產生邀請連結

1. 在 Developer Portal 左邊選單點 **OAuth2**。
2. 往下找到 **OAuth2 URL Generator** 區塊。
3. 在 **Scopes** 清單只勾 **bot**。
   - **不要**勾 `applications.commands`（我們用 `!` 指令，不用斜線指令）。
4. 勾完 `bot` 之後，下方會多出 **Bot Permissions** 區塊。
5. 在 Bot Permissions 裡依序勾這五項：
   1. **View Channels**
   2. **Send Messages**
   3. **Read Message History**
   4. **Add Reactions**
   5. **Attach Files**
6. 如果出現 **Integration Type**，選 **Guild Install**。
7. 捲到最下面的 **Generated URL**，按 **Copy**。
   - 這條網址裡**沒有** token，只有 Application ID 和權限，可以安心使用。

### 把 bot 邀進 Server

1. 打開瀏覽器新分頁，貼上剛剛複製的網址，按 Enter。
2. 如果要你登入，用同一個 Discord 帳號登入。
3. 在「**Add to server**」（新增至伺服器）的下拉選單，選你的 Server（`油耗記帳測試`）。
4. 按 **Continue**（繼續）。
5. 畫面會列出 bot 要求的五項權限，確認**只有**這五項，然後按 **Authorize**（授權）。
6. 完成人機驗證。
7. 看到「Authorized」或「已授權」就成功了。

### 確認 bot 已經在 Server 裡

1. 回到 Discord，進入你的 Server。
2. 看畫面**最右邊**的成員清單。
3. 你應該會看到 `gas-tracker-bot`，旁邊有「BOT」標籤，狀態是**離線（灰色）**。
   - 離線是正常的，因為我們的 agent 還沒寫、還沒啟動。啟動之後它才會變成綠色線上。

---

## 常見問題

| 狀況 | 怎麼辦 |
|---|---|
| Bot 頁面找不到 Copy Token，只有 Reset Token | 正常。Token 只在剛重設後顯示一次，按 Reset Token 重新產生即可 |
| 之後 agent 啟動出現 `PrivilegedIntentsRequired` | 回第四部分，確認 Message Content Intent 已打開**並按了 Save Changes** |
| Bot 上線了，但在頻道傳指令沒反應 | 先確認第四部分；再確認 `.env` 的 `CHANNEL_ID` 是**頻道**的 ID，不是 Server 的 ID |
| Bot 在頻道裡看不到或不能傳訊息 | 確認頻道不是私人頻道；若是，要到頻道設定的「權限」把 bot 加進去，並允許上面五項權限 |
| 授權頁面找不到我的 Server | 你必須在那個 Server 有「管理伺服器」權限（你是建立者，通常沒問題）；確認登入的是同一個 Discord 帳號 |
| 不小心把 token 貼出去了 | 馬上到 Bot 頁面按 Reset Token，再更新 `.env`（見本文最前面的說明） |

---

## 做完請確認

- [ ] Application 和 Bot 已建立，Public Bot 是**關閉**的
- [ ] **Message Content Intent 已打開，並按過 Save Changes**
- [ ] Token 已放進 `C:\Users\Grace\car\.env`，**沒有貼給任何人、沒有貼進對話**
- [ ] `git status` 的輸出裡**沒有** `.env`
- [ ] Bot 只有五項權限，已經出現在 Server 的成員清單（離線）
- [ ] `.env` 裡有 `DISCORD_TOKEN`、`CHANNEL_ID`、`CLAUDE_MODEL`、`DATA_DIR` 四項

---

## 補充：之後 agent 啟動時要檢查的事

這份文件只做到 Discord 這一邊的設定。等 agent 寫好，啟動後如果 bot 沒有變成綠色線上，優先檢查：

1. `.env` 的 `DISCORD_TOKEN` 有沒有貼錯（多空格、少一段）。
2. 電腦有沒有網路。
3. 是不是有第二支程式也在用同一個 token 連線。
