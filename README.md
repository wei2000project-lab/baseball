# 棒球 Bot 自動對戰遊戲

2.0.0：Python 協調規則、C++ Q32.32 物理、Electron 離線回放。每場只輸出 `match.txt`，逐 tick 儲存變動座標與狀態，回放直接讀取差分。逐項平衡統計見 [BALANCE.md](BALANCE.md)。

## 啟動對戰與回放

以下 PowerShell 命令不需要桌面控制權限。viewer 由你執行後才會開啟視窗。

```powershell
Set-Location 'C:\Users\weiwei\Desktop\ai_project\baseball'
$matchDir = 'results/match-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python workspace/match.py --away bots/base_bot --home bots/base_bot --seed 42 --regulation-ticks 1200 --output $matchDir
python workspace/replay.py verify --input $matchDir
python workspace/viewer.py --record $matchDir
```

1200 ticks 是短賽，仍完成上下半局。完整預設賽移除 `--regulation-ticks 1200`，採 15 分鐘模擬時間；每半局最多 10 分或 15 打席。輸出目錄必須為空或不存在。

附帶新版 TXT 範例：

```powershell
python workspace/unpack_demo.py --output results/offline-v2
python workspace/viewer.py --record results/offline-v2
```

## 建置

已測 Windows x64、Python 3.13、Node 24、Zig 0.13.0、Electron 45.2.3。首次安裝需要網路，之後可離線。

```powershell
python -m pip install -r workspace/requirements.txt -r workspace/requirements-dev.txt
python workspace/build_native.py
npm ci --prefix workspace
```

若 Node 未附 npm：

```powershell
python workspace/bootstrap_node.py
node .tools/npm-runtime/package/bin/npm-cli.js ci --prefix workspace
```

編譯使用新的來源雜湊目錄，不覆寫已載入的 DLL。更新後請自行重新啟動舊 viewer。

## 驗證與接續

```powershell
python workspace/balance_batch.py --n 40 --label local --check-targets --output results/balance-local.json
python -m pytest workspace/tests -q
node --test workspace/tests/viewer.test.mjs
python workspace/ui_acceptance.py --input $matchDir --report workspace/tests/reports/v2-ui.json
```

UI 驗收只建立自己的隱藏離屏視窗，不切換視窗或注入鍵盤滑鼠。平衡批次使用真實引擎與 Bot，但省略 IPC／記錄 I/O，不代表正式對戰效能。

- [PROGRESS.md](PROGRESS.md)：進度、已過測試與已知問題。
- [BALANCE.md](BALANCE.md)：改前、a–f、調參與目標。
- [使用與故障排查](workspace/README.md)、[數值公式](workspace/PHYSICS.md)、[版本](workspace/VERSIONS.md)、[驗收](workspace/ACCEPTANCE.md)。
- [Bot 協定](bots/protocol/README.md)：更換 --away／--home 路徑即可替換 Bot。

決策機會為每 tick，120 Hz 下為 8.33 ms 模擬時間；Bot 故障 watchdog 另為 2 秒牆鐘時間。舊 P0–P7 記錄在新版回報 unsupported_version，請使用原 Git tag 查看。verified_record 表示 TXT 完整性通過，不宣稱重算物理。

results、建置產物、node_modules、工具鏈與快取均被 Git 忽略；必要報告與壓縮範例另版控。程式不自動推送 remote。
