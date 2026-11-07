# tactical_cpp

僅依據 `bots/BOT_REFERENCE.md` 設計的 C++17 bot，未參考其他 bot 或引擎實作。

- 投球：讀取場地與物理設定，以低彈道朝好球區投球，並用觀測速度校正後續估計。
- 打擊：依球的位置、速度與重力預測到達時間，配合揮棒延遲，朝守備空隙擊球。
- 跑壘：優先處理強迫進壘、回壘義務，其他情況比較跑壘與守方回傳時間。
- 守備：每 tick 更新攔截點，由兩名球員追球，其餘球員補位；持球時選擇封殺、回壘申訴或觸殺。
- 通訊：持續讀取 JSONL，遵守 `legal_action_types`、每人一動作與每次最多九動作的限制。

設定欄位名稱未在參考文件逐一列出，因此程式辨識常見設定名稱，缺少個別參數時使用內建估計；這些估計與策略尚需透過對戰調整。

在專案根目錄編譯：

```powershell
python workspace/build_bot.py bots/tactical_cpp/bot.cpp
```

直接指定 `bots/tactical_cpp` 或 `bots/tactical_cpp/bot.cpp` 即可參賽，對戰主機會自動編譯。例如自我對戰：

```powershell
python workspace/match.py --away bots/tactical_cpp --home bots/tactical_cpp --seed 42 --regulation-ticks 1200 --output results/tactical-cpp-selfplay
```
