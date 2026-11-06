# 版本與範圍

目前專案、schema、ruleset、physics、map 皆為 **2.0.0**，Bot JSONL 協定維持 1.0.0。

新版包含擊球時機／位置品質、力度縮窗、35 m/s 上限、滾動減速、獨立守備移動能力、撲接冷卻、跑動傳接球誤差與快球落點誤差。公式由 C++ Q32.32 決定性計算，沒有成功率骰子；見根 BALANCE.md。

記錄為 BASEBALL-TXT 2，快取為 bb-frames-v2。舊 P0–P7 JSON 記錄一律 unsupported_version，請使用原 Git tag；歷史報告不代表新版仍支援舊格式。

verified_record 僅表示 TXT／摘要完整性與終局觀看狀態雜湊相符，不重算物理、不驗證原動作合法性，也不是簽章。無 END 為 incomplete；原引擎終局雜湊為紀錄資訊，回放另使用 replay_state_hash。

每 tick 一次決策機會（120 Hz，8.33 ms 模擬時間）；watchdog 另為 2 秒牆鐘時間。移動／接球意圖持續，不因重送而增加動作。

已驗收 Windows x64；其他平台尚未宣告 D3。維持 Q32.32、bb-canon-v1、固定 CORDIC、xoshiro256**／SplitMix64。Job Object 是資源限制，不是檔案／網路沙箱。

仍為幾何球員與 visual profile，未加入真人操作、網路多人、GLB 動畫或訓練平台；計畫省略的換人、DH、牽制、內野高飛必死等規則仍未加入。模型偏移與比例僅影響顯示。
