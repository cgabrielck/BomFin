# 前端可依賴的 API 契約

前端只讀這份檔與 `apps/desk-web/src/shared/contracts/generated.ts`。Python 實作不在前端範圍。

所有端點都走既有的認證與能力授權：

- 瀏覽器必須持有 `gabfin_session` cookie（HttpOnly、Secure、SameSite=Strict）。
- 請求必須帶 `Origin` 標頭，且與 `allowed_origin` 完全相同。
- 端點只允許 HTTPS。HTTP 一律 401。
- 需要寫入的請求另需 `x-csrf-token` 標頭，值取自 `__Host-gabfin_csrf` cookie。

## 認證失敗的形狀

```json
{ "detail": "Unauthorized" }
```

HTTP 401。HTTP 403 表示能力不足（`"Market access denied"`）。

## 既有端點

| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/pair` | 以配對碼換 session cookie |
| GET | `/session` | 查詢目前身分 |
| POST | `/logout` | 撤銷 session |
| POST | `/market/snapshot` | 一次取得行情快照 |
| WS | `/market/stream` | 行情串流（snapshot 影格 + update 影格） |

`/market/snapshot` 與 `/market/stream` 接受 `MarketRequest`／`MarketStreamRequest`：

```json
{
  "version": 1,
  "keys": [
    { "instrument_id": "<uuid>", "channel": "quote", "timeframe": null },
    { "instrument_id": "<uuid>", "channel": "bar", "timeframe": { "count": 1, "unit": "minute" } }
  ]
}
```

上限 64 個 key。`channel` 只有 `quote`、`trade`、`bar` 三種；只有 `bar` 需要 `timeframe`。

回應是 `MarketSnapshot`：

```json
{
  "schema_version": "1.0",
  "epoch": "<string>",
  "cursor": 0,
  "as_of": "<iso8601>",
  "health": {
    "schema_version": "1.0",
    "source": "futu",
    "connected": true,
    "connection_started_at": "<iso8601>",
    "gap_pending": false,
    "heartbeat_at": "<iso8601>"
  },
  "gap": null,
  "quotes": [ /* QuoteMarketEvent[] */ ],
  "bars": [ /* BarMarketEvent[] */ ]
}
```

## 指標端點（WU-9，本輪新增）

`GET /v1/indicators`

查詢參數：

| 參數 | 必填 | 說明 |
|---|---|---|
| `instrument_id` | 是 | UUID |
| `timeframe` | 是 | `1min` / `1day` 形式，例 `1min`、`5min`、`1day` |
| `indicator` | 否 | 指標名；省略則回傳全部 canonical 指標。可重複 |
| `limit` | 否 | 回傳點數上限，預設 500，上限 100000 |

`source_coverage` 不是查詢參數。它由 tape 內該序列的口徑決定，會出現在回應的 `source_coverage` 欄位。前端不可自行指定口徑。

回應 `IndicatorResponse`：

```json
{
  "schema_version": "1.0",
  "instrument_id": "<uuid>",
  "timeframe": { "count": 1, "unit": "minute" },
  "source_coverage": "sip",
  "computed_by": "local",
  "series": [
    {
      "schema_version": "1.0",
      "instrument_id": "<uuid>",
      "indicator": "rsi",
      "params": { "period": "14" },
      "timeframe": { "count": 1, "unit": "minute" },
      "source_coverage": "sip",
      "points": [
        {
          "schema_version": "1.0",
          "instrument_id": "<uuid>",
          "indicator": "rsi",
          "params": { "period": "14" },
          "timeframe": { "count": 1, "unit": "minute" },
          "value": "56.12",
          "event_at": "<iso8601>",
          "computed_at": "<iso8601>",
          "source_coverage": "sip",
          "computed_by": "local",
          "realtime": false
        }
      ]
    }
  ]
}
```

### 指標端點的失敗形狀

| 狀況 | HTTP | body |
|---|---|---|
| 認證失敗 | 401 | `{"detail":"Unauthorized"}` |
| 能力不足 | 403 | `{"detail":"Market access denied"}` |
| 參數不合法 | 400 | `{"detail":"Invalid indicator request"}` |
| 該標的沒有 tape 序列 | 404 | `{"detail":"Indicator series not found"}` |
| 指標還沒有足夠 bar | 200 | `series` 為空，且 `statuses` 說明原因 |
| 指標平面暫時無法回答 | 503 | `{"detail":"Indicator plane unavailable"}` |

`value` 是**字串**（十進位），不是數字。要顯示就直接顯示，不要 parse 成 float 再格式化。

### `statuses` 欄位

`IndicatorResponse` 另含 `statuses: IndicatorStatus[]`，說明每個請求的指標目前為何沒有值：

```json
{
  "indicator": "rsi",
  "params": { "period": "14" },
  "ready": false,
  "reason": "insufficient_history",
  "required_bars": 14,
  "observed_bars": 5
}
```

## 宏觀端點（WU-9，本輪新增）

`GET /v1/macro`

查詢參數：

| 參數 | 必填 | 說明 |
|---|---|---|
| `series_id` | 否 | 省略則回傳全部內建序列的最新值 |
| `as_of` | 否 | ISO 日期（`YYYY-MM-DD`）。省略則用最新。指定時只回傳該日期**當時已發布**的觀測值 |

回應 `MacroResponse`：

```json
{
  "schema_version": "1.0",
  "observed_at": "<iso8601>",
  "as_of": "2026-11-27",
  "points": [
    {
      "schema_version": "1.0",
      "series_id": "DGS10",
      "observation_date": "2026-11-20",
      "release_date": "2026-11-20",
      "value": "4.15",
      "units": "Percent",
      "frequency": "daily",
      "vintage": null
    }
  ]
}
```

### 宏觀端點的失敗形狀

| 狀況 | HTTP | body |
|---|---|---|
| 認證失敗 | 401 | `{"detail":"Unauthorized"}` |
| 能力不足 | 403 | `{"detail":"Market access denied"}` |
| 參數不合法 | 400 | `{"detail":"Invalid macro request"}` |
| 沒有 FRED key | 503 | `{"detail":"Macro plane unavailable"}` |
| 該序列不存在 | 404 | `{"detail":"Macro series not found"}` |

### 宏觀顯示規則（強制）

`release_date` 與 `observation_date` **必須同時顯示**。只顯示數字而不顯示發布日期，等於顯示一個沒有時效資訊的舊數字，比不顯示更糟。

## 能力端點（WU-9，本輪新增）

`GET /v1/capabilities`

回應 `CapabilitiesResponse`：

```json
{
  "schema_version": "1.0",
  "checked_at": "<iso8601>",
  "sources": [
    {
      "schema_version": "1.0",
      "source": "alpaca",
      "asset_classes": ["equity"],
      "sessions": ["pre_market", "regular", "post_market"],
      "latency_label": "delayed",
      "max_subscriptions": null,
      "history_limits": [],
      "checked_at": "<iso8601>",
      "permission_errors": [],
      "sequence_rules": [],
      "venue_coverage": "sip",
      "realtime": false,
      "delay_minutes": 15,
      "tradable_for_entry": false,
      "depth_levels": null,
      "fee_class": "none",
      "unavailable_reason": null
    }
  ]
}
```

### 新增欄位的語意

| 欄位 | 語意 |
|---|---|
| `venue_coverage` | 該來源覆蓋的場所。`sip` = 全美 SIP；`iex` = 單一交易所 IEX；`futu_nasdaq_totalview` = 富途 Nasdaq TotalView。**不可與其他口徑的量能指標混用。** |
| `realtime` | 是否為即時報價。`false` 表示有延遲。 |
| `delay_minutes` | 已實測的延遲分鐘數；未知為 `null`。 |
| `tradable_for_entry` | 是否可用作入場依據。indicative 或延遲報價一律 `false`。 |
| `depth_levels` | 該來源可提供的深度檔數；`null` = 未知或未提供。 |
| `fee_class` | 費用級別：`none` / `exchange` / `per_quote` / `subscription`。 |
| `unavailable_reason` | 不可用時的原因；可用時為 `null`。 |

### 能力顯示規則（強制）

- `tradable_for_entry === false` 時，UI 必須顯示明確警示，且該來源的任何報價不得被描述為「可入場」。
- `unavailable_reason !== null` 時，UI 顯示原因，不可顯示為空白或假資料。
- `venue_coverage` 與 `source_coverage` 必須一起顯示。兩者口徑不同時不可混算。
