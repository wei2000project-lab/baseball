# 開發進度

目前階段：**P3 已通過，準備進入 P4**。P0 `ef3b943` / `p0`，P1 `ca37e53` / `p1`，P2 `0a82857` / `p2`。

依序 P0 → P7；每期先通過該期全部出口測試，再提交 `P<n>: 說明` 並建立 `p<n>` tag。未通過不可進下一期。

| 階段 | 狀態 | 出口驗證 |
| --- | --- | --- |
| P0 專案骨架與資料合約 | 通過（tag: `p0`） | 專案內 Zig 0.13.0 原生建置；10 項 pytest 通過；compileall 通過 |
| P1 物理與場地核心 | 通過（tag: `p1`） | 原生重建；P0/P1 共 24 項測試通過；100 ticks golden 軌跡重算 10 次一致 |
| P2 打席與半局 | 通過（tag: `p2`） | T01–T07、T18；全套 39 tests；診斷控制器完成上下半局並封存記錄 |
| P3 活球與限時規則 | 通過（tag: `p3`） | T08–T22、限時／交換邊界、回壘 checkpoint；全套 68 tests |
| P4 Bot 與端到端對戰 | 未開始 | — |
| P5 重算與驗證器 | 未開始 | — |
| P6 Electron 回放 | 未開始 | — |
| P7 整合封存 | 未開始 | — |

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
- 已知未完成：外部程序 BotHost、基本 Bot、正式 match CLI 尚屬 P4；`scripted_match.py` 僅為 diagnostic。驗證／seek CLI、Electron、整合文件亦未完成，不宣稱首版已交付。
- 下一期 P4：受限外部 Bot、JSONL 協定與 20 seeds 對戰出口。
- `results/`、工具鏈、建置產物、node_modules 與快取不納入 Git。
