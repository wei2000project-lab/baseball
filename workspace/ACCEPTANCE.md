# 2.0.0 驗收與需求追蹤

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
