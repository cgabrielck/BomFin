# ADR-006 — 富途 OpenD → Desk 觀察層｜Futu OpenD Desk Observe

> **Status:** **Draft**（pending Owner/PM Accepted）。**尚未 Accepted。** **Date：** 2026-11-10（Asia/Hong_Kong / HKT）。  
> **設計別名：** `FUTU_OPEND_DESK_OBSERVE`。本檔係架構決策草擬，**不是**施工單，也不是已上線的行情。  
> **基底：** `main` @ `5e29dde8`（#59）。本檔不改該提交的 Desk 殼。  
> **Binds under:** [ADR-003 + Addendum A](ADR-003-live-ai-trading-desk.md)（Accepted）> [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) > [AUDIT_REMEDIATION_PLAN_2026-10-21.md](AUDIT_REMEDIATION_PLAN_2026-10-21.md)（Confirmed 1–5 **不變**）> [ADR-004](ADR-004-chart-engine.md)（Accepted）> [ADR-005](ADR-005-mobile-desk-readonly.md)（**Draft**，本檔不升格其 Status）> **本 Draft**。  
> **ADR-002 is VOID.** Issue **#10 stays OPEN.**  
> **Merge ≠ Accepted ≠ runtime。** **no live。** **Draft ≠ Accepted**（要 Owner 於閘後標 Accepted）。**HOLD** for triple gate。本輪 **docs-only**；不改 runtime／`web/static`／backend／config／risk／mandate／kill／`OrderManager`／券商 adapter。  
> **Index：** [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md)。  
> **Author lane：** Docs Arch。不寫執行碼。  
> **對齊：** Option C 雙殼。**Desk**（FastAPI + `web/static`）＝產品面；**Streamlit ≠ 本路徑主面**（lab／legacy）。  
> **對齊 [DATA_FEED_AND_SUBSCRIPTIONS.md](DATA_FEED_AND_SUBSCRIPTIONS.md) §9：** 券商（**Alpaca paper**）≠ 研究帶／觀察帶。本 Draft 是 Owner 自營的 OpenD **觀察**路徑，**不是**採購 SKU，**不**取代該頁「稍後再買 Massive Stocks Starter」的建議。  
> **觀察路徑零 order tools。** 不經本路徑下單、不呼叫富途交易介面、不改 RiskEngine／`OrderManager`／mandate／kill。

---

## 1. 背景｜Context

- Desk 需要比現有日線更細的時框：**1m／5m／15m／60m**，以及會更新的報價與分時（intraday）。
- 既有日線圖表路徑維持不動：Desk `GET /api/chart/{symbol}`（`interval: 1d`，`source_kind: daily_snapshot`）。OpenD **不**刪除、**不**靜默取代這條日 K。
- Owner 將在 **富途牛牛** 開啟 API 權限，並在本機啟用 **OpenD**。團隊可並行準備 Desk 觀察 adapter 的設計；**準備 ≠ 本 Draft 已 Accepted，≠ 可以改 runtime。** 落碼仍 **HOLD**，直到 Owner 於三重閘之後把本 ADR 標為 Accepted。
- 產品殼是 **Desk**。Streamlit 不是這條觀察路徑的主面。方向 C：一資料、雙殼；交易動作只在 Desk 既有入口，**不**從圖表或觀察報價長出新的下單工具。
- 紙上券商仍是 **Alpaca paper**。富途在本決策裡只提供觀察用行情閘道，不是第二個下單券商。

---

## 2. 決策｜Decision（Draft — 未 Accepted）

### D1. OpenD 是本機守護進程；Desk 只經觀察 adapter 與它說話

**採納（Draft）：** OpenD 由 Owner 在自己的機器上跑，作為富途 OpenAPI 的本機閘道。Desk **不**把富途交易站當雲端 REST 直接叫，也 **不**在本倉庫裡再造一個券商。Desk 與 OpenD 之間只放一層 **observe adapter**。

連線位址（host／port）由 Owner 設定。富途文件常見的預設是本機 `127.0.0.1:11111`；該預設 **不是**本檔已部署的事實。若 Desk 與 OpenD 不在同一台機器，拓撲 **待 Owner 核對**，而且只能走私有路徑。本 Draft **不**授權 Funnel、ngrok，或任何公網隧道。

Adapter 只使用行情上下文（概念上對齊富途 `OpenQuoteContext`）。**不得**建立交易上下文（`OpenSecTradeContext`）、**不得**解鎖交易、**不得**送出富途委託。

### D2. 範圍｜Scope IN／Scope OUT

| | 內容 |
|--|------|
| **Scope IN** | 訂閱報價、分時、細時框 K 線（**1m／5m／15m／60m**）。Desk **GET** 路徑，以及 **可選 WS** 路徑，都在本檔寫成草圖（見 §4）。回應帶來源標籤與 provenance。 |
| **Scope OUT** | 富途下單、改單、撤單；任何對 RiskEngine、`OrderManager`、mandate、kill 的改動；live trading；用富途取代 **Alpaca paper** 作為券商；把 OpenD 行情寫進日線 `/api/chart` 並聲稱為唯一日 K；公網暴露 OpenD。 |

觀察路徑上的工具清單 **沒有** order。圖表上的報價、細 K、分時 **≠** 委託，**≠** `RISK_APPROVED`。

### D3. 代碼對照｜Symbol mapping

Desk 內部代碼與 `/api/chart/{symbol}` 相同：大寫、不帶市場前綴（例：`AAPL`）。富途代碼帶市場前綴。

| 方向 | 規則 | 例 |
|------|------|----|
| 內部 → 富途 | 本輪只處理美股。前綴 `US.` | `AAPL` → `US.AAPL` |
| 富途 → 內部 | 僅當代碼以 `US.` 開頭時，去掉這一個前綴，**保留代碼內部的點** | `US.AAPL` → `AAPL`；`US.BRK.B` → `BRK.B` |
| 其他市場 | `HK.`／`SH.`／`SZ.` 等 **不**猜測、**不**靜默改寫 | 回誠實錯誤 `unmapped_symbol` |

本 Draft 的第一刀只覆蓋 Desk 日線路徑已經使用的那種內部代碼。不另造第二套代碼表。`US.BRK.B` 這類對照只說明前綴規則；不表示該代碼已在宇宙內，也不表示已訂閱成功。

### D4. 來源標籤｜Source label

觀察回應的來源標籤是 **`futu_opend`**（欄位名 `source`）。若同時帶 `vendor`，其值必須相同，不得寫成 `yahoo`、`polygon` 或其他供應商。

**不得** stamp `verified` 或 `live`。草圖裡這兩個欄位若出現，值只能是 `false`。未來實作應像現有 `/api/chart` 一樣，拒絕 `verified: true` 與 `live: true`。有報價、有細 K、有推送，都不等於已核實，也不等於真倉。

### D5. 與日線圖表並存

| 路徑 | 角色 | 本 Draft |
|------|------|----------|
| `GET /api/chart/{symbol}` | 既有 **日線**（`interval: 1d`） | **保持**。OpenD 不刪除其 bars，不把日線 vendor 改寫成 `futu_opend`，不用細 K 覆蓋這份日線快照 |
| 觀察 GET／可選 WS | **報價、分時、1m／5m／15m／60m** | 平行序列。失敗時只影響觀察回應，不回寫日線 |

日線路徑今天用哪個 vendor（含既有 fallback），仍由那條路徑自己的標籤說明。觀察路徑 **不得**在 OpenD 失敗時改叫 Yahoo（或日線 fetcher），再把結果標成 `futu_opend`。

### D6. 失敗與額度用盡｜Honest degrade

| 情況 | 回應 | 禁止 |
|------|------|------|
| OpenD 不可達 | `degraded: true`，`error: opend_unreachable`，價格與 bars 為空 | 假 close、假 last、把空窗填成上一根的收盤 |
| 無權限 | `error: permission_denied` | 把無權限說成「仍是即時」 |
| 訂閱或歷史 K 額度用盡 | `error: quota_exhausted` | 靜默改走 Yahoo，再標 `futu_opend` |
| 代碼不在本輪對照 | `error: unmapped_symbol` | 猜港股／A 股前綴 |
| 推送中斷 | 保留最後一次真實 `asof`，`degraded: true` | 為缺掉的那根 K 編造 close |

沒有 bar 就是沒有 bar。缺值用空序列與 `null`，不用 0 價冒充成交。

### D7. 狀態語意｜Draft ≠ Accepted ≠ runtime

- 本檔是 **Draft**。Owner 開通富途 API、或團隊並行準備 adapter，**都不是** Accept。
- **Draft ≠ Accepted：** Owner 於閘後標 Accepted 之前，決策未生效。
- **Merge ≠ Accepted ≠ runtime：** 即使日後合入，只是文件落庫。不改 runtime，不等於已有 OpenD adapter，不等於已在訂閱，不等於 live。
- **no live。** 不開 live，不改 live Harness／mandate／kill／風險％，不用富途送單。
- **HOLD** for triple gate。未過閘前，本 Draft **不是**施工授權，也不是開 live 授權。
- Confirmed 1–5 **不變**。不把本檔寫成 Confirmed item 6。Issue #10 **OPEN**。ADR-002 **VOID**。ADR-005 維持 **Draft**。

---

## 3. 依賴｜Dependencies

本決策要成立，下面幾項必須由 Owner 提供。本檔 **不**代填帳號狀態。

| 依賴 | 誰 | 本 Draft 的寫法 |
|------|----|----------------|
| 富途牛牛 API 權限已開 | Owner | 未開則 adapter 不得假造報價 |
| OpenD 已在 Owner 機器啟用，Desk 經私有位址可達 | Owner | host／port **待 Owner 核對** |
| 美股即時（推廣期，**若適用**） | Owner 帳戶 | 若帳戶正處於富途牛牛美股即時行情推廣期，觀察層只使用該權限**實際覆蓋**的報價。推廣是否仍有效、覆蓋哪些市場、到期日，一律 **待 Owner 核對**。推廣期不是永久即時，也不是 `verified`／`live` |
| Desk 觀察 adapter | 日後實作（本輪不寫碼） | 只做 §2 Scope IN。零 order tools |

### 額度占位｜Quota placeholder

下表 **沒有**額度數字，也 **沒有**美元或港幣價格。格子維持「待 Owner 核對」，避免把記憶中的官網數字寫成事實。

| 項目 | 本檔記載 | 狀態 |
|------|----------|------|
| 訂閱檔位（subscribe slots） | 待 Owner 核對 | 待 Owner 核對 |
| 歷史 K 線額度（historical K） | 待 Owner 核對 | 待 Owner 核對 |
| 分時／`RT_DATA` 是否在權限內 | 待 Owner 核對 | 待 Owner 核對 |
| 美股即時推廣是否有效、到期日 | 待 Owner 核對 | 待 Owner 核對 |
| 月費或任何標價 | **本檔不記載價格** | 不發明標價；OpenD 觀察 **不是** DATA_FEED 的採購 SKU |

額度用盡時走 §D6 的誠實降級，不自動改買另一條帶，也不改 DATA_FEED 的 Massive Stocks Starter「稍後再買」建議。

---

## 4. 介面草圖｜Interface sketch

以下路徑與欄位是 **草圖，未實作**。Accepted 之前可以改名，邊界不可改：獨立於 `/api/chart`，只讀觀察，來源必為 `futu_opend`，零 order。

### 4.1 Adapter 邊界

```text
OpenD（Owner 本機守護進程，行情閘道）
        ▲  只行情（OpenQuoteContext）
        │  無交易上下文、無 place／unlock
FutuObserveAdapter          source = futu_opend
  subscribe(symbols, kinds)
  quote(symbol)
  bars(symbol, tf)
  unsubscribe(symbols, kinds)
        ▲
Desk 草圖路由（未掛載）
  GET  /api/observe/quote/{symbol}
  GET  /api/observe/bars/{symbol}?tf=1m|5m|15m|60m
  WS   /api/observe/stream          （可選）
```

`kinds`／`tf` 只允許：`quote`、`intraday`、`1m`、`5m`、`15m`、`60m`。

| Desk | 富途訂閱子類型（草圖名） | 備註 |
|------|--------------------------|------|
| `quote` | `QUOTE` | 快照＋訂閱 |
| `intraday` | `RT_DATA` | 分時；權限 **待 Owner 核對** |
| `1m` | `K_1M` | |
| `5m` | `K_5M` | |
| `15m` | `K_15M` | |
| `60m` | `K_60M` | |
| 日線 | （不經本 adapter 取代） | 仍走 `GET /api/chart/{symbol}` |

Adapter **不得**提供：`place_order`、`modify_order`、`cancel_order`、`unlock_trade`，以及任何 import `OrderManager`、RiskEngine、mandate、kill 的入口。

### 4.2 Desk GET 與可選 WS

- **GET quote：** 一個內部代碼的最新報價。無資料則 `last: null`，並帶 `error`。
- **GET bars：** `tf` 為 `1m`｜`5m`｜`15m`｜`60m`。無資料則 `bars: []`。
- **可選 WS：** OpenD 推送經 adapter 轉成同一套 provenance 的幀。未做 WS 時不得假造一條「已連線」。WS 與 GET 都 **不得**帶下單欄位。

WS 是可選路徑：未來可以先做 GET。驗收清單仍把「GET 與 WS 都存在」留作未勾項；在 Owner 另示「本輪不做 WS」之前，該項保持未勾，本 ADR 也因此 **不能**被說成已實作完成。

### 4.3 Provenance

成功草圖（數值皆為說明用，不是現網回應）：

```json
{
  "symbol": "AAPL",
  "vendor_symbol": "US.AAPL",
  "source": "futu_opend",
  "interval": "1m",
  "asof": "2026-11-10T01:35:00Z",
  "fetched_at": "2026-11-10T01:35:01Z",
  "degraded": false,
  "error": null,
  "bars": [],
  "verified": false,
  "live": false
}
```

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

`source` 必須是 `futu_opend`。`verified`／`live` 不得為 `true`。`error` 用 §D6 的閉集：`opend_unreachable`、`permission_denied`、`quota_exhausted`、`empty`、`unmapped_symbol`。

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

---

## 6. 不得宣稱｜Must not claim

1. 本 Draft 已是 Accepted，或「Owner 將開 API／團隊並行準備 adapter」等於 Owner 已 Accept 本 ADR。  
2. 合入本檔＝ runtime 已改、OpenD 已接通、觀察路由已掛、或 live 已開。  
3. 富途／OpenD 是下單券商，或已取代 Alpaca paper。  
4. 觀察報價或細 K 可以 stamp `verified`／`live`，或等於成交、seal、`RISK_APPROVED`。  
5. 缺 bar 或額度用盡時，可以用假 close，或把 Yahoo（或其他日線來源）標成 `futu_opend`。  
6. 本路徑取代 DATA_FEED 的 Massive Stocks Starter「稍後再買」建議，或 OpenD 是該頁的採購 SKU。  
7. ADR-002 仍有效；Confirmed 變成 6 項；Issue #10 已關；ADR-005 已被本檔升為 Accepted。  
8. Funnel、ngrok 或公網暴露是本觀察路徑的接法。那些與本決策無關，也不是後備。  
9. confetti、FOMO，或「已核實即時」話術。

---

## 7. Out of scope

- 任何 runtime、`web/static`、backend、config、risk／mandate／kill、`OrderManager`、券商 adapter；開 live。  
- 實作 OpenD 客戶端、訂閱、GET／WS、UI 來源標。本檔只定邊界與驗收，**HOLD** 到 Accepted。  
- 改寫 ADR-003、ADR-004 Accepted 正文；升格 ADR-005；改寫 DATA_FEED 的購買建議正文。  
- 富途下單、解鎖交易、以富途 paper／live 帳戶取代 Alpaca。  
- 把 Confirmed 1–5 擴成第 6 項。  
- 為本路徑做公網隧道。  
- 發明訂閱檔數、歷史 K 額度、或任何標價。

---

## 8. 權威次序｜Authority

1. ADR-003 + Addendum A  
2. MODULAR_ARCHITECTURE  
3. AUDIT_REMEDIATION_PLAN（Confirmed 1–5）  
4. ADR-004（Accepted）  
5. ADR-005（Draft；本檔不升格它）  
6. **本 ADR-006（Draft，2026-11-10）** — 未 Accepted；低於上列  
7. 舊 roadmap（frozen）；**ADR-002 VOID**

衝突時：ADR-003 > MODULAR > AUDIT > ADR-004 > ADR-005 Draft > 本 Draft。本 Draft 未 Accepted 前，不推翻上列。DATA_FEED 的券商 ≠ 研究帶／觀察帶仍然有效；Massive Stocks Starter 仍是該頁的稍後購買建議，不是本檔的交付物。

---

*Drafted 2026-11-10（Asia/Hong_Kong）by Docs Arch。設計別名 `FUTU_OPEND_DESK_OBSERVE`。基底 `main` @ `5e29dde8`（#59）。Status＝**Draft**，pending Owner/PM Accepted。docs-only。**Merge ≠ Accepted ≠ runtime。no live。HOLD** for triple gate。觀察 only。零富途下單。Alpaca paper 券商不變。*
