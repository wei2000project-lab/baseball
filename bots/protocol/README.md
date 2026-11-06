# Bot JSONL 協定 1.0.0

一隊一程序。stdin/stdout 各行為 UTF-8 JSON；stderr 為診斷。
`init → ready → observe/action → shutdown`。
回覆必須包含相同 decision_id 與 protocol_version；不可超過 64 KiB。
每名球員最多一個複合動作（移動與接球可同時開啟）。
數值位置與速度使用 Q32.32 十進位字串，power_u16 為整數。

2.0.0 每 tick（8.33 ms 模擬時間）提供一次決策機會，程序故障 watchdog 另為 2 秒。移動／接球意圖持續生效，不必重送相同動作。`dive` 與 `hold` 相同欄位：action_id、player_id、kind；只可在防守活球時使用，觀察中的 dive_until_tick／dive_ready_tick／catch_ready_tick 是持續、冷卻與掉球後可重試時間。冷卻跨打席保留。公開 capabilities 含新物理參數，Bot 可選擇減速再傳接，或使用撲接。
