# GabFin 第一版：Plus 額度下的分段執行指南

日期：2026-11-25，Asia/Hong_Kong。狀態：S01 與 S02 基礎已完成；其餘按 checkpoint 推進，原工作單位數僅為初估。

本文件調整執行粒度，不改變已確認功能。需求以 [架構設計](../specs/2026-11-25-gabfin-system-design.md) 為準；檔案、契約、測試與驗收以 [24-task 主計劃](2026-11-25-gabfin-upgrade-plan.md) 為準。

## 1. Section、工作單位與對話

- Section：一組有完整成果的子系統；共 12 個必要 Sections。
- 工作單位：一項可獨立驗收的變更，例如一個資料契約、一條恢復流程或一個 UI 垂直切片。
- 對話：承載工作的一個 context。通常一個新工作單位可開新對話；簡短且高度相連的單位可沿用，避免重新讀取的成本。
- 工作單位不保證剛好消耗一個 quota window，也不保證能在一次回覆完成。遇到測試失敗或額度不足，可在同一單位留 checkpoint。
- 新對話不增加／重置 Plus 額度；它主要減少無關歷史進入上下文。以帳戶 usage dashboard／CLI `/status` 顯示的實際額度與 reset 為準。
- 初估 44–70 個工作單位是切分預算，不是固定聊天次數、token 配額或完成承諾。S01、S02 後重新估算。

## 2. 12 個 Sections

| Section | 範圍及對應主計劃任務 | 初估工作單位 | 完成時可驗收成果 |
|---|---|---:|---|
| S01 | Source、基線與功能盤點；Task 1 | 2–3 | 隔離 checkout、固定 SHA、真實測試／build 結果、失敗與外部依賴清單。 |
| S02 | 契約、SQLite、身份權限；Tasks 2、3 | 3–5 | 精確數值與時間契約、可遷移 DB、明確 owner／chat／research／executor 能力。 |
| S03 | OpenD、推送、新鮮度及重播；Tasks 4、5 | 4–6 | 一股行情全鏈路、訂閱配額、late/duplicate events、斷線補缺與 stale。 |
| S04 | 全新前端殼與圖表；Task 7 | 3–5 | 快速桌面首屏、股票切換、增量圖表及來源／時間／錯誤狀態。 |
| S05 | 任務、預算、證據及動態股票池；Tasks 6、8 | 4–6 | 可恢復 job、費用預留、來源登錄、候選更新、任意美股清單分析入口。 |
| S06 | 研究 Harness 與多 Agent；Task 9 | 3–5 | 有界並行研究、模型介面、引用核對、缺資料報告及重啟恢復。 |
| S07 | 可信回測與策略研究；Tasks 10、16 | 4–7 | 手算 fixtures、引擎決策、時間切分、成本後基準及策略 scorecard。 |
| S08 | 動態風控、paper adapter、OMS；Tasks 11、12 | 5–8 | Long/short、盤前／正常／盤後、冪等／UNKNOWN／partial fills；數值未批准時禁啟用。 |
| S09 | 保護、對帳、策略仲裁及治理；Tasks 13、15 | 4–6 | 慢研究不阻塞保護、恢復對帳、帳戶淨持倉、提案批准與版本回退。 |
| S10 | App 研究／帳戶 UI、期權、iPhone；Tasks 14、17、18 | 5–8 | 完整只讀／研究聊天、獨立 paper controls、期權研究頁、私人 PWA 與實機恢復。 |
| S11 | 安全、效能與閉環整合；Task 23，再 Task 19 | 4–6 | 能力隔離、CI、實測延遲、完整事件到成交／日誌、故障前置檢查。 |
| S12 | Paper 驗收、遷移、回退與交付；Tasks 20、21、24 | 3–5 | 有限制聲明的 paper evidence、唯一 executor 切換、資料對帳、操作手冊。 |

合計 44–70 個工作單位。S12 另有至少 20 個交易日的工程觀察窗口提案；觀察日不代表每天需要新開 coding 對話，也不等於已證明策略有效。
Task 24 的記憶更新隨所有 Sections 執行，S12 再整體核對。
Task 22（REA／ECC／ORCA 工具比較）為可選支線，不阻塞第一版；不額外安裝整套工具來逃避現有實作問題。

## 3. 每節如何再拆成小工作

按這些邊界排工作，而非要求一次完成整節：

| Section | 小工作切片，依序進行 |
|---|---|
| S01 | 01a 取得 source／固定基準；01b 跑基線並分類失敗；必要時 01c 深查阻塞依賴。 |
| S02 | 契約／serialization；SQLite migrations；session／capability；schema／auth regression。 |
| S03 | entitlement smoke；symbol／訂閱計劃；callback→cache；bar／freshness；補缺重播。 |
| S04 | workspace／shell；transport／types；chart；切換／取消／stale；build 與瀏覽器驗收。 |
| S05 | job lease／取消；費用帳本；evidence；source register；universe as-of；清單解析。 |
| S06 | fake model runner；分支並行；引用檢查；cache／恢復；模型實測小樣本。 |
| S07 | 修正手算案例；引擎 spike；資料 manifest；temporal splits；baseline 策略；成本／多空；scorecard。 |
| S08 | policy validation；dynamic sizing；short／session；broker adapter；outbox／冪等；UNKNOWN／partial；數值批准。 |
| S09 | 啟動對帳；獨立保護；多策略仲裁；實驗隔離；proposal hash；部署／回退。 |
| S10 | 帳戶／研究／委託頁；聊天 allowlist；controls；期權資料／數學；期權頁；PWA；私人連線；iPhone 實機。 |
| S11 | security boundaries；dependency／secret／license checks；效能 replay；CI／supervisor；closed loop；跨 session 整合。 |
| S12 | 故障演練；觀察證據；import dry-run；cutover／rollback；最終文件與追溯。 |

表中切片是可用邊界，不要求一次對話包辦同一格；數量可按實際程式複雜度合併或拆分。未完成測試不能藉新對話跳到下一節。
S07 引擎完成後，S08 才按其輸出落實 adapter；S10 的獨立 controls 必須接到 S08／S09 的唯一執行服務。

## 4. 每個工作單位的固定操作

### 開始

1. 讀 `AGENTS.md`、`docs/memory/tasks.md`、`docs/memory/execution.md`。
2. 只讀本 Section 對應的主計劃任務及必要契約；不每次重讀兩份完整大文件。
3. `git status`／diff 檢查真實狀態；查看上次命令結果，不能只信進度文字。
4. 選一個可驗收目標；說明要改的範圍，不重新做整庫審計。

### 工作

1. 做有意義的失敗測試、最小實作及必要回歸；文件或低風險機械調整不寫形式化測試。
2. 預設一位主 Agent 實作。只有獨立且有價值的探索／審查才使用子 Agent，不為每個小單位開整隊。
3. 新增數值政策、購買、改用真倉或改需求，帶具體差異請使用者決定；日常可逆實作不反覆問「繼續嗎」。
4. 不以固定的「幾個檔案」取代正確設計，但避免跨越前端、provider、策略、風控同時大改。

### 結束／額度不足前

1. 記錄已修改 paths、驗證命令與結果、未完成部分、下一個具體動作。
2. 寫入 `execution.md` 的最新 checkpoint；lasting facts 只更新其 owning memory，進度保留最近 10 項。
3. 有 Git checkout 時，已驗證完整變更可建立 local commit；未完成變更保留狀態，不為結束而假稱完成或自動 push。
4. 最終訊息只交代成果、限制與下一單位；不重複整份計劃。

### Checkpoint 格式

```text
Section / Unit:
Status: not-started | active | blocked | verified
Source commit / working tree:
Completed behavior:
Changed files:
Verification command + actual result:
Unresolved failure / external dependency:
Next exact action:
Usage observation (if available):
```

不保存密碼、API key、account ID、長 log 或完整聊天。若 log 大，記本機路徑與關鍵錯誤。

## 5. 時間、token 與費用

### 時間

- 主計劃原估 41–73 工程工作日，約 8–15 個五天工作週；這是假設熟悉技術的執行者，並非已量測 Codex 時間。
- Paper 工程觀察另約 20 個交易日，可與部分文件／UI 收尾重疊，但交易日不能靠多 Agent 壓縮。
- 對 Plus 有限額度、非全職推進，暫以 3–5 個月作日曆規劃預留；不是交付保證，授權、資料、回測問題或額度等待可令時間更長。
- S01／S02 後，用實際每單位耗時、返工與可用額度重估，不將 44–70 個單位直接當 44–70 天。

### Token／用量

- 雖已建立 application baseline，仍不能在沒有帳戶實際用量紀錄時可信估出「總共幾百萬 tokens」。
- Plus 亦不是可由我承諾的固定 token 數；可用量與 reset 以帳戶狀態為準。
- 頭 3–5 個單位記錄模型、推理強度、工作類型、活躍時間、重試／重讀及可見的用量變化，再估後續範圍。
- 小改動用目前帳戶可用的較省模型／推理設定；金融邊界、競態與安全審查才提高投入，不以省 token 為由略過重要驗證。
- 短 context、精簡工具輸出、穩定 contracts、fake providers 及窄測試減少返工；開新對話本身不增加額度。

### 費用

- 開發：現有 Plus／Cursor 會員可以繼續使用；若不購買額外 credits／API，遇限額就等待，不承諾會員內必然足夠。
- App 運行：LLM API、行情等另算，基礎 HK$400／月及可能期權約 HK$100 加額沿用；未選定 provider／行情前不視為正式月費。
- 本機先不新增 VPS／域名固定費；電費及既有網絡不包含於「無新增雲端費用」的說法。
- 真實總成本 = 開發會員／加購 + App 當月實際用量 + 資料／主機／其他；不能混成一個 token 價格。

## 6. 可直接貼入新對話的啟動提示

```text
繼續 GabFin 第一版。先讀 AGENTS.md、docs/memory/tasks.md 及
docs/memory/execution.md，只讀目前 Section 對應的計劃與必要程式。
今次完成一個可驗收工作單位；不要重做已完成審計或重啟 grill-me。
預設單主 Agent，按需要才使用子 Agent。不要修改未批准風險或開真倉。
結束前更新 checkpoint，列出實際驗證結果及下一個動作。
```

目前 Section、下一單位及已驗證版本以 [execution checkpoint](../../memory/execution.md) 為準。S02／S03 的原單位估算不作剩餘工作承諾；依實際驗收逐步更新。S02 基礎限制見 [完成報告](../../audit/s02-completion-2026-11-25.md)，需求擴充見 [研究體驗計劃](2026-11-25-gabfin-research-experience-plan.md)。

## 7. 官方用量來源

[Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)，查閱 2026-11-25。消耗與模型、上下文、推理、工具及任務有關；帳戶頁／CLI `/status` 提供適用的 allowance 與 reset 資訊。本指南不固定抄寫可能變動的會員額度。
