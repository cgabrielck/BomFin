# 領漲戰役接上 Harness（實驗，預設關）

**狀態：** 實驗接線。**產品預設未改。未合入。** 不是 alpha，也不把 E-STAIR-0 的官方 VALID=0 改寫。  
**策略代號：** `leader_campaign`（領漲戰役）  
**旗標：** `BOOMBOOM_EXPERIMENTAL_STRATEGIES`，未設定或 `0` 都是關。

規則文本在草案 PR #45（`docs/BOOMBOOM_NEW_STRATEGY.md`）。四種買點的分類器對齊草案 PR #46 的 E-STAIR-0 census。本分支不合併那兩張。`main` 已含 PR #47 的紙上閉環：判斷員呼叫留在唯一買入送單者 `process_signal` 的正前方（`AI_JUDGE=0` 時不打模型、不改張數）。領漲戰役走同一條路，沒有第二個送單者。

## 接了什麼

- 劇本：`backend/trading/strategies/experimental/leader_campaign.py`  
  四種買點 `gap_up` → `pivot_break` → `pocket_pivot` → `ma_pullback`。一天一檔一個 VALID，其餘是 skip code。
- 預設不載入。`KNOWN_STRATEGIES`、`STRATEGY_REGISTRY`、AI Mode 按鈕都沒有這個代號。Desk 的啟動 API 會拒絕它。
- 旗標打開之後，worker CLI 才列得出 `--strategy leader_campaign`。產品預設仍是 `breakout`。未知代號仍回到 `adaptive`。這個代號在旗標關閉時**不會**偷偷改跑別的策略，只記 `experimental_disabled`，不開新倉。
- 模組不 import `OrderManager`、`place_desk_order`、Alpaca 下單客戶端。`product_path_enabled()` 永遠是 false。Signal 不是訂單。
- 缺基本面分數是 `fund_missing`。來源是 `default` 或 `missing` 的 50／55 不會送進劇本。沒有 SPY 日線是 `market_unavailable`，不買。
- 出場按書面：樞紐跌回、均線、跳空的 5 日未到 +1R。沒有另做一個括號停利目標，避免紙上單用書面沒有的理由賣出。
- 沒有熱路徑去改實驗常數。日誌裡的 `why_no_trade` 只是證據。以後改規則仍是總督提案，等主人批准（方法文件的 Phase 4）。

E-STAIR-0 在同一 74 檔窗口的官方 VALID 仍是 **0**（四種都是 0，`stop_sparse`）。這一張沒有重跑普查，沒有做 E-STAIR-1 報酬回測，也沒有為了讓實盤出現買點而放寬規則。單元測試裡的 VALID 只用合成 K 線，證明接線在規則說成立時能交出 Signal。

## 紙上怎麼試

只在你願意看實驗輸出時打開旗標。預設不要開。不要加 `--allow-live`。

```bash
BOOMBOOM_EXPERIMENTAL_STRATEGIES=1 \
  python -m backend.trading.engine.worker \
  --strategy leader_campaign \
  --mode shadow \
  --once
```

`--mode paper` 仍走 Alpaca paper endpoint，同樣不要加 `--allow-live`。沒有合格買點時，這一輪應寫下 skip（`why_no_trade`），不應送出第二張單，也不應崩潰。

旗標關掉之後，同一個 `--strategy leader_campaign` 會被 CLI 拒絕。Desk／AI Mode 即使旗標開著也不能把這個代號存成產品模式。

劇本需要約兩年日線才有機會看完 252 日領漲條件，所以**只有**這個代號會把抓取週期從 `1y` 改成 `2y`。`breakout` 與其餘產品策略仍是 `1y`。這不是風險閘的改動。

## 刻意沒做

- 沒改 `RiskLimits`、半凱利 0.5、mandate、殺開關、VCP 常數。
- 沒把缺分填成 50 或 55。
- 沒有自動開始 E-STAIR-1。
- 沒有 Scout，沒有 `--allow-live`，沒有打開 `IGNORE_MARKET_HOURS`。
- 沒有把這個代號放進 AI Mode 預設選項。

## 經驗與學習

1. **普查 VALID=0 仍然成立。** 接線的成功是 worker 能跑、skip 寫得下來、旗標關掉不會下單。不是這套已經比 VCP 會用現金，也不是它贏過 SPY。
2. **合成 K 線只能證明規則讀得懂。** 樞紐、回踩、pocket pivot、跳空各自可以在人造資料上成為 VALID。那不是 74 檔窗口的成績。窗口成績仍是 0，所以停在 `stop_sparse`，不做報酬回測。
3. **缺分不能補。** Worker 給其他策略的中性 50 若流進這個代號，就會把 `fund_missing` 做成假及格。這個代號改看原始分數；沒有原始分數就當沒有。
4. **大市沒有 SPY 就不能買。** 別的趨勢策略在測試裡可以放行缺少的 SPY。領漲戰役的書面要求先看大市，所以沒有 SPY 是 `market_unavailable`。
5. **旗標不是第二條下單路。** 開著也只是讓既有的 `process_signal` 有機會收到 Signal。模組自己不能下單。關著就不能用這個 id 成交，也不能改去跑 `adaptive`。
6. **常數仍然不能自己改。** 倉位沿用現有的半凱利與約 1% 風險單位，再被單筆 $10,000 夾住。劇本上的勝率數字只是這條舊公式的輸入，沒有測量過，不代表優勢。要改門檻，仍是一次一個旋鈕的提案，等主人點頭。
