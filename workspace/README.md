# 棒球 Bot

以專案根目錄為工作目錄，Python 3.13；目前 Windows 建置使用 Zig 0.13.0。

```powershell
python -m pip install --target .tools ziglang==0.13.0
python workspace/build_native.py
python -m pytest workspace/tests -q
```

Python 透過 ctypes 呼叫原生 C++，無第二套物理；無須 pybind11。
亦提供 CMakeLists.txt，使用支援 `__int128` 的 Clang/GCC 工具鏈。
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
