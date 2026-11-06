# 開發進度

目前階段：**P0–P7 已封存；2.0.0 平衡與 TXT 差分改版已完成並通過出口驗證**。本次封存 tag：`balance-v2.0.0`。P0–P7 以下內容保留為歷史；新版請看本檔 2.0.0 章節、BALANCE.md 與 workspace/ACCEPTANCE.md。

目前操作限制：使用者正在使用電腦；不得要求電腦控制權限或操作／切換使用者視窗。後續改用 CLI、隱藏離屏 renderer、記錄副本與背景測試驗收。

依序 P0 → P7；每期先通過該期全部出口測試，再提交 `P<n>: 說明` 並建立 `p<n>` tag。未通過不可進下一期。

| 階段 | 狀態 | 出口驗證 |
| --- | --- | --- |
| P0 專案骨架與資料合約 | 通過（tag: `p0`） | 專案內 Zig 0.13.0 原生建置；10 項 pytest 通過；compileall 通過 |
| P1 物理與場地核心 | 通過（tag: `p1`） | 原生重建；P0/P1 共 24 項測試通過；100 ticks golden 軌跡重算 10 次一致 |
| P2 打席與半局 | 通過（tag: `p2`） | T01–T07、T18；全套 39 tests；診斷控制器完成上下半局並封存記錄 |
| P3 活球與限時規則 | 通過（tag: `p3`） | T08–T22、限時／交換邊界、回壘 checkpoint；全套 68 tests |
| P4 Bot 與端到端對戰 | 通過（tag: `p4`） | 78 tests；20 seeds × 2 輪全 completed、動作／事件／checkpoint／終局逐檔 byte 一致；預設 15 分鐘對戰完成 |
| P5 重算與驗證器 | 通過（tag: `p5`） | 全套 96 tests；D1/D2 各 10 次、20 舊版完整驗證、100 隨機 seek、全部 checkpoint 恢復、篡改與 incomplete |
| P6 Electron 回放 | 通過（tag: `p6`） | 98 Python tests、5 JS tests、20 項真實 Electron 離屏整合檢查、1080p artifact |
| P7 整合封存 | 通過（tag: `p7`） | 107 Python、7 JS、20 新版背景 UI 檢查；新版 20 seeds／10 次 D2、舊版回歸、隔離建置與離線範例 |

## 已知問題與接續

- 本機有 Python 3.13.9、Node 24.22.1、Git 2.54.0；PATH 無 CMake、npm。C++ 由專案內 `.tools/ziglang/zig.exe` 建置；不需要 CMake。
- 沙箱內 Zig 建快取曾失敗；使用已授權的原生建置命令成功，暫存與快取皆留在 `workspace/build/`。
- P0 驗收：`python workspace/build_native.py`；`python -m pytest workspace/tests/test_p0.py -q` → **10 passed**；`python -m compileall -q workspace bots`。
- 已驗證 Q32.32 綁定、整數舍入、RNG golden vector、嚴格 JSON／Schema、非法設定拒絕、狀態 snapshot/restore 雜湊一致、觀察副本無副作用、最小 Bot 握手。
- P1 驗收：`python workspace/build_native.py`；`python -m pytest workspace/tests -q` → **24 passed**；compileall 通過。
- P1 涵蓋自由落體、單次重力、地面反彈、精確滾停、牆反射／空中出場、AABB 穿越、移動接球區、切線、固定 ID 排序、四壘觸碰急停、通過非目標壘、加速度／速度上限、方向 clamp、CORDIC、溢位拒絕。
- 原生接觸量化與責任界線記錄在 `workspace/PHYSICS.md`；固定數值／場地版本提升為 `1.0.0-dev.P1`，舊版本使用 `p0` checkout，不以新核心冒充舊結果。
- 狀態納入設定雜湊與規則／物理／場地版本，restore 拒絕設定不符。
- P2 驗收：`python -m pytest workspace/tests -q` → **39 passed**；compileall 通過；原生重建通過。
- `python workspace/scripted_match.py --regulation-ticks 1200 --output results/p2-scripted` → completed、0:0、雙方各 1 半局、7555 ticks；最終雜湊 `f6a48e31f190d8c5881367d8de1e25f7ed14088e77da62f56b306394f68904cf`。
- T01–T07/T18 包括圓角好球區擦球、兩好球界外、揮棒窗、單次接觸、精確投球違規時點、觸身優先序、滾地公平定案與越壘後維持界內、保送強迫進壘、打序。
- 補充規則已涵蓋半局得 10 分上限、投捕／跑者重置；15 打席上限分支已實作，P3 再擴充活球相關驗收。
- Recorder 從 P2 起封存自含設定／初始狀態／動作／事件／checkpoint／summary 與檔案雜湊；測試已以相同引擎從初始狀態重放控制器輸入，逐事件與終局 hash 一致。
- P3 驗收：原生重建；`python -m pytest workspace/tests -q` → **68 passed**；compileall 通過。T08–T22、投球重置、半局 10 分／15 打席上限、正常完成優先於保護上限皆通過。
- 已加入接殺／拾球／傳球、封殺／觸殺、強迫鏈依賴、回壘申訴、跑者超越／壘位權、第三出局候選得分結算、全壘打／二壘授壘、合法停壘後收球與活球收斂。
- 限時測試涵蓋上下半局打席、上下交換與下半轉下一局、交換結束前／同／後 tick、目標局不漂移、雙方完成相同半局數、正常完成優先於 max_ticks。無法收斂時明確 aborted／winner=null。
- 修正觸壘時間向下量化後的停止位置，確保位於觸碰區內；方向正規化保守限制速度；在 tick 中途進入準備階段時，以接下來的 tick 邊界作為完整準備計時起點。規則／物理／場地版本提升 `1.0.0-dev.P3`，P2 舊結果用 p2 checkout。
- 接殺後欠回壘場景 checkpoint 恢復並繼續 200 ticks，逐事件／狀態雜湊一致。
- P4 驗收：`python -m pytest workspace/tests -q` → **78 passed**；compileall／Node syntax check 通過。20 seeds（0–19、regulation_ticks=1200）重跑兩輪，共 40 場全 completed；各 seed 的 initial/actions/events/checkpoints/summary 逐 byte 一致。
- 批次記錄：`results/p4-batch`（首次）、`results/p4-final-batch`（完整封存 metadata）。完整報告版本化於 `workspace/tests/reports/p4-acceptance.json`；結果本體維持 Git 忽略。
- 預設賽制：`python workspace/match.py --away bots/base_bot --home bots/base_bot --seed 42 --output results/p4-default-42` → 50:45、雙方各 5 半局、132898 ticks、finish_after_inning=5。實際 68.549 秒，含 Bot／記錄約 16.16 倍模擬實時。
- 參考機：Intel Core Ultra 5 225、33787138048 bytes RAM、Windows、Python 3.13.9、Zig 0.13.0。
- 已實測 Job Object 256 MiB committed-memory 限制（300 MiB 配置引發 MemoryError），含 worker 的程序數限制 2、2 秒 watchdog、超長 stdout／stale ID／非法 JSON／Bot crash 與中止封存；Python 被動 Bot vs JavaScript 被動 Bot 可完整對戰，不改規則。
- 已修正出手者殘留 catch 意圖導致原地接回傳球；納入回歸測試。規則／合約版本提升為 `1.0.0-dev.P4`。DLL 建置指紋會檢查來源及二進位是否過期。
- 已知限制：Job Object 是程序／資源隔離，不是檔案或網路安全沙箱；只執行信任的 Bot。非 Windows 尚不支援正式 BotHost。第一份探索記錄 `results/p4-smoke-42` 因上述已修正問題而手動中斷，維持 incomplete，不納入驗收。
- 下一期 P6：Electron 回放介面、播放／倍速／單步／精確 seek、重要事件與視覺偏移。最終整合尚未開始，不宣稱首版已完成。

## P5 驗收紀錄

- 最終 `python -m pytest workspace/tests -q` → **96 passed in 15.93s**；compileall 通過。

- `replay.py verify/seek/frames` 已完成，無 Bot 啟動；headers／檔案索引／版本／Schema／觀察／意圖／逐事件／checkpoint／summary 均校驗。差異回報首個 tick、seq、欄位與預期／實際值。
- 20 個 P4 基準 seed 與預設 132898-tick 對戰，於 P5 的版本相容路徑重新完整驗證皆為 verified_full；報告 `workspace/tests/reports/p5-replay-acceptance.json`。
- 同一完整輸入重算 10 次；每個 checkpoint 恢復至終局；額外涵蓋活躍揮棒窗、持球／半局交換、欠回壘及回壘中狀態。
- 相同 seed 42 的基本 Bot 重賽 **10 次**，accepted intents／逐事件／終局雜湊一致；首份亦完整重算。見 `workspace/tests/reports/p5-d2-acceptance.json`。
- 100+ 個隨機 tick 定位與順序推進一致。實際基準賽 100 次 hot seek：中位 48 ms、P95 175 ms、最長 241 ms；索引首次載入 572 ms。見 `workspace/tests/reports/p5-seek-performance.json`。
- 篡改 accepted intent、事件、checkpoint（含重算封存雜湊）、截斷、未知版本、非法 Unicode、有限小數拒絕稽核、程序故障同 tick 終局、incomplete 前綴、映射／回覆順序測試通過。分塊影格每塊最多 600 格，損壞或刪除 chunk 可重建。
- 發現並版本化修正過早揮棒的窗口結束後仍應計揮空好球；新 rules/schema 為 `1.0.0-dev.P5`，物理／場地維持 P4，明確保留 P4 舊規則與指定建置相容指紋，未悄改舊回放。
- 跨平台 D3 尚未宣告。P0–P3 開發記錄須使用對應 Git tag；目前驗證器支援已驗收的 P4 與 P5。
- `results/`、工具鏈、建置產物、node_modules 與快取不納入 Git。

## P6 驗收紀錄

- `python -m pytest workspace/tests -q` → **98 passed in 17.39s**；`node --test workspace/tests/viewer.test.mjs` → **5 passed**；main/preload/renderer JS 語法檢查通過。
- `python workspace/ui_acceptance.py --input results/p4-final-batch/seed-00` → **20 checks passed**。使用獨立隱藏離屏 Electron，不顯示視窗、不取得桌面控制，原始記錄逐檔雜湊未變更。
- 真實 renderer 覆蓋完整驗證、逐 tick 前後、上一／下一球、跳半局、0.25×／8× 播放後回到相同狀態雜湊、視覺偏移／比例不影響權威狀態、球高／比分／持球／事件同步、終局一致、HTML 稽核文字不執行、取消重算並清除驗證宣告。
- 測試輸出 1920×1080 離屏影像並檢查佈局；8× 播放時量得 **60 FPS**（背景測試，不宣稱所有前景硬體皆達此值）。報告 `workspace/tests/reports/p6-ui.json`。
- Electron 45.2.3、npm 12.2.2 與 Node 24 工具鏈已記錄；package-lock 鎖定依賴。renderer context isolation／sandbox 開啟、Node integration 關閉，IPC 僅允許固定操作，Python 以參數陣列啟動。
- 影格 LRU 上限 3 chunks；精確 seek 由持續存活的 Python worker 重算。修正取消重算後的過期驗證標示與舊請求競態。
- 已知限制：目前為基本幾何與視覺 profile；GLB／Blender 美術製作仍依規格保留到後續。作業系統與瀏覽器前景 FPS 尚無額外桌面控制驗收，尊重使用者正在使用電腦的限制。
- 下一期 P7：安裝與故障排查文件、完整需求追蹤、範例記錄、visual profile Schema、隔離來源建置與端到端封存檢查。

## P7 最終封存

- 最終 `python -m pytest workspace/tests -q` → **107 passed in 27.93s**；Node viewer suite → **7 passed**；compileall／git diff --check 通過。
- 整合補測修正普通守備員的目標急停、牆外目標與初始牆外站位。新規則／地圖 `1.0.0-dev.P7`，球物理仍 P4；保留原 P4/P5 規則與地圖函式及明確建置相容表。
- 新版 seeds 0–19 **20/20 completed、0 aborted**，20 份全部逐事件／checkpoint／summary **verified_full**。相同 seed 42 **10 次**外部 Bot 重賽的 accepted intents／事件／終局 hash 完全相同。
- 20 份 P4 基準記錄再次完整驗證；版本化 P5 範例亦重算一致。未知未來版在套用現行 payload Schema 前回報 unsupported_version。
- 新版預設賽為 36:36、雙方各 6 半局、121419 ticks，正常平手；實際 61.031 秒，含 Bot／記錄約 **16.58×** 模擬實時。
- 新版 100 次 hot seek：中位 **44 ms**、P95 **187 ms**、最長 **228 ms**；首次索引 734 ms。新版隱藏 renderer **20 checks passed**、1920×1080、8× 播放 **59 FPS**（目標 60），原始記錄雜湊未變更。
- 隔離來源／輸出成功執行原生建置、離線 npm ci、Python/JS 測試、完整對戰、從頭驗證、影格產生、範例解壓與重算等 **9 個命令**；只重用明確記錄的工具鏈與套件快取，未依賴舊專案 DLL。
- 已提供根 README、ACCEPTANCE.md、VERSIONS.md、故障排查、完整 Bot message Schema、visual profile Schema 與載入驗證、壓縮離線參考記錄（約 807 KiB）與安全解壓工具。範例不包含 Bot、模型或影格 cache。
- Bot init 現在傳遞公開 field/physics/rules capabilities，另一語言可遵循同一合約。核心與舊版物理未複製為另一套 Python 實作。
- 原生輸出採來源雜湊目錄；未關閉或操作任何使用者視窗。此次續作完全以 CLI 與獨立隱藏離屏程式驗收，沒有要求桌面控制權限。
- 證據彙整：`workspace/tests/reports/p7-release.json`；詳細報告見 `workspace/ACCEPTANCE.md`。

## 2.0.0 平衡與 TXT 改版（完成）

- a–f 均按順序實作並保存固定 seeds 測量。修正界外飛球接殺統計分母後，再用各期保存參數逐項復核；原始與重測報告均保留，見 BALANCE.md。
- 改前真正 p7 核心的固定 seeds 0–39：HR 48.73%、界內球出局 26.96%、7.3375 分／半局。新版同 40 seeds：**HR 8.58%、出局 71.01%、簡化安打 28.99%、0.525 分／半局、9863.85 ticks／場**，40/40 completed、0 aborted，三項整體目標通過。
- 最終設定：35 m/s 上限、4 m/s² 滾動減速、守備 9 m/s／16 m/s²、1m 接球半徑、24-tick 撲接與 360-tick 冷卻；跑動影響半徑／控球與傳球偏差，快球落點平方增加誤差。公式均由 C++ 決定性計算。
- 決策每 tick，120 Hz 下為 8.33ms 模擬時間；2 秒程序 watchdog 另計。修正短間隔時出手者立即自接的卡死問題，新增防止重開 catch 繞過的回歸測試。
- 每場只輸出 match.txt，只記變動欄位／座標；回放直接讀差分。verified_record 代表完整性／終局觀看狀態，不冒稱物理重算。舊 JSON／舊版本為 unsupported_version，使用原 Git tag 查看。
- ruleset／physics／map／schema 全部升為 2.0.0，golden 已更新：飛行、擊球品質、跑動傳接、快球偏差、滾動與守備移動；新版 TXT 壓縮範例已替換。
- 出口：**111 Python tests、7 JavaScript tests 全過**；10 次外部 Bot 同 seed 重賽 TXT／終局雜湊一致；隱藏 UI 驗收一般場 17 項、有得分場 **20 項全過**；來源記錄未改。
- 正式預設賽 seed42：0:13、雙方各 10 半局、117662 ticks，正常 completed；原始 TXT 9618785 bytes。完整賽 100 次 hot seek 中位 **0.150ms**、P95 **0.268ms**（本機記憶體索引）。該場有 55 次跑動傳球偏差。
- 隔離來源／原生重建／離線 npm ci／全套 Python/JS／外部對戰／TXT 驗證／影格／範例解壓共 **9 個命令全過**。證據為 workspace/tests/reports/v2-*.json。
- 已知範圍：目標在全部 40 場整體達成；20–39 子批次得分只有 0.275／半局，基本 Bot 的固定模式與有限樣本仍有變異。40 場直接掉球為 0；高相對球速掉球場景已測，傳球偏差在正式賽實際出現。這不是完整官方記錄員的安打／野手選擇判定。更換 Bot 應重跑批次。
- 沒有操作、關閉或切換使用者桌面視窗。results、建置產物、node_modules 與快取仍全部忽略；沒有推送 remote。後續工作可直接從根 README 命令開始。

## 後續範圍／已知限制

- 已驗收 Windows x64；其他平台的 D3 尚未宣告。Job Object 是資源隔離，並非檔案／網路安全沙箱。
- 首版是幾何球員、球高陰影與 visual profile；Blender/GLB 動畫、美術、真人控制、網路多人、進階訓練依計畫留待後續。
- FPS 是本機 1080p 離屏實測，不代表所有前景硬體。舊版已開啟的 viewer 在程式更新後應由使用者自行重新啟動。
- results、build、node_modules、工具鏈與 cache 均維持忽略。所有階段已完成，可從根 README 的離線範例或新對戰命令開始使用。
