# v6.2 更新到 GitHub Pages

這一包是本機交付檔，不會自己修改你的 GitHub 或 laundry.com.tw。

## 本機先試

1. 解壓縮到新的資料夾，保留舊版備份。
2. 用 Chrome / Edge 開 `index.html`。
3. 左上應看到 v6.2；按「圖片工具箱・單張 / 批次」測一張。
4. 有 iPhone 的 HEIC 照片時，加入一張確認能顯示。這一步需要 `index.html` 旁邊的 `vendor` 資料夾。
5. 舊版先匯出慣用版型 JSON 留在自己的電腦。照片與工作內容不是版型，請先完成輸出。

## 上傳

在原 repository 的 `Code → Add file → Upload files`，將解壓縮後的檔案和子資料夾上傳到 repo 根目錄，覆蓋同名檔案。**index.html 必須在根目錄，不要多包一層資料夾，也不要只上傳 ZIP。**

最少要更新 `index.html` 與 `vendor` 資料夾（裡面的 `heic-decoder.html` 是 Chrome、Edge 開 HEIC 照片用的解碼元件，約 2 MB，另有兩份授權文件）；README、docs、SECURITY 與舊版入口檔也應一起更新，避免文件或舊網址落後。少了 `vendor` 資料夾工具仍可使用，只有 HEIC 照片會被略過並提示。

Commit message：

```text
Update to v6.2: local toolbox, selected batch export and reusable presets
```

Pages 保持原本 `main / (root)` 設定，本包有 `.nojekyll`。等待對應本次新提交的部署完成，再開工具網址核對 v6.2。不要把重跑舊提交的成功紀錄當成新版已發布。

GitHub Pages 官方發布來源說明：https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## 哪個 HTML 要開

- `index.html`：正式主入口。
- `en_compare_manager_v6_2_toolbox.html`：與主入口內容相同，供下載單檔使用。
- `en_compare_manager_v5_8.html`、`en_compare_manager_v6_0_toolbox.html`、`en_compare_manager_v6_1_toolbox.html`：舊網址相容入口，會導向主入口，沒有保留舊程式碼。

若公開 repo 原本有其他老版本完整 HTML，仍會公開且可直接訪問。本次工具沒有自動刪除你 repo 的檔案；請自行決定移除舊版或改相容入口。

## CSP 注意

正式 HTML 內嵌腳本的內容有 SHA-256 CSP 雜湊。不要只手動改腳本、貼入額外腳本或讓編輯器亂換腳本換行符，否則會被瀏覽器阻擋。

維護者修改後可用 `python tools/update_csp.py` 重算雜湊並同步兩個 v6.2 入口。一般使用者不需要執行此指令。

## HEIC 解碼元件

`vendor/heic-decoder.html` 內含第三方元件 libheif-js 1.23.5（LGPL-3.0），未修改。`vendor/THIRD_PARTY_NOTICES.md` 與 `vendor/LICENSE-libheif-js.txt` 是它的聲明與授權全文，請一起保留。

主程式以沙箱框架載入這個頁面，所以它必須和主程式在同一個網站、同一層的 `vendor` 資料夾。GitHub Pages 不需要額外設定。若改放在自己的主機，而主機會送出 `X-Frame-Options: DENY` 或 `frame-ancestors 'none'` 這類禁止內嵌的標頭，解碼頁會被瀏覽器擋下，HEIC 會退回「無法解碼」的提示；改成允許同站內嵌（`SAMEORIGIN`／`'self'`）即可。

維護者可用 `node tools/build_heic_decoder.mjs --check` 核對這個頁面：內含的元件必須是記錄的 SHA-256，膠合程式必須和 `tools/heic_decoder_glue.js` 相同。要換成其他版本的 libheif，見 `vendor/THIRD_PARTY_NOTICES.md` 最後一段。

## 回滾

保留本次更新前的 Git 提交和舊版型 JSON。遇到問題可由你在 GitHub 回復前一個提交，再確認新的 Pages 發布。不要清除瀏覽器資料作為第一步，避免版型遺失。
