# WU-9-ui — 指標疊圖、宏觀面板、來源能力標示

## 目標

在既有股票詳情工作區內，加上面向使用者的三件事：圖表上的指標疊圖、
獨立的宏觀面板、以及每個行情來源的能力標示。三者都必須把後端說的
真話原樣呈現，不能補前端自己猜的值。

## Base

- 後端 commit：`cd59fca1`（分析平面的生產接線 + e2e 覆蓋）
- 分支：`codex/s01-source-baseline`
- Checkout：`C:/Users/001/Downloads/GabFin-ai-trade/.worktrees/gabfin-s01`
- 前一階段：`5c49495a`（WU-7 + WU-9）、`9e7d109b`（交接卡）

## 後端已就緒、Carbon 可直接對接的事實

這三點是 Carbon 動手前必須知道的，否則會把「後端沒接好」誤判成「前端寫錯」。

1. **三個端點在真實 server 上可用**。`tests/e2e/analysis.spec.ts`（新增，後端提供）
   已對真實 private-TLS fixture 驗證 6 項全過。Carbon 可直接 `fetch` 真端點，
   不必先攔截 mock。
2. **API 呼叫必須帶 `Origin` 標頭**。`validate_request` 要求 origin 與
   `allowed_origin` 精確相等，缺少時回 **401**（不是 403、不是 CORS 錯誤）。
   瀏覽器內 `fetch` 會自動帶，`page.request.get` 不會——這是後端既有的一致性要求，
   不是缺陷。
3. **查詢字串帶憑證 → 401**。`/v1/*` 的 `_guarded_query` 會擋下
   `token`／`csrf`／`session`／`authorization`／`api_key` 等名稱，回 401。
   正常查詢參數（`instrument_id`、`timeframe`、`indicator`、`series_id`、`as_of`、`limit`）不受影響。

## 錯誤形狀（Carbon 的元件需要分辨）

| 狀態 | 觸發 | `detail` |
|---|---|---|
| 400 | 非法 timeframe／未知 indicator／非法 limit | `Invalid indicator request` |
| 401 | 無 session、origin 不符、查詢字串含憑證 | `Unauthorized` |
| 403 | session 無 `read_market` scope | `Market access denied` |
| 404 | 該標的沒有可算的 tape 序列／venue 未知；宏觀序列不存在 | `Indicator series not found`／`Macro series not found` |
| 503 | 平面本身不可用（上游故障） | `Indicator plane unavailable`／`Macro plane unavailable` |

**404 是「沒有序列」，503 是「壞了」**。兩者的前端文案必須不同：404 顯示
「此標的尚無可計算的歷史序列」，503 顯示「指標服務暫時不可用」。


## 改動範圍

可以新增或修改（相對於 `apps/desk-web/src/`）：

- `features/chart/**` — 指標疊圖
- `features/macro/**` — 宏觀面板（可新目錄）
- `features/feed/**` — 來源能力標示（可新目錄）
- `features/market/StockDetail.tsx` — 把三個新元件接進既有版面
- `shared/transport/analysis.ts` — 新增，負責打三個分析端點
- `shared/contracts/generated.ts` — **唯讀**

## 不可動

| 檔案 | 理由 |
|---|---|
| `shared/contracts/generated.ts` | 只能由 `npm run contracts` 產生。要新欄位請在 `HANDOVER.md` 的 Backlog 登記。 |
| `shared/contracts/market.schema.json` | 同上。 |
| `services/**` | 後端範圍。 |
| `schemas/gabfin-1.0.json` | 後端範圍。 |
| `shared/transport/market.ts`、`live.ts` | 行情通道的權威在前端既有實作，本單位不動它。 |

## 資料流

```
features/chart/IndicatorOverlay.tsx
  → shared/transport/analysis.ts 的 fetchIndicators()
  → GET /v1/indicators
  → generated.ts 的 IndicatorResponse

features/macro/MacroPanel.tsx
  → shared/transport/analysis.ts 的 fetchMacro()
  → GET /v1/macro
  → generated.ts 的 MacroResponse

features/feed/FeedCapabilityBadges.tsx
  → shared/transport/analysis.ts 的 fetchCapabilities()
  → GET /v1/capabilities
  → generated.ts 的 CapabilitiesResponse
```

`shared/transport/analysis.ts` 這一層的責任只有三件事：

1. `credentials: 'same-origin'`、`cache: 'no-store'`。
2. 把 401 轉成 `SessionRequired`（沿用 `shared/transport/live.ts` 已有的同名 class）。
3. 把 400／404／503 分成可區分的錯誤，讓元件能顯示不同的話。

**不要**在元件裡直接 `fetch`。分析端點的錯誤形狀有四種，元件要分辨它們。

## 合約

完整的欄位語意看 `docs/handover/ui-contract.md`。以下是要點。

### `/v1/indicators`

查詢參數：`instrument_id`（必填 UUID）、`timeframe`（必填，格式 `1min` / `1day`）、
`indicator`（選填，可重複，省略則回傳全部 24 個 canonical 指標）、`limit`（選填，預設 500）。

回應 `IndicatorResponse`：

- `series: IndicatorSeries[]` — 每個有值的指標一筆，含 `points`。
- `statuses: IndicatorStatus[]` — 沒有值的指標，含 `reason`、`required_bars`、`observed_bars`。
- `source_coverage` — 這條序列的口徑。前端**只讀顯示**，不可自行指定。

`IndicatorPoint.value` 是**字串**（十進位）。顯示就直接顯示，不要 `parseFloat` 再格式化。
`params` 也是字串鍵值（例如 `{ period: '14' }`）。

### `/v1/macro`

查詢參數：`series_id`（選填，省略則回傳全部內建序列）、`as_of`（選填，`YYYY-MM-DD`）。

回應 `MacroResponse`：`points: MacroPoint[]`，每個含 `series_id`、`observation_date`、
`release_date`、`value`（字串）、`units`、`frequency`。

**`series_id` 必須是內建序列 id**。後端只認 `services/gabfin/providers/fred/series.py`
裡的固定集合（`DGS2`、`DGS10`、`T10Y2Y`、`DFEDTARU`、`DFEDTARL`、`SOFR`、
`CPIAUCSL`、`PCEPILFE`、`UNRATE`、`PAYEMS`、`NFCI`、`BAMLH0A0HYM2` 等）。
傳未建 series id 回 **404**，不是空陣列。省略 `series_id` 則回傳全部內建序列。

**每個內建序列最多回一點**：後端對每個序列只取 `as_of` 當時最新且已發布的那一筆。
`release_date <= as_of` 的過濾在後端完成，前端不得自行放寬。

### `/v1/capabilities`

回應 `CapabilitiesResponse`：`sources: FeedCapabilities[]`，每個含
`source`、`venue_coverage`、`realtime`、`delay_minutes`、`tradable_for_entry`、
`depth_levels`、`fee_class`、`unavailable_reason`、`latency_label`、`checked_at`。

**`sources` 只包含實際量測過的來源**。沒被探測過的 feed 不會出現——
「不知道」與「已知沒問題」不可長得一樣。

**後端保證的約束**（可依賴，但前端仍應防守顯示）：
`realtime === false` 時 `tradable_for_entry` 必定為 `false`；`tradable_for_entry === true`
時 `realtime` 必定為 `true` 且 `delay_minutes` 為 `None`。這是後端 validator 強制的不變量。

## 驗收條件

### 指標疊圖

1. 圖表可切換至少 `SMA20`、`RSI14`、`MACD` 三組，切换後圖上有對應的線。
2. `statuses` 裡的指標**不畫線**，而是在圖表旁顯示原因（例：「RSI 需 14 根，現有 5 根」）。
3. 指標值的顯示與 K 線一致用**字串**原樣呈現。
4. 圖表上標明 `source_coverage`（例如 `sip`／`iex`），與 K 線來源口徑並排。
5. 端點回 404（該標的沒有 tape 序列）時，圖表**不空白也不造資料**，顯示
   「此標的尚無可計算的歷史序列」並保留既有 K 線。
6. 端點回 503 時顯示「指標服務暫時不可用」，不顯示上一次的值當成新的。

### 宏觀面板

7. 面板列出後端回傳的序列，每一列**同時顯示 `observation_date` 與 `release_date`**。
8. `as_of` 可由使用者指定。指定後只顯示該日期當時已發布的值。
9. `release_date` 晚於 `as_of` 的值**絕不可顯示**（後端已過濾，前端不得自行放寬）。
10. `value` 顯示為字串，單位（`units`）同時顯示。

### 來源能力標示

11. 每個來源一組標示，顯示 `venue_coverage`、`realtime`／`delay_minutes`、
    `fee_class`。
12. `tradable_for_entry === false` 時，**必須**顯示明確警示，措辭要讓人知道
    這個報價不能當入場依據。
13. `unavailable_reason !== null` 時顯示該原因，不可顯示為空白或「正常」。
14. `venue_coverage` 與圖表上的 `source_coverage` 口徑不同時，不可把兩者的
    量能指標（OBV／MFI／volume SMA）放在一起比較。

### 共同

15. 示範模式（demo）下，上述三個元件顯示「示範資料工作台 · 未接入」之類的
    明確狀態，**不可**顯示示範數字冒充真實指標或宏觀值。
16. 分析請求不需要 CSRF token（純讀取）。但仍需 `Origin` 標頭與 session cookie。

## 測試

- 新增 `tests/e2e/` 下的 Playwright 檔（可以新增檔案，**不可**改既有斷言）。
- 至少覆蓋：指標疊圖切換、`statuses` 顯示原因、宏觀列同時顯示兩個日期、
  `tradable_for_entry === false` 的警示出現、能力標示顯示 `unavailable_reason`。
- 測試需要攔截 `/v1/*` 回應。既有 e2e 已有攔截行情端的先例，沿用同一手法。
- 跑 `npm run typecheck` 必須通過。

**後端已提供的 e2e 覆蓋**（Carbon 不可修改，可直接依賴）：
`tests/e2e/analysis.spec.ts` 對三個端點的 6 項斷言已全過。若 Carbon 的 UI 測試
需要不同的 fixture 形狀，在自己的新檔案裡建立，不要改那一支。

## 已知的後端限制（Carbon 必須據此設計 UI）

1. **`/v1/indicators` 目前在生產上是 404，不是空序列**。後端已把 tape 接進指標平面，
   但 tape 內必須先有對應 symbol／timeframe 的已寫入序列。空序列回 404
   `Indicator series not found`。
2. **指標只支援 `source_coverage` 為 `sip`／`iex`／`futu_nasdaq_totalview`／`futu_arca` 的序列**。
   未知 venue 拒絕計算（404）。前端顯示 `source_coverage` 時不必自己判斷合法性。
3. **`IndicatorResponse.series` 可能是空陣列，同時 `statuses` 非空**。這是
   「歷史不足」的正常結果，不是錯誤。前端要同時處理兩者。
4. **時間框架字串格式**：`1min`、`5min`、`1hour`、`1day`（`count` + 單位，無空格）。
   後端解析失敗回 400。

## 完成後

1. 跑 `npm run typecheck`，結果貼進 `HANDOVER.md` 的「UI 變更清單」。
2. 在 `HANDOVER.md` 把 `stage` 改成 `ui-done`。
3. 在「UI 變更清單」列出每個改動檔案與一句摘要。
4. 若發現後端缺欄位或缺端點，**不要自己加**，在「Backlog」登記一條。
