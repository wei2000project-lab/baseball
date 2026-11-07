# 接手文件：無法完賽與零得分仍未解

更新日期：2026-11-07。儲存庫：https://github.com/wei2000project-lab/baseball ，交付分支 main。

**使用者目前實測仍有無法完賽、雙方未得分的問題，尚未修復。** 這次交付是現況備份、原始碼與診斷交接，不是已修好的遊戲版本。P0–P7、單元測試與效能里程碑通過，不代表目前主要對戰組合已能正常完賽與得分。

## 目前已知事實

| 項目 | 狀態／證據 |
| --- | --- |
| 主要問題組合 | 客隊 bots/base_bot；主隊 bots/GPT_tactical_cpp；seed42 |
| 無法完賽、比分0:0 | 使用者回報；本機也重現活球停滯，尚無同組合修復後正常完成的驗收 |
| 有界重現 | reproduce_stall.py 在tick14434捕捉到連續600ticks沒有公開場上狀態變化，當時0:0；本機17.225秒，含啟動 |
| 可直接還原資料 | workspace/tests/reports/handoff-stall-snapshot.json，含config、完整state、RNG、state_hash及兩隊程式雜湊 |
| 還原確認 | handoff-snapshot-restore.json：hash一致；不送新指令再跑1000ticks至15434，投影未變、terminal=null、兩跑者safe=false |
| 隔離重現 | handoff-isolated-repro.json：從隔離來源重建C++ Bot，仍在tick14434取得相同完整GameState／config／原始碼SHA；問題可跨建置目錄重現 |
| 功能測試 | 最近完整145 Python、7 JS、32項自身隱藏啟動器檢查通過；沒有證明上述缺陷已解 |
| 效能 | 基本Bot對基本Bot短賽中位32.516→12.788秒，TXT完全相同；只改善執行效率 |
| 另一組可完成案例 | 基本Bot對基本Bot完整900模擬秒：111486ticks、1:4、88.692秒、completed；不能替代主要問題組合的驗收 |
| 平衡 | 2.1.0掃描沒有四項同時達標組，selected=null；尚未完成 |

先前將停滯歸因於Bot行為，是根據場上指令／位置的診斷。**規則、收球條件與Bot互動的責任仍應重新驗證，不能僅貼上「Bot問題」就結案。** 零得分也必須沿完整得分事件鏈檢查；不能把加速或中止當成修復。

## 一、新電腦建置

目前實測Windows x64、Python3.13、Node24、Zig0.13.0；未宣稱其他平台已驗收。從新clone的專案根目錄執行PowerShell：

```powershell
git clone https://github.com/wei2000project-lab/baseball.git baseball
Set-Location baseball
python -m pip install -r workspace/requirements.txt -r workspace/requirements-dev.txt
python workspace/build_native.py
npm ci --prefix workspace
```

若Node沒有附npm，可改用：

```powershell
python workspace/bootstrap_node.py
node .tools/npm-runtime/package/bin/npm-cli.js ci --prefix workspace
```

不需要CMake。Zig由requirements-dev安裝，Bot JSON標頭已附在bots/vendor。首次安裝套件與Electron需要網路。工具鏈、DLL、exe、node_modules、快取與results不在Git；新clone需要重新建置。

啟動器入口為 launcher/啟動遊戲.bat；接手除錯可完全使用CLI。不要要求桌面控制、切換視窗或操作使用者正在使用的程式。

## 二、優先用有界診斷重現

```powershell
$case = 'results/handoff-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
python workspace/reproduce_stall.py --output $case --report "$case-snapshot.json"
```

預設為基本Bot對GPT_tactical_cpp、seed42、regulation1200。連續600ticks活球投影無變化時捕捉；最多觀察20000ticks。這只是診斷預算，不改正式引擎規則或Bot動作。

成功捕捉會印出 unchanged_live_play 並回傳0。**此0只表示診斷成功，不是比賽完成。** capture_only=true、formal_outcome=null；因診斷停止，match.txt沒有END，回放驗證為incomplete是預期，不能算成勝負／完賽修復。若正常終局或到tick預算而未捕捉停滯，工具回傳2，請查report.reason。

正式行為可用新輸出目錄測試：

```powershell
$case = 'results/formal-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
python workspace/match.py --away bots/base_bot --home bots/GPT_tactical_cpp --seed 42 --regulation-ticks 1200 --output $case --progress
```

即使regulation1200也可能拖很久：時間到只設定完成目標局，不能直接結束未完成活球。碰max_ticks則aborted，不能當completed。輸出目錄需為空或不存在。

目前GPT_tactical_cpp已原樣納入交接，沒有改策略：

- bot.cpp SHA256：`82b1872572ce5edc4d611cee40c1ac1d4ea767ab1db1f22fa25b9c96bcb18bfc`
- 同目錄README保留原文，其中bots/tactical_cpp是舊目錄名；實際使用bots/GPT_tactical_cpp，以本交接指令為準。
- C++在對戰前自動編譯至忽略的workspace/build/cpp-bots，不需要手動打包或提交exe。

## 三、不啟動Bot，直接還原已捕捉場景

完成原生建置後，以下可驗證同一場景，無需等待整場：

```powershell
@'
import json, sys
from pathlib import Path
sys.path.insert(0, 'workspace')
from baseball_engine import BaseballEngine
from txt_record import project
r = json.loads(Path('workspace/tests/reports/handoff-stall-snapshot.json').read_text(encoding='utf-8'))
e = BaseballEngine()
e.initialize(r['config'], r['state'])
assert e.canonical_state_hash() == r['state_hash']
before = project(e.state)
for _ in range(1000):
    e.step()
assert project(e.state) == before
print(e.state['sim_tick'], e.state['phase'], e.state['score'], e.terminal_result())
'@ | python -
```

這是「沒有新指令時如何收球」的診斷，不能代替包含Bot決策的端到端測試。TXT只保存觀看差分，不能拿TXT的restore當權威GameState；上面的完整state快照才可用於引擎還原。

## 四、停滯場景與優先追查位置

改前／改後效能診斷的最後場上記錄變更均為tick13834。有界捕捉確認tick14434仍為BALL_IN_PLAY、比分0:0：

| 球員 | 狀態 |
| --- | --- |
| away.P01 | 持球；球為fielder_held，origin=throw |
| home.P04 | 最後合法壘3；位置約(-4.904,5.013)，停在三壘到本壘之間；target_base=null |
| home.P05 | 最後合法壘1；位置約(14.038,24.448)，停在一壘到二壘之間；target_base=null |
| 跑者義務 | 兩人force_obligation與retouch_obligation皆null；還原測試safe皆false |

模擬時鐘與通訊仍前進，並非單次回覆卡住。TXT省略未變欄位，因此最後T行停在13834不代表引擎sim_tick停在13834；不能誤判為CPU死循環。

| 檔案／函式 | 需要釐清 |
| --- | --- |
| workspace/baseball_engine.py：_safe、_settle | 收球要求全部跑者target=null、速度0且安全在壘；壘間靜止不算safe。loose-ball recovery也先要求stopped，持球則不走該路徑 |
| 同檔：_boundary、_finish_pa、_finish_half | regulation_expired只標記公平完成目標局，活球可能不結束；max_ticks預設432000是中止，不是正常完賽 |
| 同檔：_arrival、_finish_play、_run_scored | 查BaseTouched(4)→RunPending→得分確認；檢查第三出局、取消得分與授壘，找出0:0是跑壘未完成還是計分缺陷 |
| bots/GPT_tactical_cpp/bot.cpp | 查何時清空跑壘目標／hold、是否永久等待，及是否正確讀取2.1.0恢復／傳球成本；先定位責任，不先改策略 |
| bots/base_bot/bot.py | 持球、無強迫壘時可能不再處理；傳球瞄準仍用40m/s假設，而規則上限為28m/s。這也是互動條件，不能只看單方 |
| workspace/match.py、bot_host.py | 收齊同tick兩隊回覆再套用；效能改版未跳過決策。單次回覆watchdog不會攔截每次正常回覆但場上不前進的情況 |

優先順序：先加同一案例的回歸與事件診斷，再判斷規則是否缺少活球停滯處理／Bot是否停住；依使用者限制決定修改範圍。接著核對得分事件與完整終局，再做平衡。不要先再調打擊／守備參數掩蓋停滯。

## 五、使用者限制與尚未決定事項

- 不要操作桌面或要求電腦控制。CLI、自己的隱藏／離屏驗收可使用。
- 先前明確要求：如果主要是Bot問題就不要修Bot；只有規則問題才修。本次沒有取得修改Bot策略的新授權；上傳原始碼不等於修改策略。
- 「活球連續20個模擬秒無進展就中止、不判勝負」已詢問但未獲選擇，尚未實作。即使加入，也只是保護，不能算正常完賽或得分已修好。
- 平衡以固定跑壘測試控制器衡量，不改正式Bot。是否擴大原6種固定擊球樣本，先前詢問仍未獲偏好；不要靠換樣本硬湊達標。
- 每個完成階段先驗證，再commit與tag；維護PROGRESS.md。results、建置、node_modules、快取維持忽略。

## 六、平衡與版本現況

schema／ruleset／physics／map為2.1.0；Bot JSONL為1.0.0；120Hz，每tick決策是8.33ms模擬時間，不是8.33ms牆鐘回覆限制。公開觀察含雙方18人與固定ID，位置為Q32.32整數字串。原生物理是C++固定數值，Python是唯一規則協調器。

起始設定：catch_recovery36、throw_windup27、持球速度×0.8、傳球上限28m/s、跑者8.25m/s、守備8.25m/s／加速度14／半徑0.9。這是未達標實驗設定。

32組初篩、6組驗證、3組保留seeds，共372場候選模擬，沒有合格組。前三組40場合併約0.25分／半局、33.33%推進、100%外野額外壘、42.59%雙殺／有效機會；四項目標皆未達。目標為1–3分／半局、35–50%推進、外野額外壘約60%（55–65%）、雙殺≤10%。分母、跨打席指標、原型作廢資料見BALANCE.md。

效能改版改變來源指紋，舊平衡快取不直接採用。重新跑scan_advancement.py可能耗時且仍未達標，請先處理停滯與計分；不要將selected=null誤讀為採用最接近候選。

## 七、驗證出口與文件索引

```powershell
python -m pytest workspace/tests -q
node --test workspace/tests/viewer.test.mjs
python launcher/verify_launcher.py
```

GUI驗收僅用自己的不可見視窗。既有145項Python通過只涵蓋既有案例；尚無「上述主要組合正常completed且合法得分」的修復驗收。接手修復至少應補：

1. 同一組合正常完成，不是aborted、人工capture、改seed或縮短最大上限造成的假通過；上下半局數公平。
2. 同一問題組合的得分事件與摘要一致，逐筆查明0分原因。一般棒球可以合法0:0，不能硬寫得分或要求每個seed都非零來造假。
3. 不因收球／停滯處理自動替Bot跑壘、授壘、判出局或判勝負；若需新規則先定義並遵守使用者授權。
4. 固定seed重跑、snapshot還原、舊版本拒絕、回放與goldens仍正確；真正改規則／物理時才升版、重算goldens，不重生期望值掩蓋缺陷。
5. 正常完賽與計分處理後，再以固定seeds驗證平衡；未達不標示完成。

文件與證據：

- PROGRESS.md：最新狀態、限制、已做與未做。
- BALANCE.md：未達標統計、分母、全部掃描。
- PERFORMANCE.md：僅速度改善，以及仍未解的停滯。
- bots/BOT_REFERENCE.md：AI寫Bot的規則／JSONL／觀察，不含策略。
- workspace/PHYSICS.md、workspace/contracts/：數值與結構合約。
- workspace/tests/reports/handoff-stall-snapshot.json、handoff-snapshot-restore.json：可還原的主要問題。
- workspace/tests/reports/handoff-cleanroom.json：交付前隔離來源10個命令通過，含145 Python／7 JS／32隱藏GUI；工具鏈快取重用，不是無網路依賴的全新電腦安裝。
- workspace/tests/reports/handoff-isolated-repro.json：隔離重新建置仍重現缺陷。program SHA含binary，兩次重建確有差異；不要求不同建置的binary SHA相等，比對的是來源、config與完整state。
- workspace/tests/reports/performance-cpp-stall.json：先前停滯觀察。

歷史：performance-v1／7d57c32只是加速；advancement-v2.1.0-experimental／c425357是未達標平衡實驗；launcher-v1／d06c7d7是啟動器；balance-v2.0.0／043d888是舊版平衡。2.0.0及P0–P7舊記錄在目前程式標示unsupported_version，需要對應tag程式觀看。這些tag都不是目前主要缺陷已修復的證明。
