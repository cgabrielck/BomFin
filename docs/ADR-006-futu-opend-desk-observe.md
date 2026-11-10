# ADR-006 — 富途 OpenD → Desk 觀察層｜Futu OpenD Desk Observe

> **Status:** **Accepted**（Gabriel，2026-11-10，Asia/Hong_Kong / HKT）。**Accepted ≠ runtime。** **Date：** 2026-11-10（Asia/Hong_Kong / HKT）。  
> **設計別名：** `FUTU_OPEND_DESK_OBSERVE`。本檔係已接受的架構決策，**不是**施工單，也不是已上線的行情。實作不在本變更。  
> **基底：** 本 Accepted 修訂起自 `main` @ `75ef6728f665bbae6c700bb2dc92287664a045cd`（#60；Draft ADR-006 已入庫，當時 Status 仍為 Draft）。原草擬不改 `5e29dde8`（#59）的 Desk 殼；本修訂同樣不改 runtime。  
> **Binds under:** [ADR-003 + Addendum A](ADR-003-live-ai-trading-desk.md)（Accepted）> [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) > [AUDIT_REMEDIATION_PLAN_2026-10-21.md](AUDIT_REMEDIATION_PLAN_2026-10-21.md)（Confirmed 1–5 **不變**）> [ADR-004](ADR-004-chart-engine.md)（Accepted）> **本 ADR-006（Accepted；只綁 OpenD 觀察路徑）**。  
> **ADR-005** 維持 **Draft**，主題是行動端唯讀（mobile RO），**不同主題**。本檔不升格它，也 **不得** 把它寫成高於本 Accepted。  
> **ADR-002 is VOID.** Issue **#10 stays OPEN.**  
> **Merge ≠ Accepted ≠ runtime。** **no live。** **paper only。** 本輪 **docs-only**；不改 runtime／`web/static`／backend／config／risk／mandate／kill／`OrderManager`／券商 adapter。不實作觀察 adapter。  
> **Index：** [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md)。  
> **Author lane：** Docs Arch。不寫執行碼。Status 由 Gabriel 於 2026-11-10（Asia/Hong_Kong / HKT）標為 Accepted。  
> **對齊：** Option C 雙殼。**Desk**（FastAPI + `web/static`）＝產品面；**Streamlit ≠ 本路徑主面**（lab／legacy）。  
> **對齊 [DATA_FEED_AND_SUBSCRIPTIONS.md](DATA_FEED_AND_SUBSCRIPTIONS.md) §9：** 券商（**Alpaca paper**）≠ 研究帶／觀察帶。本決策是 Owner 自營的 OpenD **觀察**路徑，**不是**採購 SKU，**不**取代該頁「稍後再買 Massive Stocks Starter」的建議，也 **不是** Harness 研究帶。  
> **觀察路徑零 order tools。** 不經本路徑下單、不呼叫富途交易介面、不改 RiskEngine／`OrderManager`／mandate／kill。Alpaca paper 仍是唯一下單路徑。交易維持鎖定。

---

## 1. 背景｜Context

- Desk 需要會更新的報價、分時，以及圖表時框。閉集見 **D9**：官方原生 KLType 全套，另加必須標成合成的 **5h／3d／5d**。Owner 要的是 **1m／3m／5m／10m、1h、5h、1d／3d／5d**。不再只以 1m／5m／15m／60m 為全部。
- 既有日線圖表路徑維持不動：Desk `GET /api/chart/{symbol}`（`interval: 1d`，`source_kind: daily_snapshot`）。OpenD **不**刪除、**不**靜默取代這條日 K。
- Owner 自營的 OpenD（**10.12.7208**）與權限已於 **2026-11-10** 核對（見 §3、**D10**）。本檔不記載帳號、使用者名稱或其他帳戶識別。**Gabriel 已於 2026-11-10（Asia/Hong_Kong / HKT）把本 ADR 標為 Accepted。** Accepted **≠** runtime，**≠** 本變更已接上 OpenD。觀察 adapter 的落碼是 **日後另一份 PR**；該實作 PR 仍 **HOLD**，要另行過閘。本文件變更不含實作。
- 產品殼是 **Desk**。Streamlit 不是這條觀察路徑的主面。方向 C：一資料、雙殼；交易動作只在 Desk 既有入口，**不**從圖表或觀察報價長出新的下單工具。
- 紙上券商仍是 **Alpaca paper**。富途在本決策裡只提供觀察用行情閘道，不是第二個下單券商。

---

## 2. 決策｜Decision（Accepted）

### D1. OpenD 是本機守護進程；Desk 只經觀察 adapter 與它說話

**採納：** OpenD 由 Owner 在自己的機器上跑，作為富途 OpenAPI 的本機閘道。Desk **不**把富途交易站當雲端 REST 直接叫，也 **不**在本倉庫裡再造一個券商。Desk 與 OpenD 之間只放一層 **observe adapter**。

連線由 Owner 設在本機。**2026-11-10** Owner 已核對：API port **11111**，listen **本機（local）**。這是已核對的觀察，不再只是文件常見預設。它仍 **不是**把 OpenD 部署成公網端點。若 Desk 與 OpenD 不在同一台機器，只能走私有路徑。本決策 **不**授權 Funnel、ngrok，或任何公網隧道。

Adapter 只使用行情上下文（概念上對齊富途 `OpenQuoteContext`）。**不得**建立交易上下文（`OpenSecTradeContext`）、**不得**解鎖交易、**不得**送出、修改或撤銷富途委託。交易維持鎖定，**保持鎖定**。本檔不寫任何解鎖步驟。

### D2. 範圍｜Scope IN／Scope OUT

| | 內容 |
|--|------|
| **Scope IN** | 按需訂閱報價、分時、K 線。用量硬限見 **D8**。時框閉集見 **D9**（官方原生 KLType 全套，加上必須標 **synthesized** 的 5h／3d／5d）。Desk **GET** 與 **可選 WS** 仍是草圖（§4）。回應帶來源標籤與 provenance（原生或合成必須可見）。 |
| **Scope OUT** | 富途下單、改單、撤單、解鎖交易；任何對 RiskEngine、`OrderManager`、mandate、kill 的改動；live trading；用富途取代 **Alpaca paper** 作為券商；期權觀察或期權下單（額度只記錄，見 **D10**）；把 OpenD 當 Harness 研究帶、掃描器、全股票池或宇宙預熱；把 OpenD 行情寫進日線 `/api/chart` 並聲稱為唯一日 K；把 5h／3d／5d 說成官方 KLType；因港股 LV1 就把代碼對照擴到 HK／SH／SZ；公網暴露 OpenD；在本文件變更裡實作 adapter。 |

觀察路徑上的工具清單 **沒有** order。圖表上的報價、K 線、分時 **≠** 委託，**≠** `RISK_APPROVED`。**paper only。**

### D3. 代碼對照｜Symbol mapping

Desk 內部代碼與 `/api/chart/{symbol}` 相同：大寫、不帶市場前綴（例：`AAPL`）。富途代碼帶市場前綴。

| 方向 | 規則 | 例 |
|------|------|----|
| 內部 → 富途 | 本輪只處理美股。前綴 `US.` | `AAPL` → `US.AAPL` |
| 富途 → 內部 | 僅當代碼以 `US.` 開頭時，去掉這一個前綴，**保留代碼內部的點** | `US.AAPL` → `AAPL`；`US.BRK.B` → `BRK.B` |
| 其他市場 | `HK.`／`SH.`／`SZ.` 等 **不**猜測、**不**靜默改寫 | 回誠實錯誤 `unmapped_symbol` |

本決策的第一刀只覆蓋 Desk 日線路徑已經使用的那種內部代碼。不另造第二套代碼表。`US.BRK.B` 這類對照只說明前綴規則；不表示該代碼已在宇宙內，也不表示已訂閱成功。

Owner 自營的 OpenD 於 2026-11-10 具港股 LV1（**D10**）。該權限 **不**授權把對照擴到 `HK.`／`SH.`／`SZ.`。未對照市場仍回 `unmapped_symbol`。美股指數於同日無權限；本決策不新增指數路徑。無權限時走 `permission_denied`，不假造報價。

### D4. 來源標籤｜Source label

觀察回應的來源標籤是 **`futu_opend`**（欄位名 `source`）。若同時帶 `vendor`，其值必須相同，不得寫成 `yahoo`、`polygon` 或其他供應商。

**不得** stamp `verified` 或 `live`。草圖裡這兩個欄位若出現，值只能是 `false`。未來實作應像現有 `/api/chart` 一樣，拒絕 `verified: true` 與 `live: true`。有報價、有細 K、有推送，都不等於已核實，也不等於真倉。

### D5. 與日線圖表並存

| 路徑 | 角色 | 本決策 |
|------|------|--------|
| `GET /api/chart/{symbol}` | 既有 **日線**（`interval: 1d`） | **保持**。OpenD 不刪除其 bars，不把日線 vendor 改寫成 `futu_opend`，不用細 K 或合成 K 覆蓋這份日線快照 |
| 觀察 GET／可選 WS | **報價、分時、D9 時框** | 平行序列。失敗時只影響觀察回應，不回寫日線 |

日線路徑今天用哪個 vendor（含既有 fallback），仍由那條路徑自己的標籤說明。觀察路徑 **不得**在 OpenD 失敗時改叫 Yahoo（或日線 fetcher），再把結果標成 `futu_opend`。

### D6. 失敗與額度用盡｜Honest degrade

| 情況 | 回應 | 禁止 |
|------|------|------|
| OpenD 不可達 | `degraded: true`，`error: opend_unreachable`，價格與 bars 為空 | 假 close、假 last、把空窗填成上一根的收盤 |
| 無權限 | `error: permission_denied` | 把無權限說成「仍是即時」 |
| 訂閱或歷史 K 額度用盡 | `error: quota_exhausted` | 靜默改走 Yahoo，再標 `futu_opend` |
| 無資料 | `error: empty`，價格與 bars 為空 | 用 0 價或上一根 close 冒充 |
| 代碼不在本輪對照 | `error: unmapped_symbol` | 猜港股／A 股前綴 |
| 推送中斷 | 保留最後一次真實 `asof`，`degraded: true` | 為缺掉的那根 K 編造 close |

沒有 bar 就是沒有 bar。缺值用空序列與 `null`，不用 0 價冒充成交。

日後實作必須遵守 **D8** 與 **D10** 的上限，並在 `quota_exhausted`、`opend_unreachable`、`permission_denied`、`empty`、`unmapped_symbol` 上誠實降級。無假 close。無靜默 Yahoo-as-Futu。來源標籤維持 `futu_opend`。不得 stamp `verified` 或 `live`。

### D7. 狀態語意｜Accepted ≠ runtime

- Status 為 **Accepted**。Gabriel 於 **2026-11-10**（Asia/Hong_Kong / HKT）接受本決策。
- **Accepted ≠ runtime。** 接受本 ADR，是授權**日後**的觀察 adapter 實作 PR 遵守這些約束；**不**在本變更交付 runtime，**不**掛路由，**不**連接 OpenD，**不**開 live。
- **Merge ≠ runtime** 仍然成立：即使本文件 PR 日後被 squash-merge，仍然沒有任何東西在執行。
- 實作是 **日後另一份 PR**。該實作 PR 仍 **HOLD**，要另行過閘。本文件變更本身不含實作。
- **no live。** 不開 live。`verified`／`live` 維持 `false`。零富途 order tools。Alpaca paper 仍是唯一下單路徑。**paper only。**
- Confirmed 1–5 **不變**。不把本檔寫成 Confirmed item 6。Issue #10 **OPEN**。ADR-002 **VOID**。ADR-005 維持 **Draft**（不同主題：行動端唯讀）。本檔不升格它。

### D8. 用量硬限｜On-demand only

**採納：** OpenD 觀察只按需，而且只對下面三類：

1. **目前圖表上的那一個代碼**（current chart symbol）
2. **紙上持倉**（paper／positions）
3. **一小份 Owner 自定的觀察清單**（small owner-defined watchlist）

約束：

- **離開即退訂**（unsubscribe on leave）。使用者離開該圖，或停止觀看時，退訂。
- **歷史 K 要快取**。不要無必要地重拉 hist K。
- **不做掃描器**，**不做全市場股票池**，**不預熱宇宙**（no scanners, no all-stock pools, no pre-warming a universe）。
- OpenD **不是** Harness 研究帶。回測、每日重跑，以及有閘門的策略自更新，留在可歸檔的研究帶（archivable research tape）。對齊 [DATA_FEED §9](DATA_FEED_AND_SUBSCRIPTIONS.md)：券商 ≠ 研究帶／觀察帶。OpenD 只做 Desk 觀察。

### D9. 圖表時框｜Native KLType 與合成

**採納：** 時框分成官方原生與合成。合成必須標成 **synthesized**，不得說成官方 KLType，也不得說成原生 OpenD 週期。

依據富途 OpenAPI **v10.12** 行情定義／KLType（頁面標題為 Futu API Doc v10.12）：<https://openapi.futunn.com/futu-api-doc/hk/quote/quote.html>。下表是該頁記載的原生 K 線類型全套。本決策不另造該頁沒有的 KLType 名稱。

| 官方 KLType | 該頁含義 |
|-------------|----------|
| `K_1M` | 1 分 K |
| `K_3M` | 3 分 K |
| `K_5M` | 5 分 K |
| `K_10M` | 10 分 K |
| `K_15M` | 15 分 K |
| `K_30M` | 30 分 K |
| `K_60M` | 60 分 K |
| `K_120M` | 120 分 K（2 小時） |
| `K_180M` | 180 分 K（3 小時） |
| `K_240M` | 240 分 K（4 小時） |
| `K_DAY` | 日 K |
| `K_WEEK` | 周 K |
| `K_MON` | 月 K |
| `K_QUARTER` | 季 K |
| `K_YEAR` | 年 K |

Owner 要求：**1m／3m／5m／10m、1h、5h、1d／3d／5d**。

- 原生已覆蓋 **1／3／5／10 分**、**60 分**、**日**，以及上表其餘官方週期：**15 分、30 分、2 小時、3 小時、4 小時、周、月、季、年**。官方條目對 `K_60M` 寫的是 60 分 K，沒有「1 小時」括註；Desk 的 `1h`／`60m` 對到這一個原生類型。
- **5h、3d、5d 不是原生。** 合成規則：
  - **5h** 由 **60 分** bars（`K_60M`）合成。
  - **3d** 與 **5d** 由 **日 K**（`K_DAY`）合成，為 **3／5 個交易日**（trading days），不是日曆日。
- 合成結果 **必須標成 synthesized**。不得呈現為原生 OpenD 週期。不得宣稱 5h／3d／5d 是官方 KLType。不得自造該官方頁面沒有的 KLType 名稱來稱呼這三個時框。
- 合成使用已快取的原生 bars，不把 5h／3d／5d 當成另一個官方週期再請求一次。
- Provenance 必須能看出原生或合成（欄位或標籤）。草圖見 §4：`bar_origin` 為 `native` 或 `synthesized`。

Desk 側 `tf` 與上表的對照（含合成）見 §4。`1h` 與 `60m` 是同一個原生 `K_60M`，不是兩個官方類型。

### D10. 額度與 OpenD 事實｜Quota（Owner 已核對）

**採納：** 下列事實於 **2026-11-10** 核對，取代原「待 Owner 核對」占位。帳戶只稱 **Owner 自營的 OpenD**。本檔不記載帳號、使用者名稱或其他帳戶識別，也 **不記載價格**。標成官方的句子是本輪列入的官方規則、深度或限頻，不是本檔另造的標價。數值表同時見 §3；兩處是同一組數字。

- 版本：Owner 自營的 OpenD **10.12.7208**。
- 最低檔：subscribe **100**；歷史 K **100** 個代碼／**7** 日。期權 **20／20**（與 subscribe／hist K 並列的期權額度；本檔不把「7 日」或代碼數外推成期權另有的窗口）。期權數字只作誠實記錄。本 ADR **不**新增期權觀察，也 **不**新增期權下單（Scope OUT）。
- 官方規則：同一代碼、不同週期＝**1** 個 hist K 槽；**7** 日內重複不重計。
- 歷史 K 線首頁 **≤60／30 秒**。
- 官方深度：分鐘 K 約 **8** 年；日 K 約 **20** 年。
- 權限（Owner 自營的 OpenD，2026-11-10）：美股 **LV3**；美股指數 **無權限**；港股 **LV1**。代碼對照仍只做美股（`AAPL` ↔ `US.AAPL`，**D3**）。港股 LV1 **不**把對照擴到 HK／SH／SZ；未對照市場仍回 `unmapped_symbol`。美股指數無權限，不新增指數路徑。
- 連線觀察見 **D1**：API port **11111**，listen **本機**。不是公網端點。無 Funnel／ngrok／公網隧道。
- **交易維持鎖定，保持鎖定。** 不寫解鎖步驟。無 `OpenSecTradeContext`，無下單、改單、撤單，無解鎖。
- 日後實作必須遵守這些上限，並在 `quota_exhausted` 以及 `opend_unreachable`、`permission_denied`、`empty`、`unmapped_symbol` 上誠實降級。無假 close。無靜默 Yahoo-as-Futu。來源標籤維持 `futu_opend`。不得 stamp `verified` 或 `live`。

分時（`RT_DATA`）是否在權限內，以及任何推廣到期日，都不在本輪已核對事實裡。不發明。LV3 **≠** `verified`／`live`。

---

## 3. 依賴｜Dependencies

本決策要成立，下面幾項已由 Owner 於 2026-11-10 核對，或仍屬日後實作。帳戶只稱 **Owner 自營的 OpenD**。本檔不代填、也不記載帳號、使用者名稱或其他帳戶識別。

| 依賴 | 誰 | 本決策的寫法 |
|------|----|----------------|
| OpenD 版本與權限 | Owner 自營的 OpenD **10.12.7208**，核對日 **2026-11-10** | 見下方額度表與 **D10**。無權限則不得假造報價 |
| OpenD 已在 Owner 機器啟用 | Owner | API port **11111**，listen **本機**。見 **D1**。不是公網端點 |
| 美股／指數／港股權限 | Owner 自營的 OpenD，2026-11-10 | 美股 **LV3**；美股指數 **無權限**；港股 **LV1**。代碼對照仍只做美股（**D3**） |
| Desk 觀察 adapter | 日後實作（本變更不寫碼） | 只做 §2 Scope IN。零 order tools。交易維持鎖定 |

### 額度｜Quota（2026-11-10 已核對；不記載價格）

下表取代原「待 Owner 核對」占位。與 **D10** 是同一組數字。本檔 **沒有**美元或港幣價格。

| 項目 | 本檔記載 | 狀態 |
|------|----------|------|
| OpenD 版本 | **10.12.7208** | Owner 核對 2026-11-10 |
| 最低檔：訂閱 | subscribe **100** | Owner 核對 2026-11-10 |
| 最低檔：歷史 K | **100** 個代碼／**7** 日 | Owner 核對 2026-11-10 |
| 期權額度（只記錄） | **20／20**（subscribe／hist K 的期權並列） | Owner 核對 2026-11-10。本 ADR **不**加期權觀察或期權下單。不外推 7 日窗口 |
| 歷史 K 佔位 | 同一代碼、不同週期＝**1** 個 hist K 槽；**7** 日內重複不重計 | 官方規則（本輪列入） |
| 歷史 K 首頁 | **≤60／30 秒** | 官方限頻（本輪列入） |
| 官方深度 | 分鐘 K 約 **8** 年；日 K 約 **20** 年 | 官方深度（本輪列入） |
| 權限 | 美股 **LV3**；美股指數 **無權限**；港股 **LV1** | Owner 核對 2026-11-10。對照仍只美股 |
| 連線 | API port **11111**，listen **本機** | Owner 核對 2026-11-10。見 **D1**。不是公網端點 |
| 交易 | **維持鎖定** | 不寫解鎖步驟。無交易上下文、無下單 |
| 月費或任何標價 | **本檔不記載價格** | 不發明標價；OpenD 觀察 **不是** DATA_FEED 的採購 SKU |

分時 `RT_DATA` 是否在權限內、以及任何推廣到期日，本輪未核對。不發明，也不把未核對項目寫成已開通。

額度用盡時走 **D6** 的誠實降級，不自動改買另一條帶，也不改 DATA_FEED 的 Massive Stocks Starter「稍後再買」建議。日後實作必須遵守上表與 **D8**：按需、離開退訂、歷史 K 先用快取。OpenD 不是 Harness 研究帶。

---

## 4. 介面草圖｜Interface sketch

以下路徑與欄位仍是 **草圖，未實作、未掛載**。決策已 **Accepted**，邊界已鎖：獨立於 `/api/chart`，只讀觀察，來源必為 `futu_opend`，零 order。`tf` 閉集與原生／合成標籤已鎖。實作不得把合成時框改稱官方 KLType，也不得增刪本表以外的時框。路由字串本身不是已上線的 API。

### 4.1 Adapter 邊界

```text
OpenD（Owner 本機守護進程，行情閘道；port 11111，listen 本機）
        ▲  只行情（OpenQuoteContext）
        │  無交易上下文、無 place／modify／cancel、無 unlock
FutuObserveAdapter          source = futu_opend
  subscribe(symbols, kinds)   只按需：目前圖表代碼、紙上持倉、或小份 Owner 觀察清單
  quote(symbol)
  bars(symbol, tf)            歷史 K 先讀快取；不無必要重拉
  unsubscribe(symbols, kinds) 離開圖表或停止觀看時退訂
        ▲
Desk 草圖路由（未掛載）
  GET  /api/observe/quote/{symbol}
  GET  /api/observe/bars/{symbol}?tf=1m|3m|5m|10m|15m|30m|1h|2h|3h|4h|1d|1w|1mo|1q|1y|5h|3d|5d
  WS   /api/observe/stream          （可選）
```

查詢字串寫 `1h`。`60m` 是同一原生 `K_60M` 的別名，不是第二個官方類型。用量與 **D8** 同一約束：不做掃描、不做全股票池、不預熱宇宙。OpenD 不是 Harness 研究帶。

`kinds`／`tf` 只允許下表。原生列的名稱來自富途 OpenAPI v10.12 KLType（<https://openapi.futunn.com/futu-api-doc/hk/quote/quote.html>）。

| Desk `tf`／`kind` | 富途 KLType 或合成 | 備註 |
|-------------------|--------------------|------|
| `quote` | （非 KLType）`QUOTE` | 快照＋訂閱 |
| `intraday` | （非 KLType）`RT_DATA` | 分時。2026-11-10 核對清單未包含此子類型是否在權限內；不發明 |
| `1m` | `K_1M` | 原生 |
| `3m` | `K_3M` | 原生 |
| `5m` | `K_5M` | 原生 |
| `10m` | `K_10M` | 原生 |
| `15m` | `K_15M` | 原生 |
| `30m` | `K_30M` | 原生 |
| `1h`（同 `60m`） | `K_60M` | 原生。60 分＝1 小時 |
| `2h` | `K_120M` | 原生。120 分＝2 小時 |
| `3h` | `K_180M` | 原生。180 分＝3 小時 |
| `4h` | `K_240M` | 原生。240 分＝4 小時 |
| `1d` | `K_DAY` | 原生。不取代 `GET /api/chart/{symbol}` 的日線快照 |
| `1w` | `K_WEEK` | 原生 |
| `1mo` | `K_MON` | 原生 |
| `1q` | `K_QUARTER` | 原生 |
| `1y` | `K_YEAR` | 原生 |
| `5h` | 由 `K_60M` 合成 | **`bar_origin: synthesized`**。不是官方 KLType |
| `3d` | 由 `K_DAY` 合成，**3 個交易日** | **`bar_origin: synthesized`**。不是官方 KLType |
| `5d` | 由 `K_DAY` 合成，**5 個交易日** | **`bar_origin: synthesized`**。不是官方 KLType |

Adapter **不得**提供：`place_order`、`modify_order`、`cancel_order`、`unlock_trade`，以及任何 import `OrderManager`、RiskEngine、mandate、kill 的入口。

### 4.2 Desk GET 與可選 WS

- **GET quote：** 一個內部代碼的最新報價。無資料則 `last: null`，並帶 `error`。
- **GET bars：** `tf` 只許 §4.1 表內的原生或合成值（`1m`｜`3m`｜`5m`｜`10m`｜`15m`｜`30m`｜`1h`／`60m`｜`2h`｜`3h`｜`4h`｜`1d`｜`1w`｜`1mo`｜`1q`｜`1y`｜`5h`｜`3d`｜`5d`）。無資料則 `bars: []`。回應必須帶 `bar_origin`。
- **可選 WS：** OpenD 推送經 adapter 轉成同一套 provenance 的幀。未做 WS 時不得假造一條「已連線」。WS 與 GET 都 **不得**帶下單欄位。訂閱仍受 **D8** 約束，離開即退訂。

WS 是可選路徑：未來可以先做 GET。驗收清單仍把「GET 與 WS 都存在」留作未勾項；在 Owner 另示「本輪不做 WS」之前，該項保持未勾，本 ADR 也因此 **不能**被說成已實作完成。

### 4.3 Provenance

成功草圖（數值皆為說明用，不是現網回應）。原生例：

```json
{
  "symbol": "AAPL",
  "vendor_symbol": "US.AAPL",
  "source": "futu_opend",
  "interval": "1m",
  "kl_type": "K_1M",
  "bar_origin": "native",
  "synthesized_from": null,
  "asof": "2026-11-10T01:35:00Z",
  "fetched_at": "2026-11-10T01:35:01Z",
  "degraded": false,
  "error": null,
  "bars": [],
  "verified": false,
  "live": false
}
```

合成草圖（5h **不是**官方 KLType；`kl_type` 必須為 `null`）：

```json
{
  "symbol": "AAPL",
  "vendor_symbol": "US.AAPL",
  "source": "futu_opend",
  "interval": "5h",
  "kl_type": null,
  "bar_origin": "synthesized",
  "synthesized_from": "K_60M",
  "asof": "2026-11-10T01:35:00Z",
  "fetched_at": "2026-11-10T01:35:01Z",
  "degraded": false,
  "error": null,
  "bars": [],
  "verified": false,
  "live": false
}
```

`3d`／`5d` 的 `bar_origin` 同為 `synthesized`，`synthesized_from` 為 `K_DAY`，`kl_type` 為 `null`，並帶交易日數（草圖欄位 `span_trading_days`：**3** 或 **5**）。這是交易日，不是日曆日。

額度用盡草圖：

```json
{
  "symbol": "AAPL",
  "vendor_symbol": "US.AAPL",
  "source": "futu_opend",
  "interval": "quote",
  "asof": null,
  "degraded": true,
  "error": "quota_exhausted",
  "last": null,
  "verified": false,
  "live": false
}
```

`source` 必須是 `futu_opend`。`verified`／`live` 不得為 `true`。`error` 用 §D6 的閉集：`opend_unreachable`、`permission_denied`、`quota_exhausted`、`empty`、`unmapped_symbol`。`bar_origin` 只許 `native` 或 `synthesized`。合成回應不得把 `kl_type` 填成一個官方清單沒有的名字。

---

## 5. 驗收｜Acceptance（日後實作；本輪不勾）

下列是 **日後實作** 的驗收。本 PR 只落文件，**不**聲稱任何一項已過，**不**勾選。

- [ ] 可訂閱至少 1 個代碼的即時報價（subscribe ≥ 1 symbol）
- [ ] Desk GET 路徑存在，且可選 WS 路徑存在
- [ ] 與既有日線 `GET /api/chart/{symbol}` 並存：OpenD 不刪日 K、不靜默取代日 K
- [ ] 來源標籤 `futu_opend` 在 UI 與 API 都可見；回應不 stamp `verified`／`live`

附帶邊界（同樣未勾，實作時要一併成立）：

- [ ] 觀察 adapter 無富途下單，且不改 RiskEngine／`OrderManager`／mandate／kill
- [ ] OpenD 失敗或額度用盡時是誠實錯誤／降級標籤；無假 close；無靜默 Yahoo-as-Futu
- [ ] Alpaca paper 仍是券商；本路徑不是第二個 broker
- [ ] 用量遵守 D8：只按需（目前圖表代碼、紙上持倉、或小份 Owner 觀察清單）；離開即退訂；歷史 K 有快取；無掃描器、無全股票池、無宇宙預熱；OpenD 不是 Harness 研究帶
- [ ] D9：原生與合成在 provenance 可分辨；5h／3d／5d 標成 synthesized，不說成官方 KLType
- [ ] 遵守 D10 額度與權限；不開期權觀察或期權下單；不寫解鎖交易；不公開帳戶識別

---

## 6. 不得宣稱｜Must not claim

1. 本檔 Status＝**Accepted** 等於 runtime 已改、路由已掛、OpenD 已接通、live 已開，或本文件變更授權把觀察 adapter 的實作碼併進同一份變更。  
2. 合入本檔＝ runtime 已改、OpenD 已接通、觀察路由已掛、或 live 已開。  
3. 富途／OpenD 是下單券商，或已取代 Alpaca paper。  
4. 觀察報價或細 K 可以 stamp `verified`／`live`，或等於成交、seal、`RISK_APPROVED`。  
5. 缺 bar 或額度用盡時，可以用假 close，或把 Yahoo（或其他日線來源）標成 `futu_opend`。  
6. 本路徑取代 DATA_FEED 的 Massive Stocks Starter「稍後再買」建議，或 OpenD 是該頁的採購 SKU。  
7. ADR-002 仍有效；Confirmed 變成 6 項；Issue #10 已關；ADR-005 已被本檔升為 Accepted。  
8. Funnel、ngrok 或公網暴露是本觀察路徑的接法。那些與本決策無關，也不是後備。  
9. confetti、FOMO，或「已核實即時」話術。  
10. **5h、3d 或 5d** 是原生 OpenD 週期或官方 KLType。  
11. OpenD 是 Harness 研究帶，或可用來做掃描器、全股票池、宇宙預熱。回測、每日重跑、有閘門的策略自更新可以改吃 OpenD。  
12. 可以公開富途牛牛／牛牛的帳號、使用者名稱或其他帳戶識別。帳戶只稱 Owner 自營的 OpenD。  
13. 本檔附有解鎖交易步驟，或這份 Accepted 文件可以把交易鎖定打開。  
14. 本 Accepted 文件 PR 本身就是 runtime，或就是可以在同一變更裡合入程式的實作授權。

---

## 7. Out of scope

- 任何 runtime、`web/static`、backend、config、risk／mandate／kill、`OrderManager`、券商 adapter；開 live。本變更不實作觀察 adapter、不掛路由、不連接 OpenD。  
- 實作 OpenD 客戶端、訂閱、GET／WS、UI 來源標。那些是日後另一份 PR，不在本變更；該實作仍要另行過閘。  
- 改寫 ADR-003、ADR-004 Accepted 正文；升格 ADR-005；改寫 DATA_FEED 的購買建議正文。  
- 富途下單、改單、撤單；寫入解鎖交易步驟；以富途 paper／live 帳戶取代 Alpaca。  
- 期權觀察或期權下單。  
- 把 Confirmed 1–5 擴成第 6 項。  
- 為本路徑做公網隧道。  
- 把 5h／3d／5d 當成原生 OpenD 週期。  
- 把 OpenD 用作 Harness 研究帶、掃描器或宇宙預熱。  
- 公開富途牛牛／牛牛或任何帳戶識別。  
- 把這份 Accepted 文件變更當成 runtime，或在同一變更裡合入實作碼。  
- 發明本檔未記載的價格、額外額度、推廣到期日或權限事實。

---

## 8. 權威次序｜Authority

1. ADR-003 + Addendum A  
2. MODULAR_ARCHITECTURE  
3. AUDIT_REMEDIATION_PLAN（Confirmed 1–5）  
4. ADR-004（Accepted）  
5. **本 ADR-006（Accepted，Gabriel 2026-11-10 Asia/Hong_Kong / HKT）** — 只綁 OpenD 觀察路徑；**不**推翻 1–4  
6. 舊 roadmap（frozen）；**ADR-002 VOID**

ADR-005 維持 **Draft**。它是**另一主題**（行動端唯讀，mobile RO）。本檔不升格它。它 **不得** 被寫成高於本 ADR-006 Accepted。兩者不是同一條「誰取代誰」的鏈。

衝突時：ADR-003 > MODULAR > AUDIT > ADR-004 > 本 Accepted（僅 OpenD 觀察）。本 Accepted 不推翻上列。DATA_FEED 的券商 ≠ 研究帶／觀察帶仍然有效；Massive Stocks Starter 仍是該頁的稍後購買建議，不是本檔的交付物。OpenD 不是該頁的採購 SKU，也不是 Harness 研究帶。

---

*Accepted 2026-11-10（Asia/Hong_Kong / HKT）by Gabriel。設計別名 `FUTU_OPEND_DESK_OBSERVE`。本修訂起自 `main` @ `75ef6728f665bbae6c700bb2dc92287664a045cd`（#60）。docs-only。**Accepted ≠ runtime。** **Merge ≠ runtime。** **no live。** 實作不在本變更。觀察 only。零富途 order tools。Alpaca paper 仍是唯一下單路徑。交易維持鎖定。paper only。*
