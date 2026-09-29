# Security Policy / 安全回報

本文件說明如何回報「沂恩對比圖管理器」的安全問題，**不是安全認證，也不是滲透測試報告**。

## 回報範圍

本次交付與檢查的程式版本為 **v5.9**，入口為 `index.html`。較舊版本建議先更新，再確認問題是否仍存在。實際線上站點的版本，請看工具左上角；此文件不能證明維護者已完成部署。

可回報影響本工具的程式碼注入、未預期資料外傳、輸入驗證錯誤及可重現的資源耗用問題。一般排版／使用問題可在 Issues 討論；不要在公開 Issue 上貼安全漏洞細節。

## 私下回報

優先使用 [GitHub 私下漏洞回報](https://github.com/brain113tw/en-laundry-compare-tool/security/advisories/new)。此入口**需要維護者先啟用 Private vulnerability reporting**，不是放入本檔案就會自動開啟。

在專案的 **Security and quality → Advisories** 有「Report a vulnerability」時，使用該表單。如目前看不到或無法開啟，請先用不含漏洞細節的 Issue 請維護者提供私下聯絡管道；等待管道確認後再傳送重現資料。不要自行猜測安全信箱，也不要在公開留言附攻擊檔。

## 回報內容

請提供程式版本、瀏覽器／作業系統、最小可重現步驟、預期結果與實際結果、影響範圍，以及只含示意內容的測試檔。設定 JSON、檔名、截圖及 ZIP 清單也可能帶有個資，送出前請清除客戶姓名、電話、地址、訂單與 Token。

請只在自有或已獲明確授權的本機副本上測試；不要讓他人服務中斷或使用真實客戶資料。

本專案不在此承諾固定回覆期限、修復期限或漏洞獎勵。公開細節前，請先與維護者協調。

## 使用者保護措施

請從維護者提供的來源取得程式；使用更新的瀏覽器；重要版型匯出 JSON 備份；不要匯入不明來源設定檔或可疑影像。輸出檔與批次清單由使用者自行決定分享對象。

## 維護者啟用步驟

`Settings → Advanced Security → Private vulnerability reporting → Enable`，再回 `Security and quality → Advisories` 檢查回報按鈕。

官方說明：[設定私下漏洞回報](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)；[新增 SECURITY.md](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/add-security-policy)。
