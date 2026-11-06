# 棒球 Bot

以專案根目錄為工作目錄，Python 3.13；目前 Windows 建置使用 Zig 0.13.0。

```powershell
python -m pip install --target .tools ziglang==0.13.0
python workspace/build_native.py
python -m pytest workspace/tests -q
```

Python 透過 ctypes 呼叫原生 C++，無第二套物理；無須 pybind11。
亦提供 CMakeLists.txt，使用支援 `__int128` 的 Clang/GCC 工具鏈。
各期實際完成狀態、問題與驗收結果見根目錄 PROGRESS.md。

P2 診斷控制器可跑完整上下半局與記錄；打者不揮棒，不代表 P3/P4 的活球與正式 Bot 已完成。

```powershell
python workspace/scripted_match.py --regulation-ticks 1200 --output results/p2-scripted
```

輸出目錄必須為空或不存在。內含完整設定、初始狀態、動作、事件、檢查點與摘要。
