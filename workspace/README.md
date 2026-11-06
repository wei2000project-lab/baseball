# 棒球 Bot

以專案根目錄為工作目錄，Python 3.13；目前 Windows 建置使用 Zig 0.13.0。完整快速開始見根目錄 README。

```powershell
python -m pip install --target .tools ziglang==0.13.0
python workspace/build_native.py
python -m pytest workspace/tests -q
```

Python 透過 ctypes 呼叫原生 C++，無第二套物理；無須 pybind11。
亦提供 CMakeLists.txt，使用支援 `__int128` 的 Clang/GCC 工具鏈。
Python 入口請使用 build_native.py，因為它同時產生／驗證建置指紋。新原生核心輸出到依來源雜湊命名的目錄，不覆寫已載入的 DLL。
各期實際完成狀態、問題與驗收結果見根目錄 PROGRESS.md。

P2 診斷控制器可跑完整上下半局與記錄；打者不揮棒，不代表 P3/P4 的活球與正式 Bot 已完成。

```powershell
python workspace/scripted_match.py --regulation-ticks 1200 --output results/p2-scripted
```

輸出目錄必須為空或不存在。內含完整設定、初始狀態、動作、事件、檢查點與摘要。

P4 正式對戰（Windows）與批次出口：

```powershell
python -m pip install -r workspace/requirements.txt
python workspace/match.py --away bots/base_bot --home bots/base_bot --seed 42 --config workspace/config/default.json --output results/demo-0042
python workspace/acceptance.py --seeds 20 --regulation-ticks 1200 --output results/p4-batch
python workspace/match.py --away bots/examples/minimal.py --home bots/examples/node_passive --seed 9 --output results/replacement
```

預設限時 900 模擬秒；`--regulation-ticks` 可縮短驗收場次。輸出 `completed` 才是正式終局，`aborted` 的 winner 為 null。退出碼 0=完成、2=中止、1=啟動或輸出錯誤。程序被外部終止時未封存記錄仍為 recording，讀取時應識別 incomplete。

一隊一 Bot 程序，以 UTF-8 JSONL 互通。資料夾可放 `bot.py`，或 `bot.json` 的 command 字串陣列（無 shell）；亦可直接傳 `.py`／可執行檔。JavaScript 範例需要 Node。兩隊先收到同一時間快照，收齊回覆才套用；觀察不提供引擎 RNG。

正式模式使用 Windows Job Object：worker 與 Bot 合計 256 MiB committed memory、最多兩個程序（可信任 worker + 一個 Bot）、關閉即終止程序樹；每次回覆 watchdog 2 秒、stdout 每行上限 64 KiB、stderr 上限 1 MiB。未能安裝限制時直接中止。這是程序與資源隔離，不是檔案／網路權限沙箱，只執行可信任的 Bot。[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。

每份記錄包含設定、名單／打序／站位、來源與原生建置指紋、Bot 程式雜湊、原始回覆／拒絕原因與接受意圖。DLL 與建置來源不符時要求重新建置，沒有 Python 物理備援。

P5 無 Bot 重算、精確定位與分塊影格：

```powershell
python workspace/replay.py verify --input results/demo-0042 --from-start
python workspace/replay.py seek --input results/demo-0042 --tick 720
python workspace/replay.py frames --input results/demo-0042 --output results/demo-0042/cache/frames
python workspace/verify_acceptance.py --input results/p4-final-batch --report workspace/tests/reports/p5-replay-acceptance.json
python workspace/determinism_acceptance.py --repeats 10 --output results/p5-d2 --report workspace/tests/reports/p5-d2-acceptance.json
```

verify 預設從頭重算；`--checkpoint <索引>` 只會回報 verified_prefix。seek 由較早 checkpoint 還原後推進，不會啟動 Bot；單獨 seek 回報 unverified，不能代替整場驗證。未封存記錄只驗證到最後完整 checkpoint，回報 incomplete／verified_prefix。完整性不符為 mismatch，未知規則或建置指紋為 unsupported_version；退出碼 2。

影格以每 4 ticks 與重要事件邊界輸出，每塊最多 600 影格；快取包含來源雜湊與驗證報告，過期／損壞的 chunk 自動重建。刪除整個 cache 也能從原記錄重算。`--progress` 可輸出 JSONL 進度。

P5 規則版本 `1.0.0-dev.P5` 修正已啟動但窗口結束的揮空仍須計好球；原 `1.0.0-dev.P4` 保留舊判定分支，指定的 P4 建置指紋經完整回放驗收後列入相容表，無近似套用新判決。原生物理／場地版本仍為 P4。被拒絕的有限小數輸入只保留在稽核欄位，不進入權威數值；NaN、Infinity、非法 Unicode 在 JSON 邊界拒絕。

P6 Electron 回放（Node 24、Electron 45.2.3）：

```powershell
npm ci --prefix workspace
python workspace/viewer.py --record results/demo-0042
# 或在 workspace 執行 npm run viewer，從畫面選取比賽目錄。
```

若 Node 沒有附 npm，可在專案根目錄執行 `python workspace/bootstrap_node.py`，再以 `node .tools/npm-runtime/package/bin/npm-cli.js ci --prefix workspace` 安裝鎖定依賴。postinstall 會執行固定版本 Electron 的官方 runtime 安裝器，快取留在 workspace/build。

介面支援播放／暫停、0.25×–8×、逐 tick、上一／下一球、跳局、時間軸、精確 tick 定位、事件與球員檢視。球高、陰影、持球權、壘位與待確認得分來自重算資料；暫停或定位後由背景程序回傳精確狀態雜湊。視覺偏移、比例與邏輯區域開關均不回寫引擎。未提供 Blender 模型時使用基本幾何。

無桌面控制的背景驗收：

```powershell
node --test workspace/tests/viewer.test.mjs
python workspace/ui_acceptance.py --input results/demo-0042
```

驗收只建立不可見的離屏視窗，使用獨立 userData 與記錄副本，不注入鍵盤滑鼠、不切換現有視窗。報告在 workspace/tests/reports/p6-ui.json，1080p 圖片在 workspace/build/ui-acceptance。原記錄檔案會比對確認未變更。

P7 預設 rules/schema 與 map 版本為 `1.0.0-dev.P7`，球物理仍是 P4。普通守備移動現在依加速度與距離減速，只有跑者目標壘保留立即停下例外；目標及實際位置受邏輯牆與矩形範圍限制。P4/P5 舊記錄依原地圖函式重算，詳見 VERSIONS.md。

## 常見問題

| 訊息 | 處理方式 |
| --- | --- |
| native_missing／metadata_missing／stale_or_modified | 執行 `python workspace/build_native.py`。原本已開啟的舊版 viewer 請自行關閉後重開；建置不會操作你的視窗。 |
| 找不到 compiler | 安裝 requirements-dev.txt 的 Zig 0.13.0，或 `--compiler` 指定 zig.exe。不可改成 Python 物理備援。 |
| 找不到 npm | 使用 bootstrap_node.py 的固定版本本機 npm；不要修改全域 PATH。 |
| Electron 缺少 binary | 重新 `npm ci --prefix workspace`；postinstall 使用官方安裝器與固定版本。首次需下載，之後可離線。 |
| output_not_empty | 指定新目錄。程式不會覆寫既有比賽。 |
| bot process／watchdog／memory fault | 查看 results 該場 diagnostics 與 summary。正式模式為 aborted、winner=null；不會自動替 Bot 投球或選策略。 |
| unsupported_version | 使用已支援的建置或對應 Git tag；不能以最新規則近似冒充成功。 |
| mismatch／file_integrity | 查看首個差異欄位或檔案；不可把結果標為 verified_full。 |
| incomplete／verified_prefix | 記錄未封存，只驗到最後完整 checkpoint；不是完整正式賽。 |
| 快取損壞 | 重新載入重建，或自行刪除該場 cache 後再 frames；原始記錄不能刪。 |
| 模型或 profile 無效 | 自動使用基本幾何，不影響對戰或重算。 |

進階建置可 `--cache-root` 明確指定共享 compiler cache。`python workspace/cleanroom_acceptance.py` 複製 Git 可見來源至 workspace/build 的隔離目錄，重用已記錄工具鏈，執行建置／離線依賴安裝／對戰／驗證；不接觸桌面控制。測試結果與已知範圍見 ACCEPTANCE.md。
