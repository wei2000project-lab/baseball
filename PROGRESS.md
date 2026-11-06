# 開發進度

目前階段：**P1 已通過，準備進入 P2**。P0 已提交 `ef3b943`，tag `p0`。

依序 P0 → P7；每期先通過該期全部出口測試，再提交 `P<n>: 說明` 並建立 `p<n>` tag。未通過不可進下一期。

| 階段 | 狀態 | 出口驗證 |
| --- | --- | --- |
| P0 專案骨架與資料合約 | 通過（tag: `p0`） | 專案內 Zig 0.13.0 原生建置；10 項 pytest 通過；compileall 通過 |
| P1 物理與場地核心 | 通過（tag: `p1`） | 原生重建；P0/P1 共 24 項測試通過；100 ticks golden 軌跡重算 10 次一致 |
| P2 打席與半局 | 未開始 | — |
| P3 活球與限時規則 | 未開始 | — |
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
- 尚未實作打席、比賽或回放；P2 尚未開始。
- 下一期 P2：打席／半局狀態機、投打判定與記錄基礎；先通過 T01–T07、T18。
- `results/`、工具鏈、建置產物、node_modules 與快取不納入 Git。
