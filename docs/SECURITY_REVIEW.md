# 前端安全檢視與補強紀錄｜v5.9

## 範圍

以使用者提供的 `en_compare_manager_v5_8.html` 為基礎，靜態核對程式並在交付的 `index.html` 加入補強；再進行有限的瀏覽器回歸測試。**沒有掃描或更動 laundry.com.tw、GitHub 帳號設定或目前線上的 Pages。**

v5.8 基線 SHA-256：`1d845ba697bf384bb6f246be6de6fe518fc834fb18154774909f03023e7d2f1a`。

目前版本 `index.html` SHA-256：`0b40856a048f37f5672c83627531b1c55e0e9735ded2f3084202def290812fd6`。

## 原始程式中可核對的內容

基線已有 CSP、以 Blob／Canvas 在本機處理圖片、輸出 MIME 核對、圖片數量／單檔容量／輸出像素限制、動態檔名以 textContent 顯示等措施。

原始設定匯入主要檢查 `cfg` 是否為 object，並把它直接展開到 defaults；慣用版型也直接合併設定。這不足以確保數值有限、型別正確或結構大小合理。本次**未把此問題定性為已證實的遠端程式執行漏洞**；主要可直接確認的是異常狀態、資源耗用和錯誤處理風險。

另外，`script-src 'unsafe-inline'` 允許更多內嵌腳本；資料夾計數沒有一致的跨根目錄預算；讀取 localStorage 的內容缺少完整欄位驗證。

## 本次已落地的補強

### JSON 輸入

所有設定檔、慣用版型檔和 localStorage 內容共用 bounded parser。檔案在 `.text()` 前先檢查大小（非空白、最多 1 MiB），解析後限制 12 層、4096 節點及單一物件／陣列 256 個項目。JSON 全樹的 `__proto__`、`constructor`、`prototype` 鍵直接拒絕。

cfg 只複製 defaults 的已知欄位。數值需是有限 number；布林需是 boolean；選單需是允許值；色碼限定 #RRGGBB；文字限制長度。超界有限數值做範圍限制並記錄，型別錯誤則拒絕整筆。固定輸出超過 2000 萬像素時拒絕套用；依原圖計算的尺寸還會在渲染時檢查。

慣用版型最多 12 組，拒絕重複名稱與壞項目。全部檢查通過後才替換；已有版型時先確認。匯入失敗保留既有狀態。localStorage 讀寫失敗會顯示「僅暫存」而不是假裝永久儲存。

### CSP 與外部連線

主頁 `script-src` 使用 SHA-256 白名單、`script-src-attr 'none'`；保留 `default-src 'none'`、`connect-src 'none'`、`object-src 'none'`、`base-uri 'none'`、`form-action 'none'`，並明確禁止 frame／worker／media 資源。圖片只允許 data:／blob:。沒有加入外部 JavaScript、字型、計數徽章或分析碼。

額外內嵌 script 阻擋與對外 fetch 拒絕有測試記錄。`connect-src` 不是「封鎖一切網路」：初次載入線上網站和使用者點連結仍會導覽到外部網站。外連使用 noopener／noreferrer，頁面 referrer policy 為 no-referrer。

**仍保留 CSS 的 `style-src 'unsafe-inline'`**，因工具原有大量 inline style 及動態樣式。沒有將此包稱為全面 strict CSP。SHA-256 不能防止已有寫入權的攻擊者連程式和 hash 一起改；它不是程式碼保密或簽章認證。

依 W3C 的 CSP 規則，meta 傳送不支援 `frame-ancestors` 等全部指令；本包沒有用無效 meta 設定宣稱防止點擊劫持。要新增這類防護須由可控制 HTTP response header 的部署層處理。[CSP Level 3](https://www.w3.org/TR/CSP3/)

### 圖片與資源限制

新增檔頭與副檔名相符檢查，拒絕偽裝成 JPG 的 SVG／HTML。單次掃描最多 1000 項（含目錄）和 16 層。保留 256 張、單張 50 MiB／6000 萬像素上限，新增來源總容量 256 MiB及已載入總像素 1.2 億；單張解碼等待設 15 秒期限。

**檔頭比對不是防毒或完整解碼驗證**。像素是在瀏覽器載入圖片後檢查，不能保證避免解碼器在檢查前分配記憶體，也不能以 setTimeout 中止所有同步解碼工作。仍需更新瀏覽器並避免不明輸入；資源上限不代表低配裝置一定流暢。

### DOM、操作與資料邊界

檔名、狀態、版型名稱走 textContent；標題是 Canvas 文字，不作 HTML 插入。本次對惡意樣式名稱與偽裝圖檔測試未觸發注入。

修正文字與底條命中層級、小數與滑鼠滾輪錯誤；清空照片時同步清空會引用已釋放 Blob 的歷史。批次檔名以不分大小寫比對避免 Windows 解壓混淆。相容舊入口改成導向主程式，避免 root 同時維護舊的可執行版本。

## v6.2 新增：專案檔、觸控縮放與 HEIC 辨識

### 專案檔是新的不受信任輸入

「開啟專案檔」讀入的 `.enproj` 可能來自別人，全部內容都當成不可信資料處理：

- 只接受不壓縮（stored）的 ZIP。壓縮、加密、使用 data descriptor、分卷的檔案一律拒絕；不做解壓縮，因此沒有解壓縮炸彈的問題。
- 先檢查整體大小（約 280 MiB）、項目數（300）、目錄大小（1 MiB），每個項目的位置與長度都必須落在檔案資料區內，並驗證 CRC-32。
- `project.json` 上限 8 MiB，用同一個有界解析器檢查節點數、深度、單一物件大小，並拒絕 `__proto__`／`constructor`／`prototype` 鍵。
- 欄位逐項白名單：對比設定走原有的 `sanitizeConfig`，工具箱設定走 `validConfig`，位置、裁切、遮蔽、標記只接受有限數值並夾限到合法範圍，類型與顏色必須是允許值，照片只能引用清單內的編號。
- ZIP 內的項目名稱不採信：照片項目名稱由序號與副檔名推導，副檔名必須在允許清單內；檔名中的路徑分隔與控制字元會被移除。
- 照片位元組仍走原本的匯入流程（檔頭簽章、單張與合計容量、像素上限、瀏覽器解碼）。
- 以上全部通過後才詢問並取代目前的工作階段；任何一項失敗就整份拒絕，目前的照片與編輯不變。個別照片無法解碼時略過該張，並丟棄引用它的指定、批次組合與工具箱編輯。
- 存檔前會用同一套驗證自我檢查，避免寫出這個版本自己打不開的檔案。

專案檔內含原始照片與檔名、相對路徑，等同客戶資料；文件已提醒不要上傳公開 repo。

### 沒有加入第三方解碼器，CSP 沒有放寬

HEIC 只做「辨識 + 交給瀏覽器解碼」：以 `ftyp` brand 判斷檔案確實是 HEIC／HEIF 後，交給瀏覽器的 `<img>` 解碼。目前只有 Safari 17 以上能解；Chrome、Edge 會略過並提示先轉成 JPEG。

要讓 Chrome／Edge 也能開 HEIC，需要內建第三方解碼元件（例如 libheif 的 WebAssembly 版，LGPL，約 2 MB），並在 CSP 加入該檔案的雜湊與 `'wasm-unsafe-eval'`。這會改變「沒有第三方程式碼」的前提，本版沒有這樣做；`script-src` 仍然只有兩個內嵌腳本的 SHA-256。是否加入由維護者決定。

### 其他

- 關閉分頁前的提醒（`beforeunload`）只是提醒，不會保存任何資料，也不寫入瀏覽器儲存空間。
- 雙指縮放只改變目前照片的縮放與位置，數值與滑鼠滾輪使用相同的夾限。
- 本段新增的程式沒有新增任何 HTML 字串插入、外部連線或瀏覽器儲存空間的使用。

### 這一段的驗證限制

HEIC 的瀏覽器原生解碼（Safari）無法在測試環境驗證，只驗證了辨識、拒絕與提示。觸控手勢以 Chromium 的觸控輸入驗證，未在實體手機或平板上測試。專案檔以 Chromium 驗證存取往返與 23 種損毀或惡意內容的拒絕。

## 仍需維護者處理

GitHub 的私下安全回報、通知、帳號安全、secret scanning 警示／Push protection、協作審查與發版權限都沒有由本包自動開啟。`SECURITY.md` 只是政策與回報說明。見 [更新說明](DEPLOYMENT.md)。

未新增 LICENSE；未替維護者承諾回報期限、修復期限或獎勵。

## 仍存在的限制

純前端程式會被使用者取得；不能在裡面放 Token 或商業機密。localStorage 是 origin 級、未加密的瀏覽器資料，不是安全保險箱；檔名、標題和 ZIP 清單也可能含客資。瀏覽器擴充套件、裝置感染、主機／帳號遭接管、跨 origin 儲存差異、影像解碼漏洞不屬於這次可全面排除的範圍。

照片與批次編輯沒有跨工作階段保存。也沒有把「平台縮圖預覽」當成 FB／IG 的真實即時呈現。[localStorage 的官方瀏覽器說明](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage)

## 驗證結論

本次 43 項指定檢查通過，包含 JSON、拖移、三格式編碼、ZIP CRC、文字安全輸出及 CSP 行為；這是限定測試樣本的結果，**不是「沒有漏洞」的保證**。測試採 Linux Chromium 144 headless，使用完整 HTML 的 set_content；Windows file://／線上 Pages、持久儲存、下載落盤與其他瀏覽器尚需實機確認。

詳見 [測試範圍與結果](../tests/RESULTS.md)。
