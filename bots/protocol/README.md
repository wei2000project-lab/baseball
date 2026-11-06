# Bot JSONL 協定 1.0.0

一隊一程序。stdin/stdout 各行為 UTF-8 JSON；stderr 為診斷。
`init → ready → observe/action → shutdown`。
回覆必須包含相同 decision_id 與 protocol_version；不可超過 64 KiB。
每名球員最多一個複合動作（移動與接球可同時開啟）。
數值位置與速度使用 Q32.32 十進位字串，power_u16 為整數。
