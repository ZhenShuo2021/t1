# V2PH Downloader
微圖坊下載器

## 特色
📦 開箱即用：不用下載額外依賴   
🌐 跨平台：全平台支援    
🔄 雙引擎：支援 DrissionPage 和 Selenium 兩種自動化選項   
🛠️ 方便：支援多帳號自動登入自動切換   
🔑 安全：使用和 [Psono](https://psono.com/zh-Hant/security) 一樣的後端 PyNaCL 


## 安裝
基本需求為

1. 電腦已安裝 Chrome 瀏覽器
2. Python 版本 > 3.10
3. 使用指令安裝套件

```sh
pip install v2dl
```

## 使用方式
首次執行時需要登入 V2PH 的帳號，有兩種方式

### 帳號管理介面
使用 `v2dl -a` 進入帳號管理介面。
```sh
v2dl -a   # 設定帳號
```

### 手動登入
帳號登入頁面的機器人偵測比較嚴格，可以隨機下載一個相簿，遇到登入頁面後手動登入。


### 嘗試第一次下載
v2dl 支援多種下載方式，可以下載單一相簿，也可以下載相簿列表，也支援從相簿中間開始下載，以及讀取文字文件中的所有頁面。

```sh
# 下載單一相簿
v2dl "https://www.v2ph.com/album/Weekly-Young-Jump-2015-No15"

# 下載相簿列表的所有相簿
v2dl "https://www.v2ph.com/category/nogizaka46"

# 下載文字檔中的所有頁面
v2dl -i "/path/to/urls.txt"
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
- -i: 下載目標的 URL 列表文字文件，每行一個 URL。
- -a: 進入帳號管理工具。
- --bot: 選擇自動化工具，drission 比較不會被機器人檢測封鎖。
- --dry-run: 僅進行模擬下載，不會實際下載檔案。
- --chrome-args: 複寫啟動 Chrome 的參數，用於被機器人偵測封鎖時。
- --user-agent: 複寫 user-agent，用於被機器人偵測封鎖時。
- --terminate: 程式結束後是否關閉 Chrome 視窗。
- -q: 安靜模式。
- -v: 偵錯模式。

## 安全性簡介

> 作為好玩的套件，所以會放一些看起來沒用的功能，例如這個安全架構，其實我也只是把文檔看過一遍就拿來用，這個段落都是邊寫邊查（不過有特別選輕量套件，這個才 4MB，常見的 cryptography 25MB）。

密碼儲存使用基於現代密碼學 Networking and Cryptography (NaCl) 的加密套件 PyNaCL，系統採用三層金鑰架構完成縱深防禦：

- 第一層使用作業系統的安全亂數源 os.urandom 生成 32 位元的 encryption_key 和 salt 用以衍生金鑰，衍生金鑰函式 (KDF) 採用最先進的 argon2id 演算法，此演算法結合最先進的 Argon2i 和 Argon2d，能有效防禦 side-channel resistant 和對抗 GPU 暴力破解。

- 中間層使用主金鑰保護非對稱金鑰對，使用 XSalsa20-Poly1305 演算法加上 24-byte nonce 防禦密碼碰撞，XSalsa20 [擴展](https://meebox.io/docs/guide/encryption.html)了 Salsa20，在原本高效、不需要硬體加速的優勢上更進一步強化安全性。Poly1305 確保密碼完整性，防止傳輸過程中被篡改的問題。

- 最外層以 SealBox 實現加密，採用業界標準 Curve25519 演算法提供完美前向保密，Curve25519 只需更短的金鑰就可達到和 RSA 同等的安全強度。

最後將金鑰儲存在設有安全權限管理的資料夾，並將加密材料分開儲存於獨立的 .env 環境中。

## 在腳本中使用

```py
import v2dl
import logging

your_custom_config = {
    "download": {
        "min_scroll_length": 500,
        "max_scroll_length": 1000,
        "min_scroll_step": 150,
        "max_scroll_step": 250,
        "rate_limit": 400,
        "download_dir": "v2dl",
    },
    "paths": {
        "download_log": "downloaded_albums.txt",
        "system_log": "v2dl.log",
    },
    "chrome": {
        "profile_path": "v2dl_chrome_profile",
        "exec_path": {
            "Linux": "/usr/bin/google-chrome",
            "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        },
    },
}

# Initialize
log_level = logging.INFO
logger = logging.getLogger(__name__)
config_manager = v2dl.ConfigManager(your_custom_config)
app_config = config_manager.load()
download_service = v2dl.ThreadingService(logger)

runtime_config = RuntimeConfig(
    url=args.url,
    input_file=args.input_file,
    bot_type=args.bot_type,
    chrome_args=args.chrome_args,
    user_agent=args.user_agent,
    use_chrome_default_profile=args.use_default_chrome_profile,
    terminate=args.terminate,
    download_service=download_service,
    dry_run=args.dry_run,
    logger=logger,
    log_level=log_level,
    no_skip=args.no_skip,
)

# (Optional) setup logging format
v2dl.setup_logging(runtime_config.log_level, log_path=app_config.paths.system_log)

# Instantiate and start scraping
web_bot = v2dl.get_bot(runtime_config, app_config)
scraper = v2dl.ScrapeManager(runtime_config, app_config, web_bot)
scraper.start_scraping()
```

## 補充
1. 換頁或者下載速度太快都可能觸發封鎖，目前的設定已經均衡下載速度和避免封鎖了。
2. 會不會被封鎖也有一部分取決於網路環境，不要開 VPN 下載比較安全。
3. 謹慎使用，不要又把網站搞到關掉了，難得有資源收錄完整的。
