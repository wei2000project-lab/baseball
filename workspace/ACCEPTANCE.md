# 首版驗收與需求追蹤

對應原始計畫第 19 節。所有里程碑先跑出口測試，再以 `P<n>: …` 提交並打 `p<n>` tag；原始結果不納入 Git，必要報告與壓縮參考記錄版本化保存。

| 需求 | 實作與證據 |
| --- | --- |
| R01/R08/R09 限時、公平、模擬時間 | baseball_engine.py；test_p3 時限／交換邊界、正常完成優先於上限；新舊完整對戰 |
| R02 四個根目錄 | bots、results、model、workspace；隔離來源建置驗收 |
| R03 自動對戰入口 | match.py；20 seeds 批次、預設 15 分鐘完整賽、另一語言 Bot 替換 |
| R04 唯一規則與重算核心 | match/replay/viewer_worker 共用 BaseballEngine；D1、全部 checkpoint 恢復、隨機 seek |
| R05 C++ 物理與限制 | baseball.hpp/baseball.cpp/native_bindings.cpp；固定數值、掃掠、反彈、角度、速度／加速度 golden tests |
| R06 獨立邏輯地圖 | map.cpp/map.hpp；公平／界線、路徑／觸壘、普通減速與牆邊界，沒有美術依賴 |
| R07 Electron 回放 | viewer.html、viewer、electron；真實隱藏 renderer 的 20 項整合驗收 |
| R10 球 3D／球員 2D | 原生球軌跡、移動相對掃掠；球高／陰影與位置同步 |
| R11 可替換 Bot | JSONL、程序隔離、完整訊息 Schema；Python/JavaScript 對戰、故障與資源限制測試 |
| R12 模型接點 | visual profile Schema、原點／角色偏移、比例與錨點；雜湊不因視覺變更而變動 |

## 規則與合約矩陣

| 案例 | 驗收位置 |
| --- | --- |
| T01–T07、T18 | test_p2：球體好球區、兩好球界外、揮棒窗／幾何、投球時鐘、觸身優先、滾地定案、保送與打序 |
| T08–T14 | test_p3：接殺／拾球同時、多守備員固定 ID、牆／HR／二壘授壘、封殺競速、雙殺與獨立強迫鏈 |
| T15–T22 | test_p3：第三出局候選得分、回壘／申訴、超越與壘位權、傳球出場、合法收球與精確等待 |
| 補充規則 | test_p2/test_p3：10 分／15 打席上限、投捕與跑者重置、目標壘立即停下 |
| 時限公平 | test_p3：上／下打席、交換、交換結束前／同／後、相同半局數、一次到時與正式／中止分離 |
| D1 與完整性 | test_p5：10 次完整重算、全部 checkpoint suffix、100 隨機 seek、故意破壞並重封存雜湊、截斷、舊版／未知版本、incomplete |
| D2 與 Bot 限制 | test_p4、determinism_acceptance：10 次同 seed；真實 memory allocation、watchdog、超長輸出、stale ID、另一語言替換 |
| 順序與數值 | test_p0/test_p1/test_p5：Q32.32、RNG／seed、canonical、接觸時間、容器插入與回覆順序、有限範圍 fuzz |
| P7 移動補測 | test_p7：普通目標減速收斂、加速度界、牆外目標及邊界停止時間、舊地圖路徑保留 |
| 介面／視覺 | test_p6、viewer.test.mjs、ui_acceptance：精確 tick/hash、0.25×／8×、事件、角色／球高、HTML 不執行、取消、LRU 上限與 1080p 影像 |

## 可重現報告

- `tests/reports/p4-acceptance.json`：P4 20 seeds × 2 輪、預設賽與參考機。
- `p5-d2-acceptance.json`、`p5-replay-acceptance.json`、`p5-seek-performance.json`：確定性、舊賽重算與 100 次 hot seek。
- `p6-ui.json`：20 項隱藏離屏整合檢查；來源記錄未變更。
- `p7-d2-acceptance.json`、`p7-legacy-acceptance.json`：新版 10 次重賽及舊版逐事件／雜湊相容。
- `p7-cleanroom.json`：隔離來源／輸出重新編譯、離線 npm ci、全套測試、對戰、完整驗證、影格與壓縮範例還原；只重用明確記錄的工具鏈快取。
- `p7-release.json`、`p7-replay-acceptance.json`、`p7-ui.json`：首版最終批次、效能、重算與新版本介面驗收。
- `p7-seek-performance.json`：新版 100 次 hot seek，中位 44 ms、P95 187 ms、最長 228 ms；首次索引載入 734 ms。

參考機：Intel Core Ultra 5 225、33787138048 bytes RAM、Windows x64、Python 3.13.9、Node 24.22.1、Zig 0.13.0。P4 含外部 Bot 與記錄的預設賽曾量得約 16.16 倍模擬實時；P5 已建索引的 100 次 seek 中位 48 ms、P95 175 ms、最長 241 ms。新版數據寫入最終報告。

最小復現：根目錄 README 的建置與範例命令。完整批次可用 acceptance.py、verify_acceptance.py、determinism_acceptance.py；cleanroom_acceptance.py 驗證隔離源碼，不操作任何桌面視窗。

最終檢查：107 項 Python 測試、7 項 JavaScript 測試、20 項新版真實離屏 UI 整合檢查全過。新版 20 seeds 全 completed 且逐份 verified_full；同 seed 10 次重賽一致；20 份 P4 記錄與壓縮 P5 範例仍逐事件／雜湊一致。隔離來源驗收完成 9 個命令（當時全套 105 tests，後續補上解壓與未來版本分類回歸案例）。

新版預設賽：seed 42、regulation_ticks=108000，36:36、雙方各 6 半局、121419 ticks、正常平手終局；實際 61.031 秒，含 Bot 與記錄約 16.58 倍模擬實時。新地圖的結果與 P4/P5 範例不同是版本化的行為變更，沒有覆寫舊記錄。新版 1080p 離屏播放測得 59 FPS（目標 60；P6 測得 60）。

使用者要求 `results/`、build、node_modules 與 cache 不進 Git；因此範例以 `examples/demo-0042.bbrec.zip` 提供，解壓至新的 results 目錄後驗證。沒有打包 Bot、模型或 playback cache，刪除這些資料仍能重算。
