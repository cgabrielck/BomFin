# GabFin S02/02b Market and Event Contracts Implementation Brief

> Execute the next slice of confirmed Task 2 with `executing-plans` and TDD. Existing local checkout, single agent, no new architecture interview or process approval.

**Goal:** 建立可驗證、可 roundtrip 的商品／市場資料與 typed MarketEvent envelopes，供後續行情服務使用。

**Architecture:** 新模型只依賴 02a primitives；沒有 provider、cache、clock loop、DB 或交易執行。MarketEvent 為以 kind 區分的 quote/trade/bar union，payload 不是任意 dict。

**Tech Stack:** 現有 Python 3.12／Pydantic 2.14.4／pytest，沒有新增依賴。

**Spec:** [main plan §2 / Task 2](2026-11-25-gabfin-upgrade-plan.md)；[design §7.2](../specs/2026-11-25-gabfin-system-design.md)。

## Global Constraints

- UUID instrument/event IDs；價格／數量用 Decimal，JSON 字串；所有 instant 使用 shared UTC codec。
- None 表示缺資料，不能用零或舊價格補齊；沒有即時權益或交易資格的默認判定。
- 不固定日線／月份的秒數，不因資料缺口合成 bar；session/calendar 邏輯後續實作。
- 保留現有 source、lockfile 及 baseline；只延伸 common aliases，不修改 legacy／02a intent。
- 不接 provider、DB、API、broker；不啟動交易或 push。不是整個 Task 2 完成。

## Files and Interfaces

- Modify `services/gabfin/contracts/common.py`：新增 `PositiveDecimal`、`NonNegativeDecimal`、`OpaqueKey`。Opaque keys 不偷偷 trim 或改大小寫；拒絕空白邊界／控制字元，避免 identity collisions。
- Create `services/gabfin/contracts/market.py`：
  - `Instrument`：schema_version、instrument_id、asset_class(equity/option)、vendor_symbols(nonempty mapping)、currency、tick_size、lot_size、option terms。
  - `OptionTerms`：underlying_id UUID、expiry date、right(call/put)、strike、multiplier。Option 必須完整；equity 不帶 option terms；multiplier 無 100 預設，underlying 不能引用自己。
  - `QuotePoint`：price(nonnegative)、event_at(nullable)、received_at、available_at、age_ms(nullable)。
  - `QuoteEntitlements`：status(unknown/realtime/delayed/indicative/denied)、checked_at(nullable)、capability_snapshot_id(nullable)。已知 status 要有 checked_at；不代表真的已驗證權益。
  - `QuoteSnapshot`：schema_version、instrument_id、as_of、feed、session、bid/ask/last(each nullable QuotePoint)、quality flags、entitlements。
    每個 present point 的 age 要等於相對 as_of 的整數毫秒；未知 event_at 對應 age=None/incomplete，future event_at 對應 age=None/clock_skew；point.available_at 不可晚於 snapshot.as_of。
    全缺報價要標 unavailable；crossed bid/ask 要標 crossed，保留原觀察而非篡改價格；denied entitlement 要標 permission_denied。
  - `TradeTick`：schema_version、instrument_id、price/quantity(positive)、trade_id(nullable)，是行情成交，不是 broker fill。
  - `Timeframe`：count、unit(second/minute/hour/trading_day/week/month/year)，不內建固定時長換算。
  - `Bar`：schema_version、instrument_id、source、timeframe、session、start/end、OHLC、volume(nullable)、status(forming/final/corrected)、revision、corporate_action_policy、event_at/received_at/available_at。
    OHLC 保持 low<=open/close<=high；volume 非負或 None；start<end；corrected revision>0；final/corrected end<=available_at。
- Create `services/gabfin/contracts/events.py`：`QuoteMarketEvent`、`TradeMarketEvent`、`BarMarketEvent` 與 discriminator union `MarketEvent`。
  共同 envelope：schema_version、event_id、instrument_id、event_at/received_at/available_at、source、source_seq(nullable string)、dedup_key、kind、typed payload。
  instrument ID 必須與 payload 相同；bar envelope 三個時間需與 Bar 相同；quote capture as_of<=envelope.available_at。
  保留 late/out-of-order 及 source clock skew，不要求 event_at<=received_at；本地 available_at>=received_at。
- Create `tests/gabfin/conftest.py`：純資料 fixtures，不 import 新模型以免阻斷 RED collection。
- Create `tests/gabfin/test_market_contracts.py`、`test_market_events.py`：真實 validation／roundtrip／schema tests。

## Review Focus

1. 期權被當股票 ticker：缺 option terms、錯 asset class、自我 underlying、錯 expiry 皆拒絕；正確非標準 multiplier 保留。
2. None 被補零或假 age：各 point 時間／age 獨立；zero bid/zero volume 與缺值保持不同；未知／future 時間要明示品質問題。
3. 復原歷史資料被時間排序錯誤拒絕：只檢查本地 capture 因果；允許來源晚到／亂序／clock skew；forming end 可以在未來。
4. 事件 metadata 與 payload 不一致：kind-discriminated payload、instrument、bar times 與非空 dedup key 必須匹配；source_seq 大整數保留字串。
5. Decimal／整數被寬鬆 coercion：價格／數量拒絕 float／bool；revision／age／timeframe count 使用 strict、JS-safe integer。沒有 source_seq 就仍必須提供 dedup key。

## Steps

- [x] Snapshot source／lockfile；確認兩個新市場 modules 尚未存在，保存全部原始 02a 證據。
- [x] 寫 Instrument／quote／Bar 測試並跑 RED；實作 shared aliases 與 market models，跑 GREEN。
- [x] 寫 MarketEvent union／一致性／去重欄位測試並跑 RED；實作 typed envelopes，跑 GREEN。
- [x] 跑全部 gabfin 契約測試、schema validation、獨立 import／wheel 檢查；自我覆核五種失效情境，必要修正先做失敗案例。
- [x] 跑完整 sanitized pytest；分類 skip／warning，保存新產生的 legacy journal，不覆蓋既有證據。
- [x] 核對原有檔案、允許修改的 common.py、scope、lockfile 及 diff；只 commit 本單位 paths，不 push。
- [x] 更新報告、memory／checkpoint；下一步是其餘 Task 2 領域契約，不宣稱行情服務或交易已可用。

## Builder Calls and Limits

- 公開 MarketEvent 是 TypeAdapter 解析的 discriminated union；具名 envelope classes 可直接建構。它承載去重 key，不實作去重 store 或 key 產生算法。
- QuoteMarketEvent 承載完整觀察快照，不是 partial delta；原始 callback 的增量合併須在發布前完成，不能把 None 當作 unchanged。kind/source/payload 一致性避免把其他 feed 重新標成目標 feed。
- MarketSession 是觀察時段分類，不是 PolicyVersion 的可交易時段白名單；overnight/closed/unknown 標籤不啟用任何交易時段。
- Snapshot age 由 supplied as_of 決定，不使用現在時鐘；沒有 5 秒或其他 freshness 啟用門檻。
- corporate_action_policy 是版本政策標籤，不在本單位實作股票分拆／股息調整。Option metadata 不證明供應商 listing／deliverable／資料權益已核對。
- 模型檢查形狀與一致性，不證明來源權益、身份或交易授權；服務層仍須驗證 actual capabilities／principal。
- Instrument vendor_symbols 是 mapping；frozen model 不等於深層不可變 registry，後續 catalog 必須用受控更新／快照，不能將 instance 本身當 identity key。
- Self-review: the four main table contracts are covered here; full support models, aggregate schema and migrations remain later units.

完成結果由 [02b report](../../audit/s02-02b-market-events-2026-11-25.md) 擁有；本地提交及下一單位見 checkpoint。
