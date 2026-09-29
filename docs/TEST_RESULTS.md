# v6.2 限定範圍測試紀錄

這是本次執行結果，不是外部安全認證或零漏洞保證。

| 範圍 | 檢查數 | 通過 |
|---|---:|---:|
| 比較工作區回歸 | 43 | 43 |
| 新工具箱 | 54 | 54 |
| 追加邊界與操作 | 11 | 11 |
| 合計 | 108 | 108 |

## 環境與限制

Linux Chromium headless / Python Playwright。HTML 使用 page.set_content，因執行環境限制本機導航；沒有弱化正式程式的 CSP。下載由實際編碼產生 Blob，測試直接擷取 Blob 驗證格式、尺寸、位元組數與 ZIP CRC，未操作使用者 Windows 另存新檔視窗。

沒有驗證 Windows 原生檔案總管拖放、file:// 導覽、Safari/Firefox、GitHub Pages 實際部署、全部 EXIF／色彩描述檔或所有惡意圖片。localStorage 寫入被拒絕時的明確提示有測，但未做關閉重開之後的持久儲存端到端驗證。

## 覆蓋範圍

新舊工作區啟動、分享照片清單、拖入事件、等比例及90度旋轉、裁切、裁切後旋轉之遮蔽座標、全不透明遮蔽、模糊、馬賽克、四角拉伸、鎖定裁切比例、文字浮水印拖曳、Logo載入、Undo/Redo、各張局部編輯、數值0、平坦區銳化亮度、容量不可達警告、批次依勾選輸出且保留遮蔽、JSON白名單與容量限制、CSP雜湊和網路限制、1366px及390px水平版面，以及處理過的PNG回到比較素材清單。

## 可重跑的檔案

`tests/check_compare.py` 與 `tests/check_toolbox.py` 是開發者測試，需要 Python、Playwright、Pillow 及 Chromium。一般使用者只開 HTML，無須這些環境。

`tests/additional_test_source.txt` 是追加11項測試的來源紀錄，使用工具箱測試產生的校準圖片。`tests/results.json` 保留各項結果。

測試與截圖僅使用合成示意素材，沒有客戶照片。原圖、Logo與局部工作內容不會跨關閉分頁保存；本版不是完整專案自動儲存。
