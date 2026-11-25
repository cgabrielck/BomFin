# S02 / 02b — Market and typed event contracts

本單位已完成。建立新架構的市場資料契約及驗證；行情服務、供應商連線、DB、API、broker 與交易執行仍未接入。

## Revision and scope

- Checkout: `C:/Users/001/Desktop/GabFin-ai-trade/.worktrees/gabfin-s01`。
- Branch: `codex/s01-source-baseline`；base `24ae093b7b8cbf7a4263faaf1a9e0a616f8d5c35`。
- Local commit: `5891b2ed1ef8d604535c2ce564eaba7f6f7949bc`，未 push。
- 修改 `services/gabfin/contracts/common.py`，新增 `market.py`、`events.py`、`tests/gabfin/conftest.py`、`test_market_contracts.py`、`test_market_events.py`。
- common.py 新增正值／非負 exact Decimal 及 opaque key helpers；13 個既有 declarations 的 AST 保持一致，其餘 482 個原有 tracked 檔案 SHA256 相同。
- 既有 untracked `web/package-lock.json`、baseline／02a 證據保持原樣；沒有新增依賴或更改舊 backend。

## Resulting interfaces

- `Instrument` 區分 equity／option，以 UUID 識別；期權完整提供 underlying、date-only expiry、right、strike、multiplier。沒有默認 100 multiplier；不接受 self-underlying。
- `QuoteSnapshot` 的 bid／ask／last 可獨立為 None；各自保留 event／received／available 時間及相對 supplied as_of 的 age。零報價與缺值分開，不補舊價。
- 缺 event time、source clock skew、crossed quote 須明示品質標籤；只檢查本地 capture 因果，不使用現在時鐘或設定 freshness 門檻。Locked quote 可保留。
- `Bar` 驗證 OHLC、interval、capture 時序及 revision；forming 可尚未完結，final／corrected 不可在 end 前可用。缺 volume 與零 volume 分開保存。
- `Timeframe` 保留 count／unit，不把 trading day／month 換算成固定秒數。`corporate_action_policy` 是政策標籤，沒有拆股／股息調整計算。
- `MarketEvent` 為 quote／trade／bar discriminated union；payload 有指定類型，驗證 instrument／source／bar capture timestamps 一致。Availability 不早於本地 receipt，但允許 late／out-of-order／source clock skew。
- source_seq 為可空字串，避免大整數經 JSON 失真；dedup_key 不可空。Opaque keys 不隱式 trim／改大小寫，拒絕邊界空白與 ASCII 控制字元。
- QuoteMarketEvent 是完整快照，原始增量須先合併；None 不能解讀為 unchanged。公開 union 用 `TypeAdapter(MarketEvent)` 解析。

## Verification actually run

| Check | Actual result | Evidence |
|---|---|---|
| Market TDD | implementation 前 77 fail；初次 GREEN 76 pass／1 fail，修正 fixture alias 後 77 pass | [RED](artifacts/s02-02b/market-red-final.log)、[GREEN](artifacts/s02-02b/market-final.log) |
| Event TDD | 33 個 missing-module failures，加 2 個 feed-relabel failures；35 pass | [RED](artifacts/s02-02b/events-red.log)、[source RED](artifacts/s02-02b/events-source-red.log)、[GREEN](artifacts/s02-02b/events-green.log) |
| 最終 gabfin contracts | 204 passed，其中 118 個是 02b 新增案例 | [log](artifacts/s02-02b/contracts-final.log) |
| 最終完整 sanitized pytest | 1412 passed／4 skipped／1 warning，exit 0，65.59s | [log](artifacts/s02-02b/full-final.log)、[JUnit](artifacts/s02-02b/full-final.xml) |
| Packaging | wheel build 成功，套件檔案與 source bytes 相同 | [build](artifacts/s02-02b/wheel-build.log)、[verification](artifacts/s02-02b/verification.json) |
| Schema／isolated smoke | 4 個 serialization schemas 通過 Draft 2020-12 schema check；一個 event wire schema validation 與 roundtrip 通過；未載入 backend | [smoke](artifacts/s02-02b/isolated-smoke.log) |
| Dependency／scope | pip check: No broken requirements found；diff check、source hashes、舊證據／lockfile 保留核對通過 | [verification](artifacts/s02-02b/verification.json) |

- 4 個 skip 均為原有 optional Postgres cases，缺 `psycopg`；警告仍是 `backend/research/comps.py:26` 的 Pandas4Warning，沒有當作已修復。
- 初次 GREEN 的失敗來自 option fixture 修改共用 instrument dict；改成 deepcopy 隔離 fixture，未放寬 assertion。自我覆核另加 6 個案例，沒有再改 production logic。
- 完整 suite 產生 legacy mock journal；確認開工前不存在後，移到本單位 [artifact](artifacts/s02-02b/legacy-test-generated-journal.json)，未覆蓋舊檔。
- Wheel SHA256: `09da946f38ec4c5aac9ad8366534ea525740219bcea3c2e6005d150d9044a0e9`。
- 按使用者要求採單 Agent；覆核為作者自我覆核，沒有獨立 reviewer。沒有啟動 app／trading worker、實際供應商或 paper 驗收。

## Engineering rulings and costs

1. 只細化已批准 Task 2 的本切片，不重開架構訪談或等待 legacy UI／Postgres 修復。代價：舊入口與 optional PG coverage 的限制仍存在，不能以本測試結果宣稱已修復。
2. Source sequence／identity key 使用 opaque string；數字 counters 使用 strict JS-safe integer。代價：adapter 要保留原字串；超出 counter 範圍須明確轉換契約，不能靜默截斷。這些不是金融風險設定。
3. 保留 crossed／incomplete／clock-skew 觀察並要求標籤，只驗證 capture 因果。代價：後續消費者必須讀品質及執行 policy，契約本身不阻擋所有不適合交易的資料。

## Boundaries and next unit

- Entitlement／session metadata 不證明實際權益或交易授權；MarketSession 不是可交易時段白名單。Option metadata 不證明 listing／deliverable 已核對。
- Frozen model 不代表 nested dict 深層不可變；後續 catalog 須受控更新／快照，不能把 Instrument instance 當 registry identity key。
- 沒有去重 store／key 演算法、calendar、freshness／adjustment engine 或真實權益核對。Schema 形狀驗證不替代 Python 跨欄位驗證及服務層授權。
- 下一單位為 S02／02c：EvidenceItem／ResearchRequest／ResearchReport 等研究契約。其他 order／policy／support models、aggregate frontend schema artifact、SQLite migrations 及 Task 3 授權仍待完成；整個 Task 2 尚未完成。
- [02b brief](../superpowers/plans/2026-11-25-gabfin-s02-02b-market-events.md)、[execution ledger](artifacts/s02-02b/progress.md)、[checkpoint](../memory/execution.md)。
