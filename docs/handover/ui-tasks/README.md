# 前端任務卡

每個前端單位一份。任務卡由後端寫，Carbon 只依任務卡與
`apps/desk-web/src/shared/contracts/generated.ts` 工作。

## 任務卡格式

- 標題：`WU-<n>-ui`
- 目標：一句話說明這個 UI 單位要做什麼。
- Base：後端 commit SHA 與分支。
- 改動範圍：可以動的檔案（相對於 `apps/desk-web/src/`）。
- 不可動：明確列出的檔案與理由。
- 資料流：元件 → hook → 端點 → 型別。
- 合約：這個 UI 依賴的 TS 型別與欄位（引用 `ui-contract.md` 的段落）。
- 驗收條件：可觀察、可測試的條件。
- 測試：需要新增或更新的 Playwright 檔。
- 完成後：怎麼回填 `HANDOVER.md`。

## 目前的任務卡

| 任務卡 | 狀態 | 對應後端單位 |
|---|---|---|
| [WU-9-ui.md](WU-9-ui.md) | 可開始 | WU-9 分析平面與端點（commit `5c49495a`） |
