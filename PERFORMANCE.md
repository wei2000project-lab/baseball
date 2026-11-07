# 對戰效能改善

正常對戰的實測中位耗時由 **32.52 秒降至 12.79 秒，約快 2.54 倍（耗時減少60.7%）**。相同 Bot、seed、設定與15031ticks，改前3場與改後3場的 match.txt、事件、終局狀態雜湊完全一致。規則／物理仍2.1.0，每tick仍提供兩隊決策，沒有減少觀察、加快跑者或縮短賽程來換取速度。

## 改動與量測

- 原本每tick：兩次公開observe、兩次decision_record各再observe、一次故障回復snapshot，合計約5次全狀態deepcopy；另對完整公開狀態做約4次canonical轉換。
- 現在每tick：一份公開觀察與一份故障回復快照，共2次JSON樹複製；完整公開狀態只canonical一次，計算一次SHA並共用給兩隊。各隊的team_id、decision_id、合法動作清單仍個別編碼、各自送出，收齊回覆才套用動作。
- JSON樹複製保留所有值、巢狀隔離與Q32.32精度；不再為每個不可變字串／整數反覆進入deepcopy。故障時仍回復最後有效tick並封存aborted記錄。
- Bot JSONL封包連位元組都與原本canonical編碼一致；NFC／控制字元、完整18人資料與私有RNG隱藏另有測試。

| 正式外部Bot短賽 | 第1次 | 第2次 | 第3次 | 中位數 |
| --- | ---: | ---: | ---: | ---: |
| 改前 | 32.537s | 32.516s | 32.147s | 32.516s |
| 改後 | 12.593s | 12.826s | 12.788s | 12.788s |

本機Windows x64／Python3.13.9，基本Bot對基本Bot，seed42、regulation1200、實際完成15031ticks。不是把10秒模擬時間誤當成10秒牆鐘時間；到時仍完成目標局。基準TXT SHA256為 `e04f09e08ec5e3ff88eb953e59f73593b4063d5e50db9abdf7234683492da057`。

另跑完整900模擬秒（regulation108000）：**88.692秒、111486ticks、1:4、雙方各8半局、completed**，TXT回放驗證通過。完整賽只量測新版，沒有冒稱和未量測的舊完整賽比較。不同Bot的計算成本會影響實際耗時。

原始證據在 workspace/tests/reports/performance-before.json、performance-after.json、performance-full-after.json、performance-summary.json。cProfile摘要 performance-profile-before.json 是定位成本用，profiler本身增加耗時，沒有拿其128秒和一般執行時間比較。

## 目前選用組合的場上停滯

也以啟動器原本的基本Bot對GPT_tactical_cpp重現：改前與改後引擎都在最後狀態變更tick13834後，維持同一個活球場景。投手away.P01持球；home.P04最後合法壘為三壘、位置約(-4.904,5.013)，home.P05最後合法壘為一壘、位置約(14.038,24.448)，兩者target_base都為null、均停在壘間。守方也沒有繼續處理，因此跑者不滿足安全停壘的收球條件。

模擬時鐘和Bot通訊仍在繼續，場上沒有進展；這不是某個tick或單次回覆卡住。單純降低regulation也無法保證該活球自動結束，仍可能等到max_ticks。這兩個診斷測試已由我們停止，沒有算作完成的耗時樣本；沒有停止使用者自己的比賽。證據 performance-cpp-stall.json。

依使用者先前要求，保留正式Bot策略。已另詢問是否加入「活球連續20個模擬秒無進展就中止、不判勝負」的保護，尚未收到選擇，本次沒有加入該中止規則。

## 驗證與使用

145項Python、7項JS、32項自身隱藏啟動器檢查通過，完整賽回放verified_record；全程未控制桌面。既有goldens直接通過，沒有重寫期望值。

原啟動器不需重新打包；下一次按開始對戰時，Python子程序會載入新版。已在執行的程序仍用啟動時的程式碼。完整模式仍是15分鐘模擬時間；可自行選「短場」或「自訂模擬秒數」來調整賽程長度。

重測命令（從專案根目錄、每次換新的output）：

```powershell
python workspace/benchmark_match.py --n 3 --output results/perf-local --report results/perf-local.json
# 與既有同設定比賽逐位元組比較：加 --reference results/某場次
# 完整900模擬秒：加 --regulation-ticks 108000
```

效能里程碑tag為 performance-v1。平衡目標仍未達標，與這次執行速度改善分開記錄，見BALANCE.md與PROGRESS.md。
