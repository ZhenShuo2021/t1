# V2PH Downloader
微圖坊下載器

## 特色
📦 開箱即用：不用下載 Chrome driver   
🌐 跨平台：全平台支援    
🔄 雙引擎：支援 DrissionPage 和 Selenium 兩種自動化選項   

## 使用方式
### 前置需求
1. 安裝 Chrome 瀏覽器
2. Python 版本 > 3.10

首次執行時需要手動登入網站。在 `.env` 檔案中填入帳號密碼後腳本可以自動登入。
```sh
pip install v2dl
v2dl <url>
```

### 嘗試第一次下載
```sh
# 單一相簿：有村架純《私の好きな町。》
v2dl "https://www.v2ph.com/album/Weekly-Young-Jump-2015-No15"

# 相簿列表：乃木板46
v2dl "https://www.v2ph.com/category/nogizaka46"
```

## 設定
會尋找系統設定目錄中是否存在 `config.yaml` 以及 `.env` 設定檔，兩者格式請參照根目錄的範例。

裡面可以修改捲動長度、捲動步長與速率限制等設定：

- download_dir: 設定下載位置，預設系統下載資料夾。
- download_log: 紀錄已下載的 album 頁面網址，重複的會跳過，該文件預設位於系統設定目錄。
- system_log: 設定程式執行日誌的位置，該文件預設位於系統設定目錄。
- rate_limit: 下載速度限制，預設 400 夠用也不會被封鎖。
- chrome/exec_path: 系統的 Chrome 程式位置。

系統設定目錄位置：
- Windows: `C:\Users\xxx\AppData\v2dl`
- Linux, macOS: `/Users/xxx/.config/v2dl`

### 參數
- url: 下載目標的網址。
- --bot: 選擇自動化工具。drission 比較不會被機器人檢測封鎖。
- --dry-run: 僅進行模擬下載，不會實際下載檔案。
- --terminate: 程式結束後是否關閉 Chrome 視窗。
- -q: 安靜模式。
- -v: 偵錯模式。
- --verbose: 設定日誌顯示等級，數值為 1~5 之間。

## 從原始碼安裝
```sh
git clone -q https://github.com/ZhenShuo2021/V2PH-Downloader  # 或是直接下載 repo
cd V2PH-Downloader                           # 進入資料夾
python -m venv .venv                         # 創建虛擬環境，下一步是進入虛擬環境
source .venv/bin/activate                    # Windows指令: .venv\Scripts\activate
pip install -r requirements.txt              # 安裝依賴套件
```

## 補充
1. 這不是破解腳本，只是下載工具，該有的限制還是有。
2. 換頁或者下載速度太快都可能觸發封鎖，目前的設定已經均衡下載速度和避免封鎖了。
3. 請謹慎使用，不要又把好網站搞到關掉了，難得有資源收錄完整的。
4. 從頁面中間開始下載不會被視作重複下載，以方便補齊缺失檔案。
5. 會不會被封鎖也有一部分取決於網路環境，不要開 VPN 下載比較安全。
