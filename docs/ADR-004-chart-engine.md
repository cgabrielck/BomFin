# ADR-004 — 圖表引擎選型與能力邊界｜Chart Engine & Drawing Boundaries

> **Status:** **Owner-approved pending Accepted** — Gabriel Approve 圖表 P0（2026-10-27 Asia/Hong_Kong）。**未標 Accepted**（等提案 PR／慣例三重閘）；**Merge ≠ Accepted ≠ runtime。**  
> **Owner lock（卡面，同日）：** ③確認繼續 **lightweight-charts v4.2.3**＋接受無完整內建畫線庫；①**Fib／測量入 P0**（自研 overlay）；②**P1（chat→圖）延後**。①零 order／②畫線只 Desk＝方向 C 已鎖（唔另問）。  
> **Binds under:** [ADR-003 + Addendum A](ADR-003-live-ai-trading-desk.md)（Accepted）> [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) > [AUDIT_REMEDIATION_PLAN_2026-10-21.md](AUDIT_REMEDIATION_PLAN_2026-10-21.md)（Confirmed 1–5）> [CHARTS_INDICATORS_DESIGN.md](CHARTS_INDICATORS_DESIGN.md)（Draft；GC1 跟本 ADR 引擎確認對齊）。  
> **Index：** [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md)。**ADR-002 is VOID.**  
> **Product direction C（Owner 鎖，2026-10-23）：** 雙殼一資料 — Streamlit 可唯讀鏡像 Desk 瀏覽（含 paper history）；**交易動作只 Desk**。Chat／Streamlit／圖表面：**零 order tools**（唔下單、唔暴露 submit／OrderManager）。  
> **Does not elevate：** Intent→M8、D7 schema 凍結、Desk flatten、fake verified／live、lab→OrderManager、Confirmed item 6。Issue #10 stays OPEN.  
> **Does not rewrite：** ADR-003 正文；live Harness／mandate／kill／風險％。**唔改 runtime。**  
> **Date：** 2026-10-27（Asia/Hong_Kong）  
> **Author lane：** Docs Arch（PM 可落 docs）；**唔寫執行碼。**

---

## 1. 背景｜Context

- ADR-003 北星：遠端 Desk 要有 TradingView-*style* 睇圖／指標；唔係宣稱已接 TradingView 官方。
- Desk **已 vendored** [TradingView Lightweight Charts **v4.2.3**](https://github.com/tradingview/lightweight-charts)（PR **#36** ns-1 charts v0）＋閉合經典指標集方向（對齊 CHARTS §7）。**本 ADR 唔係綠地選型**，而係 **確認既有引擎** 同鎖 **畫線／多殼能力邊界**。
- `CHARTS_INDICATORS_DESIGN`（Draft）**GC1** 原先寫「建議預設 lightweight-charts、未鎖」；程式已採用 **lightweight-charts v4.2.3**。**Gabriel ③ 已確認**（2026-10-27）：Desk 引擎＝既有 LC v4.2.3。本 ADR Status 仍係 **Owner-approved pending Accepted**（未標 Accepted）；CHARTS 頁維持 **Draft ≠ Accepted**。
- Vendored 引擎 **唔等於**「完整畫線庫已齊」或「對外可承諾 TradingView 級 drawing tools」。
- Chat＋圖表／TA 觀察功能要開工前，必須寫清：**既有引擎能做咩、做唔到咩、邊個殼係權威、邊啲係 P0／P2**，避免過度承諾（尤其畫線）。

---

## 2. 決策（Owner-approved — 確認既有引擎＋邊界）｜Decision

### D1. 產品圖表殼（對齊方向 C）

| 殼 | 角色 | 圖表／畫線 | Order tools |
|----|------|------------|-------------|
| **Desk**（FastAPI + `web/static`） | **產品權威** | 睇圖＋（若做）**權威畫線／註記** 嘅唯一寫入面 | 僅 Desk 既有交易入口（本 ADR **唔擴**）；圖表點擊／線／指標交叉 **唔係** M9／`OrderManager` 入口 |
| **Streamlit** | lab／legacy；方向 C = **唯讀鏡像** | 可鏡像 OHLCV／指標／已保存畫線嘅**唯讀顯示**；**唔**做權威畫線編輯器 | **零** order tools |
| **Chat／觀察助手** | 解讀／摘要／TA 觀察 | 可引用圖表狀態、指標數值、已保存線；可建議「去 Desk 畫／改」 | **零** order tools；**零** raw size／submit |

**接受陳述（Owner-approved）：** 一資料；雙殼。畫線真相只喺 Desk。Streamlit／Chat 睇得、講得，**落唔到單、改唔到權威線**（除非日後 Owner 另決並 Accepted）。

### D2. 引擎確認（GC1 — **Owner-approved：確認既有，非綠地**）

| 事實（repo） | 含義 |
|--------------|------|
| Desk 已 vendored **lightweight-charts v4.2.3**（PR #36） | 產品圖表渲染路徑已係 LC；**唔再開綠地選庫**（除非 Owner 另決換引擎） |
| 閉合指標集（SMA／EMA／BB／RSI／MACD 等）沿 CHARTS §7 | 指標＝衍生視圖；唔係畫線庫、唔係下單 |
| CHARTS GC1／UI UX 建議與現況一致 | Owner **③ 已確認**（2026-10-27）：Desk 引擎＝LC v4.2.3；接受無完整內建畫線庫 |

| 曾並列、現明確降級 | 決定（Owner-approved） |
|--------------------|------------------|
| Plotly.js 做 Desk 預設 | **否**（lab 可留；CHARTS GC5） |
| 官方 TradingView Widget／Charting Library | **否**（默認）；另決先要授權／Owner |
| 為「完整畫線」而換引擎或自研全套 canvas（P0） | **否**；畫線能力另見 D3／P2 |

**③ 已確認（Gabriel 2026-10-27）：** Desk 圖表引擎＝**lightweight-charts v4.2.3**（PR #36）；接受「無完整內建畫線庫」邊界。本 ADR Status＝**Owner-approved pending Accepted**（未標 Accepted 前，唔寫「引擎 ADR 已 Accepted」；實作可寫「Desk 現用 LC v4.2.3」）。

### D3. 能力邊界 — 尤其畫線（硬誠實）

**Lightweight Charts 預設 = 圖表渲染庫，唔係完整 TradingView 畫線套件。**

| 能力 | P0（必須／可承諾） | 明確唔承諾（除非另開 Accepted 工單） |
|------|-------------------|--------------------------------------|
| K 線＋volume pane | ✅ | — |
| 閉合經典 overlay／副圖（SMA／EMA／BB／RSI／MACD 等，跟 CHARTS §7） | ✅（參數可見） | 任意用戶腳本／Pine 執行引擎 |
| 十字線、legend、時框至少日線 | ✅ | 完整多屏 workspace／社群 |
| 數據 provenance（vendor／asof／fallback） | ✅ | Yahoo 扮 Polygon／verified |
| **完整 TradingView 級畫線庫**（矩形／平行通道／任意工具全集等） | ❌ **永不當 LC 內建承諾** | 唔寫「LC 已齊畫線」 |
| **Desk 畫線 v1 最小集**（趨勢線／水平線／**Fib**／**測量**） | **Owner 已批准 → P0 交付**；實作＝**自研 overlay**（或明確標註之 plugin），**非**宣稱 LC 內建齊；永遠標「最小畫具＝自研 overlay」 | TV 完整畫線庫 |
| 保存／重載用戶畫線 | 隨畫線 v1（P0）一併；存 Desk 權威 Drawing store | Streamlit／Chat 寫入權威線 |
| 多 timeframe 同步、bar replay／回放 | **P2**（見 §3） | 當未排期嘅 P0 默認 |
| 圖表 → 下單／一鍵買入 | **永遠禁止**（本 ADR + 方向 C） | 「觀察＝執行」 |

**過度承諾禁令：** UI／Chat／文件禁止寫「同 TradingView 一樣齊畫線」「完整 drawing tools 已內建於 lightweight-charts」。只可寫「TradingView-*style* 可讀性」＋當前真實能力清單。

**用語對齊（Coding／UI UX）：** P0「最小畫具」＝**自研 overlay** 疊喺 LC 之上，**唔係** LC 產品功能清單。Desk 畫線 v1 最小集（趨勢／水平／Fib／測量）——**Owner 已批准入 P0**；永遠保留「唔承諾＝TV 完整畫線庫」。**P1（chat→圖）延後**（Gabriel 卡面②）。

### D4. 權威畫線 vs 唯讀鏡像

```text
[User draws / edits] → Desk only → DrawingStore（proposed 名；未實作）
                              ↓ read
              Streamlit mirror（RO）    Chat observer（RO cite）
```

- **Desk：** 唯一可 create／update／delete 畫線（若畫線功能 Accepted 後實作）。
- **Streamlit：** 只讀同一資料；無編輯工具或編輯結果丟棄／拒寫。
- **Chat：** 可讀座標／標註做 TA 觀察；改線指令 = 引導去 Desk，**唔**静默改庫。

### D5. 證據閘（繼承，唔放寬）

圖表／畫線／Chat 觀察 **永遠唔 stamp** `verified`／`live`；指標／線 ≠ fill ≠ `RISK_APPROVED`；缺 bar ≠ 假 close；paper ≠ live。對齊 ADR-003 §4、CHARTS §5。

---

## 3. P0 必須 vs P2 取捨｜Priority split

| 層級 | 範圍 | 做 | 不做（推去 P2 或另決） |
|------|------|----|------------------------|
| **P0** | 圖表／TA **觀察**＋最小畫具可用、誠實 | Desk：可靠 K 線＋volume＋閉合指標＋provenance；Desk 畫線 v1（趨勢／水平／**Fib**／**測量**）＝**自研 overlay**；Chat：讀價／指標／解釋、**零下單**（chat→圖 **P1 延後**）；Streamlit：唯讀鏡像；文件標清「LC 無完整內建畫線」 | TV 完整畫線庫；多 TF 聯動；replay；官方 TV embed；期權／黃金圖 SKU；把最小畫具寫成「LC 內建」；P1 chat→圖（延後） |
| **P2** | 進階研究體驗 | 見下表 P2 acceptance | 用 P2 能力當「引擎已選＝已交付」；P2 完成前對外宣稱齊全 |

**取捨原則：** 先令「睇得清楚、講得明白、落唔到單」穩定，再加「畫得多、回放得多」。唔用 P2／延後嘅 P1 塞進 P0 驗收。

### P2 acceptance 細項（可引用 Internet Bot／UI UX 對齊）

| P2 項 | 接受條件 | 硬邊界 |
|-------|----------------------|--------|
| **Bar replay** | 可逐步／區間回放歷史 bar，供觀察與教學 | **回放進行中禁止任何交易動作**（Desk 亦要擋 replay-session 下單）；replay ≠ live／paper 實盤時鐘 |
| **Drawing templates** | Desk 可存／套用命名模板（一組線／區） | 模板只寫入 Desk 權威 Drawing store；Streamlit／Chat **唔**寫模板 |
| **Read my drawings** | Chat／觀察助手可呼叫唯讀 API，回傳 **JSON**（座標、類型、symbol、tf、asof） | JSON＝觀察資料，**唔係**下單指令；無 order fields |
| **多 TF** | 多 timeframe 切換／對齊（若排期） | 唔當 P0；唔暗示引擎內建齊全畫線 |
| **Desk 畫線超出最小集** | 矩形／通道／更多工具、進階模板等（若排期） | 最小集（趨勢／水平／Fib／測量）屬 **P0＋自研 overlay**；LC 仍無完整內建畫線庫 |
| **P1 chat→圖**（延後） | Chat 驅動圖表焦點／標註聯動（若日後排期） | **Gabriel 卡面②：P1 延後**；唔當 P0；零 order tools 不變 |

對齊備註：UI UX 線框以 Desk＝Drawing store 權威為準；本 ADR 不改線框，只鎖文件邊界。

---

## 4. 後果｜Consequences

**正面**

- Chat／觀察功能可開工，唔誤導用戶以為有完整畫線或可從圖下單。
- 方向 C 雙殼邊界寫死：權威喺 Desk；鏡像／Chat 唯讀。
- 同 CHARTS GC1：引擎確認既有 LC v4.2.3；畫線誠實邊界寫死。

**代價**

- 若用戶期望「開箱齊 TradingView 畫線」，要文案管理預期；P0＝Owner 批准嘅**最小畫具（自研 overlay，含 Fib／測量）**，永遠唔等於完整 TV 畫線庫；P1 chat→圖延後。
- Streamlit 現有 Plotly 畫線／互動若存在，要降級或標 lab-only，避免同 Desk 權威衝突。

---

## 5. Owner 拍板紀錄｜Resolved（升格前題已齊）

| # | 題 | 結果 |
|---|----|------|
| **① 零 order** | Chat／Streamlit／圖表是否堅持 **零 order tools**？ | **是** — 方向 C 已鎖（2026-10-23）；唔另問 |
| **② 畫線權威** | 畫線權威是否 **只 Desk**；Streamlit／Chat 唯讀？ | **是** — 方向 C 已鎖 |
| **③ 引擎** | 是否 **確認既有** Desk 引擎＝**lightweight-charts v4.2.3**，並接受「無完整內建畫線庫」？ | **是** — Gabriel 2026-10-27 |
| **卡面① Fib／測量** | Fib／測量是否入 P0（自研 overlay）？ | **是** — Gabriel Approve 圖表 P0 |
| **卡面② P1** | chat→圖 | **延後** — 唔入今次 P0 |

**Status：** Owner-approved pending Accepted。寫入 ARCHITECTURE_DECISION 索引為 Owner-approved／未 Accepted；**唔改產品預設／runtime。**

---

## 6. 唔得宣稱｜Must not claim

1. Owner-approved＝Accepted／引擎 ADR 已定案（未過提案 PR／慣例三重閘前）。  
2. lightweight-charts＝完整 TradingView 畫線庫。  
3. Chat／Streamlit 可下單或改權威畫線。  
4. 多 TF／replay／P1 chat→圖 已係 P0 交付。  
5. ADR-002 仍有效；Confirmed 變成 6 項；Issue #10 已關。  
6. 本檔合入＝改 runtime／產品預設。

---

## 7. Out of scope（本輪 docs 落庫）

- 改 runtime、寫前端／worker 執行碼、改產品預設 config。  
- 改寫 ADR-003；凍結 D7 參考訊號 schema。  
- 採購官方 Charting Library；期權／黃金圖 SKU。  
- 實作 P1 chat→圖（已延後）；標本 ADR 為 Accepted（等提案 PR／三重閘）。

---

## 8. 權威次序｜Authority

1. ADR-003 + Addendum A  
2. MODULAR_ARCHITECTURE  
3. AUDIT_REMEDIATION_PLAN（Confirmed 1–5）  
4. CHARTS_INDICATORS_DESIGN（Draft；圖表產品範圍）  
5. **本 ADR-004（Owner-approved；Accepted 之後升格）** — 引擎選型＋畫線／殼邊界  
6. 舊 roadmap（frozen）；**ADR-002 VOID**

衝突時：Owner 拍板 > ADR-003 > 本 ADR（Owner-approved pending Accepted）。

---

*Drafted 2026-10-27 by Docs Arch；Owner-approved 2026-10-27（Gabriel：P0＋③ LWC v4.2.3＋Fib／測量入 P0 自研 overlay；P1 延後）。唔承諾 TV 完整畫線庫。Owner-approved ≠ Accepted ≠ runtime。*
