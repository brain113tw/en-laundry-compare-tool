# GitHub 更新說明｜v5.9

此交付包只在本機產生，**沒有代你修改 GitHub、正式洗衣網站或 Pages 設定**。

## 更新前

先在目前工具「05 我的慣用版型」按「匯出慣用版型」，也可另按「匯出設定」。將備份留在自己的電腦，不要連同客戶照片上傳 repo。先記下目前 GitHub 的 commit，以便回退。未輸出的照片／批次工作不會隨更新保存。

## 上傳到現有 repo

開啟 [en-laundry-compare-tool](https://github.com/brain113tw/en-laundry-compare-tool)，按 **Add file → Upload files**。把 ZIP 解壓縮後的**資料夾內全部檔案與子資料夾**拖入；不要只上傳 ZIP，也不要把整個最外層目錄多包一層。

根目錄應能直接看到 `index.html`、`README.md`、`SECURITY.md`、`en_compare_manager_v5_8.html`、`docs/`、`tools/`、`tests/`、`.nojekyll`、`.gitignore`、`.gitattributes`。更新同名檔案；舊入口 `en_compare_manager_v5_8.html` 也要覆蓋，這份新版只負責導向 `index.html`。不要保留它原本的舊程式。

Commit message 可用：

```text
Update to v5.9: validated imports, CSP hash, documentation and footer
```

個人專案可檢查差異後直接 commit 到 `main`；有協作審查規範時，依規範建立分支及 Pull Request。

`.gitignore` 是給 Git 工作流程的提醒，不是隱私防火牆，也不會阻止你在 GitHub 網頁手動選入敏感檔，更不會清除已提交的歷史。上傳前仍要逐項確認。

## Pages 設定不用重做

你先前使用的 `Settings → Pages → Deploy from a branch → main → / (root)` 可維持。從指定分支發布的 Pages，會在該來源更新後觸發發布。看 Actions／Deployments 是否成功，再開 [工具首頁](https://brain113tw.github.io/en-laundry-compare-tool/) 核對左上角 **v5.9**。若仍是舊版，先重新整理及查看部署狀態，不要改成付費方案。[GitHub 官方文件](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

根目錄的 `.nojekyll` 用於直接發布靜態檔，避免此單檔工具被當成 Jekyll 模板處理。檔案可能在部分介面被隱藏，請確認也有上傳。

## 你仍需在 GitHub 檢查的事項

**私下安全回報：**`Settings → Advanced Security → Private vulnerability reporting → Enable`。加入 SECURITY.md 不會自動啟用此功能。[官方步驟](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)

**機密掃描與推送保護：**公開 repo 的 secret scanning 由 GitHub 自動提供；仍需查看警示、通知，以及你帳號目前可設定的 Push protection。文件不能代表已替你開啟。[機密掃描](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/detect-secret-leaks/enable-secret-scanning)／[Push protection](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/prevent-future-leaks/enable-push-protection)

**維護權限：**保持 GitHub 帳號安全，只授權需要的人。公開連結不是管理權限；本次沒有變更其他 Private repo。

## 更新後驗收

確認首頁為 v5.9；加入兩張非客戶示意圖；洗前洗後順序正確；店名與底條能分開拖；輸出 WEBP／PNG／SVG 可開啟；左側空白區可拖入；版型可儲存並匯出 JSON；匯入舊版 JSON 後核對尺寸、文字及日期；開 README 的截圖、使用說明、Star 及正式網站連結。

本機和 HTTPS 入口可能使用不同儲存空間，不能假設舊版型自動帶過來。必要時匯入更新前的 JSON 備份。[localStorage 行為](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage)

## 修改程式碼時的 CSP

`index.html` 採 script SHA-256 白名單。任何 JavaScript 字元變更後，執行 `node tools/update_csp.mjs`，再執行 `node tools/update_csp.mjs --check`。只替換 JS 但忘記同步 hash，瀏覽器會阻止腳本執行；不要用改回 `unsafe-inline` 掩蓋問題。

`.gitattributes` 設為 LF，避免不同換行造成維護混亂。雜湊只是指定可執行腳本，無法阻擋已取得 repo 寫入權的人同時修改程式與 CSP。

## 回退

可從 GitHub commit 歷史恢復更新前檔案，再等待 Pages 發布。回退程式不等於恢復瀏覽器版型，仍需 JSON 備份。回退後舊版輸入驗證限制也會回來，請不要把它當成安全問題的永久解法。
