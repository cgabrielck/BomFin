# S03 審查修正及驗證紀錄

Base `3073cf3`；最終樹 `63f71a8`；本機提交 `1802198`。
Fresh/read-only Standards／Spec reviewers 的範圍及結果由 reviews.json 擁有。

- [x] Freshness 保留三參數呼叫；缺 health/calendar 拒絕，現時 session／來源時鐘重新核對。
  red-review-freshness → green-review-freshness：21 passed。
- [x] ManagedFeedAdapter／FeedCleanup 明確化；capability factory 失敗可重試，供應商負責回條解析。
  red-managed-contract → green-managed-contract：49 passed。
- [x] Trade ID／dedup key 雙索引，coordinator 去重紀錄淘汰後仍不能重計 volume。
  red-review-trade-alias：2 failed → green-review-trade-alias：24 passed。
- [x] History coverage 核對 instrument/channel/timeframe/window/count/pagination/empty evidence。
  red-review-history-proof → green-review-history-proof：36 passed。
- [x] Provider 明確宣告 contiguous 序號，opaque 不猜連號；有界 missing-frontier 與語意紀錄。
  red-review-sequence → green-review-sequence：35 passed。
- [x] Quote resync 僅用 post-cutover 已接受的相同事實；保留 disconnect window，舊 worker 不縮窗。
  red-review-quote-proof → green-review-quote-proof：12 passed。
- [x] 心跳失效關閉舊 feed 才 retry；清空本輪證據。
  red-review-heartbeat-retry（逾時）→ green-review-heartbeat-retry：7 passed。
- [x] Host 清理失敗關 listener 並喚醒 --serve；重試耗盡會傳遞錯誤。
  red-review-host-failure → green-review-host-failure：9 passed；後續 exhaustion 見最終回歸。
- [x] MarketCursor value object、共用數字 parser、移除不用的 wire error。
  green-cursor-refactor：34 passed。
- [x] 補缺批次拒絕 duplicate／時鐘偏移；sequence reset／舊序號不明／衝突 latch 到新 epoch。
  red-review-followup 與 red-review-duplicate-history → green-review-followup：31 passed。
- [x] 清理回條涵蓋所有 requested keys，矛盾 provider error 不可聲稱釋放。
  red-review-release-host 的5失敗已由後續測試及最終完整回歸驗證修正。
- [x] Resume 綁定 session/view 與已發出游標；slow/error 後須 snapshot。
  red-review-resume-scope：2 failed → green-review-resume-final：17 passed。
- [x] 最終完整回歸、wheel／乾淨安裝、實際 SDK→獨立 consumer、保留檢查、本機提交。
  最終證據以 final-verification.json／full-reviewed.log 為準：2108 passed、4 skipped。

## 非預期失敗與修復

- red-auth-read-close.log 首次測試卡住，經受控停止，沒有視為通過。
  Python3.12 listener.wait_closed 在 client 尚未關閉時等待；改成先關 listener、
  cancel/await clients，再 wait_closed，且等待在途 SQLite auth thread 結束。
  以有界測試重現 red-active-listener-close：1 failed，修正後16相關 passed。
- calendar-failure.log：跨年日曆 constructor 的 first_session 邊界問題；查詢 padded
  constructor range，輸出仍保留要求 coverage。最終 wheel 再匯出並核對假日／DST。
- red-review-followup 的 duplicate 案首次 fixture 落在 gap 之外，並非該問題的有效 RED；
  修正 fixture 後 red-review-duplicate-history 確認 duplicate 能錯誤清 gap，然後修正程式。
- green-review-release-host：55 passed／1 failed；舊 fake heartbeat 比 factory-failure
  disconnect 更早，正確被拒。Fixture 改成市場現時時鐘，保留實際 retry 行為驗證。
- green-review-resume-release：72 passed／1 failed；無效但尚未建立的 resume 請求
  清掉有效 checkpoint。限制為已建立 connection 才 invalidation；stream17再次通過。
- full-before-review／full-final 是較早結果，不代替 full-reviewed 的最終結果。

G2 realtime／BBO／PRE/POST 與真實 trade/bar recovery 證據仍 open；
UI render tracing 留給 S04。沒有交易、購買、部署或控制 OpenD。
