# 棒球 Bot 自動對戰遊戲

**接手狀態：目前主要對戰仍有無法完賽、雙方未得分的未解問題。** 請先讀 [HANDOFF.md](HANDOFF.md)；功能測試與速度改善不代表這些缺陷已修復。

2.1.0：Python 協調規則、C++ Q32.32 物理、Electron 離線回放。每場只輸出 `match.txt`，逐 tick 儲存變動座標與狀態，回放直接讀取差分。逐項平衡統計見 [BALANCE.md](BALANCE.md)。

2.1.0 目前為守備時間成本與推進量測的**實驗版**；功能測試通過，平衡掃描尚未找到同時達標組。完整數據與未完成項見 BALANCE.md／PROGRESS.md。

對戰已加入[效能改善](PERFORMANCE.md)：基準短賽中位32.5秒→12.8秒，TXT結果相同；原啟動器下一場直接使用。

## 啟動對戰與回放

也可直接雙擊 **[launcher/啟動遊戲.bat](launcher/啟動遊戲.bat)**，在已編譯的原生視窗選主客隊、輸出位置後開始，完成可直接看回放。詳見 [啟動器說明](launcher/README.md)。

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
python workspace/balance_batch.py --controller advancement --workers 3 --n 40 --label local --check-targets --output results/balance-local.json
python workspace/scan_advancement.py --workers 3 --apply
python -m pytest workspace/tests -q
node --test workspace/tests/viewer.test.mjs
python workspace/ui_acceptance.py --input $matchDir --report workspace/tests/reports/v2-ui.json
```

UI 驗收只建立自己的隱藏離屏視窗，不切換視窗或注入鍵盤滑鼠。推進批次使用專用固定跑壘測試控制器，正式 Bot 不變；掃描只採用四項目標全過的參數，無達標組時回傳 exit code 2。平衡批次使用真實引擎與 Bot，但省略 IPC／記錄 I/O，不代表正式對戰效能。

- [PROGRESS.md](PROGRESS.md)：進度、已過測試與已知問題。
- [BALANCE.md](BALANCE.md)：改前、a–f、調參與目標。
- [使用與故障排查](workspace/README.md)、[數值公式](workspace/PHYSICS.md)、[版本](workspace/VERSIONS.md)、[驗收](workspace/ACCEPTANCE.md)。
- [Bot 協定](bots/protocol/README.md)：更換 --away／--home 路徑即可替換 Bot。
- [AI 開發 Bot 參考](bots/BOT_REFERENCE.md)：基本規則、雙方座標／固定 ID、JSONL 與動作欄位，沒有策略。`--away bots/my_bot/bot.cpp` 可自動編譯 C++17 後對戰；無策略範例在 `bots/examples/cpp_passive/`。

決策機會為每 tick，120 Hz 下為 8.33 ms 模擬時間；Bot 故障 watchdog 另為 2 秒牆鐘時間。舊 2.0.0／P0–P7 記錄在新版回報 unsupported_version，請使用原 Git tag 查看。verified_record 表示 TXT 完整性通過，不宣稱重算物理。

results、建置產物、node_modules、工具鏈與快取均被 Git 忽略；必要報告與壓縮範例另版控。程式不自動推送 remote。
