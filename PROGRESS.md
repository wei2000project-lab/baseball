# 開發進度

目前階段：**P0 已通過，準備進入 P1**。原始計畫書已封存於 `704efe0`。

依序 P0 → P7；每期先通過該期全部出口測試，再提交 `P<n>: 說明` 並建立 `p<n>` tag。未通過不可進下一期。

| 階段 | 狀態 | 出口驗證 |
| --- | --- | --- |
| P0 專案骨架與資料合約 | 通過（tag: `p0`） | 專案內 Zig 0.13.0 原生建置；10 項 pytest 通過；compileall 通過 |
| P1 物理與場地核心 | 未開始 | — |
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
- 尚未實作打席、比賽或回放，不將骨架視為遊戲完成。
- 下一期 P1：固定時間球物理、場地／移動與連續接觸時間，先獨立測試，不加入 Bot 策略。
- `results/`、工具鏈、建置產物、node_modules 與快取不納入 Git。
