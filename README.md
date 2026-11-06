# 棒球 Bot 自動對戰遊戲

限時棒球 Bot 對戰與可重算的離線回放。Python 是唯一規則協調器，C++ 計算 3D 球、2D 球員與動作限制；Electron 使用同一引擎還原記錄。

首版 `0.1.0`，Windows 已驗收。預設 15 分鐘模擬時間；到時後公平完成目標局上下半局。每半局最多 10 分或 15 個完成打席。不需 Blender 模型，也不提供真人控球或網路多人。

## 建置

測試工具鏈：Python 3.13.9、Node 24.22.1、npm 12.2.2、Zig 0.13.0、Electron 45.2.3。初次安裝需要網路，完成後對戰及回放可離線使用。

以下均以專案根目錄為工作目錄。可先建立並啟用 `.venv`，再執行：

```powershell
python -m pip install -r workspace/requirements.txt -r workspace/requirements-dev.txt
python workspace/build_native.py
npm ci --prefix workspace
```

若只有 Node、沒有 npm：

```powershell
python workspace/bootstrap_node.py
node .tools/npm-runtime/package/bin/npm-cli.js ci --prefix workspace
```

建置腳本可自動找到 pip 安裝的 Zig，或使用專案內 `.tools/ziglang/zig.exe`。亦可指定 `--compiler`。所有建置及 Electron 使用者資料保存在 workspace/build；不改全域設定。CMakeLists 供原生開發參考；Python 入口使用 build_native.py 產生必要建置指紋。

## 先看離線範例

版本化範例約 807 KiB，包含完整記錄與雜湊，不包含原 Bot 或播放快取：

```powershell
python workspace/unpack_demo.py --output results/demo-0042
python workspace/replay.py verify --input results/demo-0042 --from-start
python workspace/viewer.py --record results/demo-0042
```

範例是 P5 規則的 10:9 對戰，驗證器保留原版運算路徑。新對戰預設使用 P7；相同 seed 在不同規則版本下可以有不同結果。輸出目錄必須不存在或為空，不會覆寫既有比賽。

## 執行新對戰

```powershell
python workspace/match.py --away bots/base_bot --home bots/base_bot --seed 42 --config workspace/config/default.json --output results/my-match
python workspace/replay.py verify --input results/my-match
python workspace/viewer.py --record results/my-match
```

可加 `--regulation-ticks 1200` 縮短驗收時間。更換 `--away`／`--home` 路徑即可替換 Bot；Python 與 JavaScript 範例均已實測。完整 JSONL 協定見 [bots/protocol](bots/protocol/README.md)。Bot 以 Windows Job Object 限制資源，不是檔案／網路安全沙箱，應使用信任的程式。

## 驗收與接續

```powershell
python -m pytest workspace/tests -q
node --test workspace/tests/viewer.test.mjs
python workspace/ui_acceptance.py --input results/my-match
```

最後一個命令只建立隱藏的離屏 renderer，使用記錄副本及獨立 userData，不注入鍵盤滑鼠、不切換使用者視窗。產生背景 UI 驗收報告與影像，不需要電腦控制權限。

- [PROGRESS.md](PROGRESS.md)：分期狀態、測試、提交／tag 與接續資訊。
- [驗收與需求追蹤](workspace/ACCEPTANCE.md)：需求／規則矩陣及實測報告。
- [執行與故障排查](workspace/README.md)：對戰、回放、定位、建置及錯誤處理。
- [物理數值約定](workspace/PHYSICS.md)、[版本與限制](workspace/VERSIONS.md)、[模型規約](model/README.md)。

`results/`、工具鏈、建置產物、node_modules 和快取均被 Git 忽略；原始計畫書與 `p0`–`p7` 里程碑保留。程式不自動推送 Git remote。
