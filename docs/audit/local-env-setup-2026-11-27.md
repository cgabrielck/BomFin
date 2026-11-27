# 本地環境搭建記錄

> 歷史記錄：以下步驟在 `.worktrees/gabfin-s01` 執行。2026-11-27 起原始碼已提升
> 至 repo 根目錄 `C:\Users\001\Downloads\GabFin-ai-trade`，命令的 `cd` 目標改為根目錄。

- 路徑：`C:\Users\001\Downloads\GabFin-ai-trade`（原為 `.worktrees\gabfin-s01`）；branch `codex/s01-source-baseline`。
- 約束：只修改 Downloads 資料夾內的檔案；不依賴 Desktop checkout。
- 原因：原有 `.venv` 的 `pyvenv.cfg` 與 editable `.pth` 都指向
  `C:\Users\001\Desktop\GabFin-ai-trade\...`，違反上述約束且跨 checkout 不可靠。

## 步驟（已在 Windows 11 / PowerShell 實跑）

```powershell
cd C:\Users\001\Downloads\GabFin-ai-trade
$py = "C:\Users\001\Downloads\GabFin-ai-trade\.tools\python\cpython-3.12.16-windows-x86_64-none\python.exe"
& $py -m venv .venv-local
.venv-local\Scripts\python.exe -m pip install --upgrade pip
.venv-local\Scripts\python.exe -m pip install "pydantic==2.14.4" "fastapi==0.165.0" "tzdata==2026.6" "uvicorn==0.54.0" "websockets==17.4" "pytest>=8.0.0"
.venv-local\Scripts\python.exe -m pip install httpx2          # starlette TestClient 必需
.venv-local\Scripts\python.exe -m pip install -r requirements.txt   # legacy conftest 需要 pandas 等
.venv-local\Scripts\python.exe -m pip install -e .            # editable → services/
Rename-Item .venv-local .venv
```

## 驗證結果

- `.venv\Scripts\python.exe -c "import gabfin"` → 指向 `...\worktrees\gabfin-s01\services\gabfin\__init__.py`。
- `pytest tests/gabfin` → **925 passed**。
- `pytest tests/gabfin/test_market_api.py` → 25 passed；`test_session_auth.py` 合計 35 passed。
- `npm.cmd run typecheck` exit 0；`npm.cmd run build` exit 0。
- `npx.cmd playwright test` → **31 passed**（含 3 項 04e acceptance），約 2.9 分鐘，使用已安裝 Microsoft Edge。
- `scripts/check-demo-fixtures.py` → 3 quote／3 bar snapshots 通過，60 bars，NVDA 空。
- Vite dev server 於 http://127.0.0.1:19045 實際啟動並渲染首頁／股票詳情／合成 K 線。

## 環境事實

- Python 3.12.16（`.tools/python/cpython-3.12.16-windows-x86_64-none`）；Node v24.19.0；npm 11.17.0。
- `.venv` 已被 `.gitignore` 忽略（`.gitignore:6`），不污染版本控制。
- Playwright 瀏覽器使用系統已安裝 Microsoft Edge（`channel: 'msedge'`），無需另下載 Chromium。
- `pip install -r requirements.txt` 需約 3.7 分鐘（pandas 3.1.1／numpy 為主），非離線可用；
  pip 與 npm 網路在本機可用。
- 既有 `.tools/uv-bootstrap`（uv 0.13.9）與 `.tools/uv-cache` 存在，可作後續加速。
