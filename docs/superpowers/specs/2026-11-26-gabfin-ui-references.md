# S04 UI 參考初篩

狀態：使用者已同意混合布局方向；已查看下列官方圖片，尚未完成線框或執行實際 UI 驗收；未引入第三方程式碼。
使用者允許有選擇地重用 GitHub UI，要求按 GabFin 用途及 codebase 判斷，並節省 token。
需求依據：[設計 U02、U13、U22–U24、§10](2026-11-25-gabfin-system-design.md)、
[Task 7](../plans/2026-11-25-gabfin-upgrade-plan.md)。

## 已查三個來源（2026-11-26）

只查 GitHub repo metadata、README 及 LICENSE；沒有 clone、安裝、執行或通讀原始碼。
以下是根據文件作的適配判斷，不是對實際畫面或實盤能力的驗收。

| 專案／來源 | 已核對情況 | GabFin 可借鑑方向 | 本輪取捨 |
|---|---|---|---|
| [AI Hedge Fund](https://github.com/virattt/ai-hedge-fund/blob/main/README.md) | 目前為互動 terminal app；paper／backtest 流程；[MIT](https://github.com/virattt/ai-hedge-fund/blob/main/LICENSE) | 研究任務、決策結果、session history 的分層 | 參考流程，不當 React UI 元件來源；README 的教育定位不構成交易可靠性證據 |
| [Ghostfolio](https://github.com/ghostfolio/ghostfolio/blob/main/README.md) | Angular；投資組合、績效、風險、mobile-first PWA；[AGPL-3.0](https://github.com/ghostfolio/ghostfolio/blob/main/LICENSE) | 持倉／曝險摘要、手機資訊優先序 | 參考資訊架構，不搬 Angular／後端；不是 AI 交易產品 |
| [Fincept Terminal](https://github.com/Fincept-Corporation/FinceptTerminal/blob/main/README.md) | 目前 C++20／Qt6 桌面程式；金融研究 dashboard；[AGPL-3.0](https://github.com/Fincept-Corporation/FinceptTerminal/blob/main/LICENSE) | 圖表、研究、投資組合工作區劃分 | 參考分區，不搬原生桌面架構或假設付費版能力存在於開源版 |

## GabFin 適配建議

- 首頁先呈現機會、why-now、研究深度與缺資料；有持倉時重要風險置頂。
- 股票詳情把圖表與支持／反對證據放在一起，分開標示初篩及深入研究。
- 固定展示 paper 狀態、來源、資料時間、stale／權益未知；舊價不包裝成即時。
- 研究聊天保持 advisory；交易控制獨立，模型／券商 key 不進前端。
- 桌面可用分區，手機按資訊優先序折疊；保持 React/Vite、S03 契約及增量更新邊界。

## 重用與成本規則

- 本輪上限三個 repo，已完成初篩；下一步產出一份 GabFin 線框，不再擴大搜尋。
- 真正有合適元件才讀其相關檔案；先固定來源 commit／檔案、核對授權與依賴，
  保留必要來源及 notices，再接 GabFin 契約。以上主專案授權不代替逐檔／素材核對。
- 不帶入原專案 broker 邏輯、模型編排、後端服務或整套 dependencies。
- 小範圍自查及相關驗證；不另派研究／文件審查 Agent。既有技能按需使用。

下一步：04a 的首頁／股票詳情線框，標明各分區對應需求及資料來源；尚未開始實作。

## 官方圖片核對與推薦

- [Fincept Equity Research](https://raw.githubusercontent.com/Fincept-Corporation/FinceptTerminal/main/images/EquityResearch.png)：
  已查看，高密度深色研究分頁／多圖面板；截圖包含 Enterprise 標記，不證明開源版功能完全相同。
- [Ghostfolio 手機 UI](https://raw.githubusercontent.com/ghostfolio/ghostfolio/main/apps/client/src/assets/images/screenshot.png)：
  已查看，簡潔淨值／績效圖、時間範圍與底部導航；是官方提供的示例圖，非本次運行截圖。
- AI Hedge Fund README 的主圖實際為系統架構圖，不能冒充產品 UI；移出視覺候選，保留流程參考。
- 已同意混合方向：Ghostfolio 的清晰層級及手機簡潔度，搭配 Fincept 的
  桌面研究分區；首頁優先機會／風險，股票詳情分圖表與研究證據，低層資料按需展開。
- 圖片快照保留於 `docs/audit/artifacts/s04-ui-references/`；沒有運行或複製上述產品程式碼。
