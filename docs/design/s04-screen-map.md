# 04a 畫面與操作對照

- [互動預覽](s04-desk-wireframe.html)：自包含 HTML／CSS／JS，無外部字型、套件或服務。
- [分段計劃](../superpowers/plans/2026-11-26-gabfin-frontend-delivery-plan.md) 的 04a 已交付預覽，
  詳細視覺方向待使用者確認；未開始 04b React app。
- 混合設計：深青導航、淺色卡片及清晰留白；股票詳情採候選／圖表／研究三區。
  沒有複用上游程式碼、素材或商標；圖形為本地 SVG 示意。

| 畫面／元件 | 可試操作與需求對應 |
|---|---|
| 桌面首頁 | 先顯示持倉變化，再呈現 why-now／時間尺度／深度／缺資料，對應 U22–24 |
| 股票詳情 | 點 AAPL／MSFT／NVDA 切詳情；圖表並排支持／反證／失效情境與缺資料 |
| 搜尋／自選 | 搜尋三檔固定示例；自選存於本頁記憶體，重載重設，不觸發策略或交易 |
| 研究證據 | 可展開／收起；無實際來源或分析，不顯示已完成研究 |
| 手機 | 按「手機排列」或縮窄視窗；候選變橫列，圖表及研究逐區排列，無法見側欄時仍可回首頁 |
| 四個情境 | 頂部選單：示範／部分報告、離線／舊資料、行情缺資料、空清單 |
| 未接入功能 | 分析清單／研究／帳戶／期權入口只打開說明，不呼叫服務 |

所有價格、圖表、事件、持倉、進度與報告為人工示例。圖表期間按鈕只切換示意標籤；
不支援真實縮放／歷史載入。沒有 ticker resolution、API、auth、OpenD、AI 或交易連線。
本頁「離線」是測試情境，不是系統實際探測；完整能力分別屬 04b–04e 及後續 Sections。

## 實際驗證

- Edge／Playwright CLI，1440×1000 桌面、390×844 與 320×740 viewport。
- [21 項瀏覽器檢查](../../output/playwright/s04-04a/verification.json) 通過；
  [檢查腳本](../../output/playwright/s04-04a/check-preview.js)、[輸出](../../output/playwright/s04-04a/verification.log)。
- 人工查看[桌面首頁](../../output/playwright/s04-04a/home-desktop.png)、
  [股票詳情](../../output/playwright/s04-04a/detail-desktop.png)、
  [手機首頁](../../output/playwright/s04-04a/home-mobile.png)；
  [手機詳情截圖](../../output/playwright/s04-04a/detail-mobile.png) 亦已產生。
- 僅 viewport 檢查，未做 iPhone 真機或正式可及性／效能驗收。
- 首次 CLI 禁止 file URL，改用僅監聽 `127.0.0.1:19044` 的靜態預覽 server。
  首次 favicon 404 已以內嵌空 favicon 修正；沒有安裝 app 依賴或改動 application checkout。

## 待確認的視覺取捨

1. 深青導航＋淺色主畫面是否作為第一版風格。
2. 桌面詳情三區的資訊密度，以及手機先圖表後研究的閱讀順序。

確認後下一步為 04b，把此布局分拆成正式 React 元件，沿用 schema 與示範 transport；
此 HTML 只作設計參考，不整份搬成巨大 App.tsx。
