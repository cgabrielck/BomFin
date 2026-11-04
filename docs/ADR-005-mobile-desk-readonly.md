# ADR-005 — 手機 Desk 唯讀路徑 A｜Mobile Desk Read-Only Path A

> **Status:** **Draft**（pending Owner/PM Accepted）。**尚未 Accepted。** **Date：** 2026-11-04（Asia/Hong_Kong / HKT）。  
> **設計輸入：** UI UX `Mobile-Desk-RO-P0-spec.md` **定稿 v1.1**（2026-11-04）。本 ADR 係架構決策，**唔**係線框全文。三題產品鎖 **已鎖／定稿 v1.1**（見 §3）；鎖 ≠ 本檔 Accepted。  
> **路徑 A：** Option C 雙殼。**Tailscale Serve**（私有 HTTPS mesh）＋ Desk **響應式唯讀面**＋ Safari「加入主畫面」。**Capacitor = P1 later**（唔係本 ADR 交付）。  
> **基底：** quieter 已在 `main` — PR **#56** @ `d67b94ce`。本檔唔重做 #51–#56 圖表幾何。  
> **Binds under:** [ADR-003 + Addendum A](ADR-003-live-ai-trading-desk.md)（Accepted）> [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) > [AUDIT_REMEDIATION_PLAN_2026-10-21.md](AUDIT_REMEDIATION_PLAN_2026-10-21.md)（Confirmed 1–5 **不變**）> [ADR-004](ADR-004-chart-engine.md)（Accepted）> **本 Draft**。  
> **ADR-002 is VOID.** Issue **#10 stays OPEN.**  
> **Merge ≠ Accepted ≠ runtime。** **no live。** **Draft ≠ Accepted**（要 Owner 於閘後標 Accepted）。**HOLD** for triple gate。本輪 **docs-only**；唔改 runtime／`web/static`／backend／config／risk／mandate／kill。  
> **Index：** [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md)。  
> **Author lane：** Docs Arch。唔寫執行碼。

---

## 1. 背景｜Context

- 使用場景：Owner 早上用 iPhone（已在 tailnet）睇**紙上**隔夜結果，再決定紙上 worker 續跑或暫停。
- 產品殼係 **Desk**（FastAPI + `web/static`）。**Streamlit ≠ 手機主面**（lab／legacy；方向 C 只可鏡像，唔做手機產品）。
- 手機面要私有到達，唔好把 Desk 放到公網。
- 手機 **零下單**。交易、Approve live、改 live 規則，全部唔出現。
- 視覺對齊 quieter（#56 @ `d67b94ce`）：平色 `--bg`／`--card`、cyan 操作色。本 ADR 只鎖邊界，唔改該實作。

---

## 2. 決策｜Decision（Draft — 未 Accepted）

### D1. 暴露面 = Tailscale Serve（私有 mesh）

**採納：** 路徑 A 只走 **Tailscale Serve**。本機 Desk 經 tailnet 以私有 HTTPS 提供；憑證由 Tailscale 簽；只有已入 mesh 的裝置開到。

**唔採納 Funnel、ngrok，以及任何公網隧道**（含同類可分享公開 URL）。

| 選項 | 決定 | 原因 |
|------|------|------|
| **Tailscale Serve** | **是，路徑 A** | 私有 HTTPS。無公網主機名、無對全世界入站、無匿名互聯網客戶。身份邊界＝tailnet 裝置，對齊單人 Owner Desk。 |
| **Tailscale Funnel** | **否** | Funnel 把同一本機埠經公開代理放到**公網**。世界可路由 URL＝公網隧道，唔係私有 mesh。 |
| **ngrok／同類公網隧道** | **否** | 可分享公開 URL。陌生人可打到挨住 paper 控制的 Desk。多一層登入都唔改變「先暴露再補門」的形狀。 |
| **Capacitor／原生殼** | **唔係本 ADR 交付** | **P1 later**。P0 到達方式＝Serve URL＋Safari「加入主畫面」。 |

私有 mesh 先於「方便分享連結」。手機殼即使唯讀，仍挨住 paper worker 的 Continue／Pause；該控制**不得**對互聯網可達。公網 URL 會把交易台輪廓交畀未入 mesh 的人，並逼出第二套公開認證。本 ADR **唔**授權本 PR 開啟 Serve、Funnel，或任何隧道。

**不可達：** 文案以 **「請開啟 Tailscale」** 為準（可接「後重新整理」）。**禁止**引導 Funnel、ngrok，或任何公網替代。

### D2. 殼｜Option C

| 殼 | 手機角色 |
|----|----------|
| **Desk** | 產品權威。手機＝**獨立響應式唯讀佈局**（`/m` 或等效 mobile-RO 殼）。**唔**把桌面交易台縮小當手機面。寬屏 Desk 維持完整操作台；該操作台**唔**隨手機殼載入。 |
| **Streamlit** | **唔係**手機主面。lab／legacy；方向 C 唯讀鏡像只留桌面實驗，唔當手機產品。 |
| **Capacitor** | P1 later。本 ADR 不交付。 |

### D3. 資訊架構｜晨報｜狀態｜活動

窄屏底欄**固定 3 tab**，唔加第 4 tab：

| Tab | 中／EN | P0 |
|-----|--------|----|
| 首屏 | **晨報 Morning** | session_card、seal、vs-SPY（誠實）、digest ≤5、Continue／Pause（paper） |
| 次屏 | **狀態 Agents** | 掃描／評分／意圖／風控狀態條。**唯讀**。無 Run。 |
| 次屏 | **活動 Activity** | 歸因：誰做了什麼＋結果。**輸／跳過與盈利同級**。 |
| 延後 | 曲線 Equity | **唔入本輪、唔係本 ADR 的 P0** |
| 不做 | Ask Cgab FAB | **P0 唔要** |

晨報誠實：未達 seal **不**顯示 beat-SPY 英雄數；working ≠ filled ≠ seal；權益標 **paper · not live**。常駐誠實條：教學／觀察面，不是 verified／live，手機不下單、不改 live 規則。

Activity：`mode=paper|shadow`；executor／fill 標 **simulated／paper fill**。禁止「live 神速」話術、Weekly Top、leaderboard。

### D4. 零下單硬條｜Hard bars

手機 DOM／路由 **不得露出**（禁止用 disabled 假按鈕當裝飾——**寧缺**）：

- 下單／ticket／submit／broker 送單
- **Approve live**／`--allow-live`
- **改 live 規則**、改 risk 參數、改 live Harness
- **Scan·Deep**（及 Committee）**執行**；狀態可讀，執行鈕不可見
- 語意含券商 kill 的 Halt／Resume
- Deposit／Withdraw；Zone 畫具編輯、evidence 寫入（編輯留桌面）

**禁止** confetti、Nx、FOMO、`verified`／`live` stamp。指標或曲線（本 P0 亦唔做曲線）≠ 成交證明。

除 §3 的 paper Continue／Pause 外，手機面以 **GET／唯讀** 為主。下單、ops kill、live approve：**403 或未掛路由**。

### D5. 狀態語意｜Draft ≠ Accepted ≠ runtime

- 本檔係 **Draft**。三題已鎖 **唔** 等於本 ADR 已 Accepted。
- **Draft ≠ Accepted：** Owner 於閘後標 Accepted 之前，決策未生效。
- **Merge ≠ Accepted ≠ runtime：** 即使日後合入，只係文件落庫。唔改 runtime，唔等於已有 `/m`，唔等於已開 Serve。
- **no live。** 唔開 live，唔改 live Harness／mandate／kill／風險％。
- **HOLD** for triple gate。未過閘前，本 Draft **唔係**施工授權，亦唔係開 live 授權。
- Confirmed 1–5 **不變**。唔把本檔寫成 Confirmed item 6。Issue #10 **OPEN**。ADR-002 **VOID**。

---

## 3. 三題鎖定｜Resolved（定稿 v1.1，2026-11-04）

Owner/PM 2026-11-04 **已鎖／定稿 v1.1**。設計來源正文同此。

| # | 題 | 鎖定 |
|---|----|------|
| **1** | Continue／Pause | **P0 可 POST**，但 **只**控制 **paper** worker（對齊現有 paper start／stop）。按鈕文案 **必須含英文 paper**（例：Continue paper／Pause paper）。禁止「再開 live」。**唔**等於 Halt buys／券商 kill。P0 **不放** Halt。合約：POST 唔碰 live／broker／Approve。 |
| **2** | 權益曲線事件釘 | **延後**。唔入本輪 PR，**唔係**本 ADR 的 P0。P0 不做折線、事件釘、曲線 tab、晨報內折疊釘。 |
| **3** | Ask Cgab FAB | **P0 唔要**。導航表＝不做。晨報誠實條仍在；只是無 FAB。 |

---

## 4. 零下單驗收｜Checklist

下列係**日後實作**的驗收。本 PR 只落文件，**唔**聲稱任何一項已過，**唔**勾選。

### UI

- [ ] 390px：晨報／狀態／活動可走完主路徑；無橫向強制翻去桌面交易台
- [ ] DOM 無下單、Approve live、改 live 規則、Scan·Deep 執行（含假 disabled 裝飾——寧缺）
- [ ] Continue／Pause 文案含 **paper**；點擊不觸發 live／broker
- [ ] session_card／seal／vs-SPY 誠實；未 seal 不秀 beat-SPY 英雄數
- [ ] Activity 含輸／skip；無 confetti／Nx／FOMO／top-trades
- [ ] 不可達文案係「請開啟 Tailscale」（可接後重新整理）；**無** Funnel／ngrok 引導
- [ ] 無 `verified`／`live` stamp
- [ ] Streamlit 未當手機主面；Option C 文案不漂移
- [ ] 底欄只有 晨報｜狀態｜活動；無曲線釘；無 Ask Cgab FAB

### API／邊界

- [ ] 除 Continue／Pause paper 外，手機面以 GET／唯讀為主（或 RO scope）；POST 下單／ops kill／live approve **403 或未掛**
- [ ] Continue／Pause：**允許 POST**，僅 paper worker start／stop；文案含 paper；測試證明唔碰 live／broker
- [ ] Serve only；CI／腳本唔開 Funnel、ngrok，或公網隧道
- [ ] DOM／文案掃描禁下單、Approve live、place order、ticket submit

### 明確勿做

- 手機開 live；Funnel／ngrok 當預設公開
- Streamlit 當手機產品
- 本 ADR 交付 Capacitor（P1 另案）
- 曲線事件釘、Ask Cgab FAB
- confetti／Nx／FOMO／verified·live
- 借本 RO 文件宣稱 runtime 已開、Serve 已開、或本 Draft 已 Accepted

---

## 5. 唔得宣稱｜Must not claim

1. 本 Draft 已係 Accepted，或三題已鎖＝Owner 已 Accept 本 ADR。  
2. 合入本檔＝runtime 已改、手機殼已上線、Serve 已開、或 live 已開。  
3. Funnel／ngrok／公網隧道係路徑 A 的後備。  
4. Continue／Pause paper POST＝下單、Approve live、Halt，或券商 kill。  
5. 曲線釘或 Ask Cgab FAB 屬本 P0。  
6. Streamlit 係手機主面；Capacitor 屬本 ADR 交付。  
7. ADR-002 仍有效；Confirmed 變成 6 項；Issue #10 已關。  
8. 手機面可 stamp `verified`／`live`。

---

## 6. Out of scope

- 任何 runtime、`web/static`、backend、config、risk／mandate／kill；開 live。  
- 實作 `/m`、Tailscale 機位、CI。本檔只決定暴露類別與驗收，**HOLD** 到 Accepted。  
- 改寫 ADR-003、MODULAR、AUDIT Confirmed 1–5 正文。  
- Capacitor；權益曲線事件釘；Ask Cgab FAB。  
- 重做 quieter #56 或 #51–#56 圖表幾何。

---

## 7. 權威次序｜Authority

1. ADR-003 + Addendum A  
2. MODULAR_ARCHITECTURE  
3. AUDIT_REMEDIATION_PLAN（Confirmed 1–5）  
4. ADR-004（Accepted）  
5. **本 ADR-005（Draft，2026-11-04）** — 未 Accepted；低於上列  
6. 舊 roadmap（frozen）；**ADR-002 VOID**

衝突時：ADR-003 > MODULAR > AUDIT > ADR-004 > 本 Draft。本 Draft 未 Accepted 前，唔推翻上列。

---

*Drafted 2026-11-04（Asia/Hong_Kong）by Docs Arch。設計輸入＝Mobile Desk RO P0 spec 定稿 v1.1（三題已鎖）。Status＝**Draft**，pending Owner/PM Accepted。docs-only。**Merge ≠ Accepted ≠ runtime。no live。HOLD** for triple gate。*
