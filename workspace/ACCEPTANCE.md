# 2.1.0 實驗里程碑驗收

功能出口通過：140 Python、7 JS、20項隱藏離屏回放；10次正式外部Bot重賽TXT bytes／終局hash完全一致；隔離來源10個命令全過（當次138 Python，後增跨打席與快取測試在目前工作樹通過），含32項原生隱藏GUI驗收。報告見 tests/reports/advancement-*.json。

新增接球恢復、延遲傳球與不可重啟、持球速度上限、實際出手授壘基準、snapshot／TXT狀態、舊2.0.0拒絕、跨打席推進／DP分母、固定來源快取閘門；golden及新版壓縮TXT範例已更新。

**平衡出口未通過**：32組初篩、6組驗證、3組保留seeds，沒有四項同時達標候選；selected=null。起始設定與最接近組的原始報告均保留，--check-targets確實返回2，不宣稱已平衡。僅封存 `advancement-v2.1.0-experimental` 工具／規則成本里程碑；接續見根 PROGRESS.md、BALANCE.md。

正式Bots未改；所有UI檢查皆自身不可見視窗，沒有操作桌面。

---

# 2.0.0 驗收與需求追蹤

## 原生對戰啟動器

`launcher-v1`：launcher/啟動遊戲.bat 是雙擊入口，啟動已編譯的 C++ Windows GUI，可選／交換主客隊、Bot 檔案或資料夾、輸出、場次名稱、Seed、模擬時間，直接開始／停止並觀看回放。支援新加入的 Bot；編譯錯誤在視窗呈現，設定／編譯產物／日誌在忽略的 launcher/build。

整套 121 Python tests 通過，新增測試確認 --progress 不改變對戰／TXT，並從不同工作目錄實際執行 BAT --check。32 項原生隱藏 GUI 驗收通過：主客隊交換、路徑引用、中文／空格、不覆寫、成功／取消自有程序樹／編譯失敗、按鈕與輸出完整性。PE subsystem=2，是真正 GUI 執行檔。隔離來源 10 個命令全過，含 121 Python／7 JS 與 GUI 重建／隱藏驗收；報告見 tests/reports/launcher*.json。

所有測試均未顯示啟動器視窗、檔案對話框或回放，不操控桌面。規則、物理與原有 Bot 策略沒有修改；進度只是可選的輸出通道。

## C++ Bot 擴充

`cpp-bot-v1`：新增 bot.cpp 自動 C++17 編譯、資料夾／原始檔／執行檔／bot.json 入口、來源與本地標頭快取、離線 JSON 標頭及無策略的 bots/BOT_REFERENCE.md。規則、物理與基本 Bot 策略未變。

新增 8 項測試涵蓋實際編譯、快取與標頭變更、編譯錯誤、descriptor 優先、完整雙方18人觀察、連續 tick 更新、動作控制及 C++／Python 混合對戰；整套 119 Python tests 通過。隔離來源 9 個命令（含 119 Python、7 JS）全部通過，見 tests/reports/cpp-cleanroom.json 與 cpp-support.json。先前 111 項與平衡統計為下方 2.0.0 封存時的結果。

P0–P7 已依原出口測試封存於 p0–p7 tags。以下為使用者追加的平衡與 TXT 需求；回放直接讀差分取代原計畫的逐動作重算。

| 需求 | 實作與證據 |
| --- | --- |
| 固定 seeds 改前／改後 | balance_reports/00-before、14-before-extra、15-before-40；真正 p7 核心，與新版相同 seeds 0–39比較 |
| a–f 依序測量 | 01–06 原始逐項報告；10-recheck-a～f 正確界內分母復核；根 BALANCE.md 說明差異 |
| 多項聯調與目標 | 07–12 保留未達標與子批次；13-final-40 三項整體 target_checks=true，40/40 completed |
| 擊球品質、力度容錯、球速／摩擦 | C++ contact_velocity、native golden、test_balance、test_p1 |
| 守備、撲接冷卻、跑動失誤 | native field skill、Engine dive／retry／release exclusion；test_balance、test_p3、test_p7 |
| 快球控球成本 | native pitch scatter 六球固定序列與平方包絡；golden／test_balance |
| 約 10ms 決策機會 | 1 tick = 8.33ms 模擬時間；保留同時觀察／一次套用，程序 watchdog 另計 |
| 精簡記錄／回放 | recording.py、txt_record.py、replay.py；單一 match.txt、未變欄位省略、100 隨機 tick 對照真實引擎觀看狀態 |
| 舊版 unsupported_version | test_p5、test_p7、test_balance；不近似套用新物理 |
| 限時、公平與棒球規則 | test_p2/test_p3 保留 T01–T22、強迫鏈、回壘、得分、第三出局、上限與交換邊界 |
| 外部 Bot 與資源限制 | test_p4、v2-determinism；Python／JavaScript 替換、記憶體、watchdog、故障中止 |
| Electron 播放與隔離 | test_p6、viewer.test.mjs；v2-ui 17 項、v2-ui-scoring 20 項，含 HR／得分同步、HTML 安全、取消與 1080p 離屏圖 |
| 隔離重建與離線範例 | v2-cleanroom：9 個命令，全套測試、對戰、TXT、快取、解壓與完整性校驗 |

最終 Python 111 項、JavaScript 7 項全部通過。golden 包含自由落體、擊球品質、滾動、守備移動、跑動傳接球與快球落點。

正式短賽 seed42 0:0、9916 ticks；有得分場 seed0 1:2、12881 ticks。相同 seed42 的 10 次外部 Bot 重賽，TXT bytes 與終局 hash 相同。正式預設賽 0:13、雙方各 10 半局、117662 ticks、completed；TXT 約 9.6MB，跑動傳球偏差 55 次。完整賽 hot seek 100 次，中位 0.150ms、P95 0.268ms；這是本機記憶體索引效能。

verified_record 只驗 TXT／摘要完整性與終局觀看投影，不驗原動作合法性或物理重算；原引擎 hash 為記錄資訊。無 END 為 incomplete，不能宣稱完整驗證。舊 P4/P5/P7 reports 是歷史，最新版不再相容舊記錄。

40 場整體目標：HR 8.58%、界內球出局 71.01%、0.525 分／半局。20 場子組有變異；安打為簡化記分，直接掉球在基本 Bot 樣本中為 0，高速掉球情境另有回歸測試。完整設定、分子分母與限制見 BALANCE.md。

所有 UI 驗收使用自己的不可見離屏視窗與記錄副本，不控制桌面。results、build、node_modules 與快取不入 Git；必要 JSON 報告及壓縮 TXT 範例另版控。Windows x64 已驗收，跨平台 D3、美術動畫與進階策略訓練仍屬後續。
