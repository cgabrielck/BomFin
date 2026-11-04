# Tailscale Serve — 手機 Desk 唯讀（路徑 A）

**狀態：** 操作說明。**ADR-005 仍是 Draft**，本文件不把它標成 Accepted，也不開 live。  
**殼：** Desk（FastAPI + `web/static`）的 `/m`。Streamlit 不是手機主面。  
**到達：** Tailscale **Serve**（私有 HTTPS mesh）＋ Safari「加入主畫面」。  
**Merge ≠ Accepted ≠ runtime。no live。**

手機面是晨報｜狀態｜活動。Continue paper／Pause paper 只影響 **paper** worker。手機不下單、不 Approve live、不改 live 規則。

打不開時，頁面文案是：**請開啟 Tailscale 後重新整理**。

本文件只描述 Tailscale Serve。公開隧道（包括 Funnel、ngrok）不是路徑 A，這裡不提供它們的開啟步驟。

---

## 1. Desk 主機

在已經跑 Desk 的機器上安裝 Tailscale，並登入 **與手機同一個 tailnet**。Desk 預設聽本機埠（下面以 `8000` 為例）：

```bash
# 例：本機只聽 loopback。Serve 會在 tailnet 上提供私有 HTTPS。
uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

確認 `APCA_PAPER=true`。這份說明不包含把帳本改成 live。

## 2. 開啟 Serve

在 Desk 主機：

```bash
tailscale up
tailscale serve --bg 8000
tailscale serve status
```

`tailscale serve status` 會列出 tailnet 上的 HTTPS 名稱，形狀類似：

`https://<machine>.<tailnet>.ts.net/`

手機晨報路徑是那個來源下面的 `/m`：

`https://<machine>.<tailnet>.ts.net/m`

只有已加入這個 tailnet 的裝置開得到。Serve 使用 Tailscale 簽的憑證。

關掉 Serve（不會改交易狀態）：

```bash
tailscale serve off
```

## 3. 手機

1. 在 iPhone 安裝 Tailscale，登入同一個 tailnet，並保持連線。
2. 用 Safari 打開上面的 `https://…/m`（不要用桌面交易台當手機主畫面）。
3. 加入主畫面：分享 → **加入主畫面** → 名稱可用 Cgab。之後從主畫面圖示進入 `/m`。

第一次若要操作 Continue paper／Pause paper，在主機設定 `DESK_OPERATOR_TOKEN`，然後只開一次：

`https://<machine>.<tailnet>.ts.net/m?op=<DESK_OPERATOR_TOKEN>`

頁面會把 token 放進 cookie 並從網址列拿掉。之後用沒有 `?op=` 的 `/m` 即可。

只給看、不給 Continue／Pause：另設 `DESK_RO_TOKEN`，用 `https://…/m?ro=<DESK_RO_TOKEN>`。這個 token 讀得到晨報，不能改 paper worker，也不能下單。

沒有 token、又不是 Desk 主機本機 loopback 的連線，是唯讀客人：數字不展開，Continue／Pause 不出現。

## 4. 手機上看見什麼

| 連線 | 畫面 |
|------|------|
| Tailscale 已通、API 有回應 | 頂欄 `Tailscale OK`（在主機本機開則是 `本機 OK`） |
| 打不開 | `請開啟 Tailscale 後重新整理`。若曾成功載入，會留上次快照並標 stale |
| 尚無 worker session card | `尚無紙上 session`（不補假數字） |

底欄只有三頁：晨報、狀態、活動。沒有曲線、沒有 Ask Cgab。

## 5. 這份說明不做的事

- 不把 ADR-005 從 Draft 改成 Accepted。
- 不開 live，不改 mandate／kill／風險％。
- 不把 Streamlit 當手機產品。
- 不交付 Capacitor（那是之後的 P1）。
- 不把公開隧道寫成備用做法。
