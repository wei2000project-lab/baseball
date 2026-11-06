# 執行與故障排查（2.1.0）

以專案根目錄為工作目錄；快速開始見根 README。

```powershell
python workspace/build_native.py
python workspace/match.py --away bots/base_bot --home bots/base_bot --seed 42 --regulation-ticks 1200 --output results/new-v2
python workspace/replay.py verify --input results/new-v2
python workspace/replay.py seek --input results/new-v2 --tick 720
python workspace/viewer.py --record results/new-v2
```

預設 108000 ticks（900 模擬秒），到時完成上下半局。退出碼：0 完成、2 中止、1 啟動／輸出錯誤。aborted 的 winner 為 null。

每場輸出 match.txt。M 設定與名單、B Bot 資訊、T 變動欄位、E 重要事件、END 摘要與雜湊。a1–a9 為客隊，h1–h9 為主隊，bx/by/bz 為球位置。Q32.32 整數除以 4294967296 得公尺，保留全部精度。未變座標不重複寫，完全靜止的 tick 沒有 T 行。

回放直接讀差分，不啟動 Bot 或原生物理。verified_record 驗證 SHA-256、摘要與終局觀看狀態；不是簽章、反作弊或逐事件重算。未封存為 incomplete，僅預覽完整寫入的行；損壞為 mismatch，舊 JSON／未知版本為 unsupported_version。--input 也接受 match.txt 路徑。

```powershell
python workspace/replay.py frames --input results/new-v2 --output results/new-v2/cache/frames
python workspace/determinism_acceptance.py --repeats 10 --output results/repeat-v2 --report workspace/tests/reports/v2-determinism.json
```

影格 bb-frames-v2：每 4 ticks 加重要事件，每塊最多 600 格；損壞或刪除可重建。精確定位從較早記憶體索引套用差分。--from-start 保留為 CLI 相容參數，不表示物理重算；TXT 沒有 checkpoint suffix 模式。

一隊一個 JSONL Bot 程序，兩隊先取得同 tick 快照，收齊回覆才套用。觀察不提供 RNG。每 tick 有一次決策機會（8.33 ms 模擬時間），不是要求程序在 8.33 ms 牆鐘內回覆。移動與接球意圖持續生效，無須每 tick 重送相同動作。

支援 `bot.cpp` 自動編譯（C++17），或直接傳 `.cpp`／`.exe`；資料夾依 `bot.json` → `bot.cpp` → `bot.py` 選擇。編譯在程序 watchdog 開始前完成，快取與錯誤 log 在 workspace/build/cpp-bots，原始碼／本地標頭變更會重建。`BASEBALL_BOT_CXX` 可指定 Zig／Clang／GCC 執行檔；亦可單獨執行 `python workspace/build_bot.py bots/my_bot/bot.cpp`。參考 bots/BOT_REFERENCE.md 與無策略 cpp_passive 範例。

Windows Job Object：worker 與 Bot 合計 256 MiB、2 程序、watchdog 2 秒、stdout 每行 64 KiB、stderr 1 MiB。這是資源限制，請執行可信任 Bot。診斷移至忽略的 workspace/build/runlogs/<輸出路徑雜湊>/。

| 訊息 | 處理 |
| --- | --- |
| native_missing／stale_or_modified | 執行 build_native.py，舊 viewer 請自行重開。 |
| compiler 缺少 | 安裝 requirements-dev.txt 或 --compiler 指定 zig.exe。 |
| npm 缺少 | bootstrap_node.py，再使用本機 npm-cli.js。 |
| Electron binary 缺少 | npm ci --prefix workspace 或本機 npm 安裝命令。 |
| output_not_empty | 使用新目錄，不會覆寫比賽。 |
| Bot crash／watchdog／memory fault | 看摘要 reason 與 build/runlogs；中止不算正式勝負。 |
| unsupported_version | 舊記錄使用原 Git tag，新版只接受 2.1.0 TXT。 |
| mismatch／file_integrity | 記錄損壞，不可宣稱驗證通過。 |
| incomplete | 無完整 END，僅可預覽已有部分。 |
| 模型 profile 無效 | 使用基本幾何，不影響對戰。 |

cleanroom_acceptance.py 可隔離來源與輸出驗收；ui_acceptance.py 使用自己的隱藏離屏 Electron，不操作桌面。

推進統計使用 `balance_batch.py --controller advancement --n 40 --label local --output results/advance.json`。多參數掃描使用 `scan_advancement.py --workers 3 --apply`，中斷後同命令可讀取相同來源／設定／seed 的快取報告；無達標組時退出碼 2，不採用未達標參數。完整定義、固定控制器與目標見根 BALANCE.md。
