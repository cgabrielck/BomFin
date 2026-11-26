# 本機行情程序與恢復

此入口只開 quote context，並以獨立 SDK Python 接收一股完整 quote observation。
它不開交易 context。`config/market-instrument-example.json` 是診斷 fixture；
正式 catalog 的 tick/lot/currency 要由 symbol ingestion 核對。

## 執行

在 checkout 根目錄，以已安裝 GabFin 的 Python 執行：

```powershell
python -m gabfin.market.host --sdk-python <isolated-sdk-python> --instrument config/market-instrument-example.json --session-db <local-session-database> --owner <owner-uuid> --seconds 12
```

`--seconds` 限 120 秒內；已有訂閱的清理可能額外等待 SDK 最短持有期。
需常駐時明確改用 `--serve`，前景運行並以 Ctrl+C 停止。程式不自行安裝服務。
開始前獨立探測 quote login/quota；只輸出 listener 位址，沒有登入碼或 token。
心跳超時會先關閉並核實舊 context 的釋放，再重試。清理失敗就停止，
關閉 listener 並喚醒前景主機，不會留下看似仍在服務的連線入口。

內部 stream 僅允許 loopback。Consumer 必須使用同 owner 的 SessionStore 所發出、
具有 `read_market` 的 service session；根 UUID 不是富途帳號。Token 經私有管道
交給 API consumer，不放命令列、URL 或診斷輸出。S04 的 API/瀏覽器橋接再接到這層。

`InternalMarketClient.connect` 先讀 typed snapshot；正常增量含 epoch、sequence、
event 原始時間及 processed_at。可攜帶 epoch/cursor 恢復；收到 snapshot_required
就重新連線取 snapshot，不沿用失效游標。會檢查 session 到期、撤銷及能力。
沒有每客戶端無限 queue；寫出逾時或 lag 超出 replay retention 會關閉連線。
Resume 只接受此 server 已向相同 session／instrument 集合發出的游標範圍；
慢讀者、連線錯誤或保留紀錄淘汰後必須先取完整 snapshot。Resume 記錄有固定上限。

## 時間與完整性

- SDK 每 10 秒查 quote-server login 作 heartbeat；它與價格事件時間獨立。
  主程序不靠自己的 timer 偽造 provider heartbeat。
- 新連線完整 quote snapshot 可恢復可合併的 quote 狀態；同價重送仍保留原始價格時間。
  quote_snapshot recovery 不可解除 trade/bar 歷史缺口。
- `FeedSupervisor` 可接外部 backfill API；其 RecoveryBatch 必須覆蓋當前 gap/cutover，
  按 instrument/channel/timeframe 提供 RecoveryCoverage，核對範圍、筆數、完整性與分頁結束。
  空頁需提供 provider_verified_empty 或 market_closed 理由；單一 complete 旗標不足。
  這是受信 history adapter 的證明介面，consumer 沒有寫入或解除 gap 的能力。
  不完整就保留 gap；不會把重新連上當成補缺成功。
- 來源序號預設 opaque；只有 provider 明確聲明 contiguous 才偵測連號缺口。
  缺號未補齊時不可解除 gap；序號重置或規則改變需建立新 epoch。
  無法核對的舊序號或保留容量溢出亦保持禁止恢復，待主機建立新 epoch。
- `BarBuilder` 僅消費 TradeMarketEvent；固定秒／分鐘、explicit calendar、可配置保留上限。
  累積的是已觀察成交。Final 代表區間結束；coverage 還要看 snapshot.gap。
  相同來源時間但價不同且沒有可比較序號會拒絕，不猜交易順序。
- 原生 bar 與 trade-derived bar 不能混用同一 builder authority。
  Quote 不會產生虛構成交量，委託事件不進行情通道。
- `entry_eligible` 每次按 now 重算價格年齡，需要明確、上游已驗證的 freshness policy。
  也需 health 與覆蓋 now 的已核對 calendar；保留原有三參數呼叫，但缺少證據會回傳拒絕。
  未知權益／session、缺 BBO、gap、stale 等會拒絕；回傳只涵蓋行情條件，不是風控批准。

## 日曆

日曆依賴為可選 extra，放獨立環境生成後再供主程序使用：

```powershell
python -m pip install 'gabfin[calendar]'
python -m gabfin.providers.exchange_calendar --start 2026-01-01 --end 2026-12-31 --output <calendar-json>
```

目前驗證 `exchange-calendars==4.13.3` 的 XNYS regular session。
快照含 coverage／來源／版本；覆蓋內沒有 session 是休市，覆蓋外是未知。
不從工作日猜假期，不以 XNYS reference calendar 代替個別 instrument 的 listing exchange，
也不據此宣稱 PRE/POST 權益。延長時段需另有已核對的 calendar windows。

## 目前界線

一股 Futu host 的即時 producer 是 quote-only；trade/bar 引擎及 history recovery seam
可接其他具完整證據的 FeedAdapter。Native quote 仍缺 BBO／已證實的 session/latency，
capabilities 保留 live_manifest_unverified。S03 的 smoke 與 G2 外部權益由外層 audit 記錄。
前端渲染 tracing 留給 S04，本層提供 source→receive→state→consumer 時間接點。
