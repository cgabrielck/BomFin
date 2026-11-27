# 2026-11-27 — 04e trace 缺陷診斷與修正

## 問題

04e 的 `acceptance.spec.ts` 中「quote trace correlates receive, state, consumer and render」
**間歇性失敗**：完整套件 31 passed，但單獨重跑時出現
`Expected: 1 / Received: 2`（`__traces.length` 多出一筆）。

初版證據見 [red-trace.log](red-trace.log)（原始 RED：trace 完全未送出）。

## 診斷過程

新增臨時 `tests/e2e/diagnose.spec.ts`（已於修正後刪除，不在交付範圍）觀察：

1. `BEFORE_CLEAR=["0dda1ff7…","0dda1ff7…"]` — **同一個 event_id 出現兩次**。
2. `IDLE_AFTER_CLEAR=["7028f876…"]` — 沒有送任何報價，clear 之後仍自行多出一筆。
3. 加上時序欄位後：
   `AFTER_WAIT` 顯示兩筆 `eventId` 相同但 `receivedMono` 不同（688 與 792），
   證明是**兩個不同的 trace 物件**，不是同一物件被重複 commit。

## 根因（產品程式碼缺陷，非測試問題）

1. `beginQuoteTrace` 對 snapshot 一律取 `quotes[0]`，**沒有核對訂閱的 channel／instrument**。
   `ChartPanel` 以 `channel:'bar'` 訂閱，卻也會 trace 到 quote 事件。
2. HTTP snapshot 與 WebSocket snapshot 描述**同一個 quote event**（相同 `event_id`），
   卻各自產生一個 trace 物件，因此**一個事件被記錄成兩次 render**。
3. 由於讀取端在 session 模式切換時會重新 mount，依 component 範圍去重不足以涵蓋。

## 修正（改產品程式碼，不放寬測試）

- `market-trace.ts`：`quoteFor` 以訂閱 keys 過濾，`channel==='quote'` 且 instrument 相符才 trace。
- `market-trace.ts`：`committed` 改為**頁面層級** `Set<string>`。
  quote `event_id` 是市場事件識別，一個事件因此只產生一筆 trace。
- `live.ts`：`fetchSnapshot`／`subscribeMarket` 把訂閱 keys 傳入 `beginQuoteTrace`／`rememberSnapshot`。
- `StockDetail.tsx`：`commitQuoteTrace` 改為單一參數（頁面層級去重）。

## 驗證

- 修正前 `BEFORE_CLEAR` 有 2 筆相同 id；修正後只有 1 筆。
- 修正前 `IDLE_AFTER_CLEAR` 有 1 筆殘留；修正後為 `[]`。
- `acceptance.spec.ts` 連續 **5 次重跑全部 3 passed**（21.9／22.0／21.9／22.6／22.2 秒）。
- 完整套件 **31 passed**（2.8 分鐘），無 flaky。
- `pytest tests/gabfin` → **925 passed**；`npm.cmd run typecheck` exit 0。

## 注意

TLS fixture 以 `--dist apps/desk-web/dist` 提供 **production build**。
改動前端後必須先 `npm.cmd run build`，否則測試跑的是舊 bundle。
本次診斷初期因此一度誤判修正無效。
