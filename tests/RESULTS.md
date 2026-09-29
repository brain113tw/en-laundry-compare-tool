# 測試紀錄｜v5.9

本次共有 **43 項檢查通過**。本記錄是限定範圍的功能／安全回歸，不是第三方認證，也不是所有瀏覽器或所有輸入的證明。

## 測試環境與限制

Linux、Chromium **141.0.7390.37**（v5.9 首次交付時為 144.0.7559.96；後續修正版以此版本重跑，43 項仍全部通過），由 Playwright 控制 headless browser。執行環境的管理政策阻止 `file://` 和 HTTP 導覽，因此使用 **about:blank + set_content** 載入完整交付 HTML，未修改程式中的 CSP。

已測 DOM 拖放事件、input 匯入、主畫面實際指標拖曳、三格式 Blob 編碼、ZIP 結構與 CRC、惡意／損壞 JSON 拒絕、CSP 阻擋額外 inline script、儲存被拒時的降級。輸出檔由測試程式讀出並核對，而非端到端驗證 Windows 下載介面。

**未端到端驗證：**Windows Chrome／Edge 檔案總管原生拖放、GitHub Pages 線上部署、跨分頁／跨工作階段 localStorage 持久性、瀏覽器下載資料夾落盤流程、手機、Safari、Firefox、全部圖片解碼器。file:// 與 HTTP/HTTPS 不同來源的儲存表現須由使用者在實機確認。

CSP `unsafe-eval` 以政策內容檢查；未以 DevTools evaluate 是否成功作為網頁 CSP 結論，因為偵錯介面本來就可能具額外權限。

## 檢查結果

| 編號 | 測試 | 結果 |
|---:|---|---|
| 1 | CSP script hash matches source | 通過 |
| 2 | Starts without JS errors | 通過 |
| 3 | Storage unavailable handled | 通過 |
| 4 | Import normal PNGs | 通過 |
| 5 | Output size values exist | 通過 |
| 6 | Left blank area handles drop | 通過 |
| 7 | Reject renamed SVG input | 通過 |
| 8 | Invalid cfg rejected 1 | 通過 |
| 9 | Invalid cfg rejected 2 | 通過 |
| 10 | Invalid cfg rejected 3 | 通過 |
| 11 | Invalid cfg rejected 4 | 通過 |
| 12 | Invalid cfg rejected 5 | 通過 |
| 13 | Invalid cfg rejected 6 | 通過 |
| 14 | Invalid cfg rejected 7 | 通過 |
| 15 | Invalid cfg rejected 8 | 通過 |
| 16 | Reject prototype | 通過 |
| 17 | Reject deep | 通過 |
| 18 | Reject oversize | 通過 |
| 19 | Reject syntax | 通過 |
| 20 | No prototype pollution | 通過 |
| 21 | JSON size guard precedes reading | 通過 |
| 22 | v5.8 import compatibility + clamp + allowlist | 通過 |
| 23 | Fractional positions preserved | 通過 |
| 24 | Watermark text above background hit | 通過 |
| 25 | Dragging watermark leaves bar unchanged | 通過 |
| 26 | Wheel over non-photo objects no exception | 通過 |
| 27 | WEBP real encoding / dimensions / bytes | 通過 |
| 28 | PNG real encoding / dimensions / bytes | 通過 |
| 29 | SVG real encoding / dimensions / bytes | 通過 |
| 30 | Guides not exported | 通過 |
| 31 | ZIP Unicode filename and CRC | 通過 |
| 32 | Storage failure reported (not falsely saved) | 通過 |
| 33 | Bad favorites keep existing entries | 通過 |
| 34 | Template name rendered as literal text | 通過 |
| 35 | Undo config works | 通過 |
| 36 | Redo config works | 通過 |
| 37 | Desktop has no horizontal overflow | 通過 |
| 38 | Unhashed inline script blocked | 通過 |
| 39 | unsafe-eval not allowed in policy | 通過 |
| 40 | Fetch blocked by CSP | 通過 |
| 41 | No ordinary remote subresource requests | 通過 |
| 42 | Clear resets undo before releasing sources | 通過 |
| 43 | No unhandled JS runtime errors | 通過 |

## 可重跑的開發測試

`check_release.py` 使用 Python、Playwright 和 Pillow，僅供開發驗證；工具使用者不需要安裝它們。測試在臨時目錄產生幾何素材，不使用客戶照片。預設尋找 `chromium`，或設定 `CHROMIUM_EXECUTABLE`；也可安裝 Playwright 自帶 Chromium。

```bash
python -m pip install playwright pillow
python -m playwright install chromium
python tests/check_release.py
```

原始紀錄：[test-results.json](test-results.json)。docs/screenshots 的示意截圖另以本機 HTTP 伺服器載入後擷取，因此顯示正常的 localStorage 儲存狀態，與本表第 3、32 項刻意測試的「儲存被拒」畫面不同。測試產物與瀏覽器版本不同可能導致容量差異，不以固定 bytes 作跨版本基準。
