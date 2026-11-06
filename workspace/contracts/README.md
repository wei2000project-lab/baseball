# 可執行合約

- `config.schema.json`：固定小數設定；額外的範圍／幾何交叉檢查由 configuration.py 執行。
- `state.schema.json`：完整未來相關狀態，checkpoint restore 使用相同合約。
- `action.schema.json`：Bot action envelope 與單一球員動作；bots/protocol 保存相同動作合約。
- `event.schema.json`：事件 envelope；重算逐欄比對實際輸出，不能只信事件文字。
- `records/`：manifest、action 稽核列、checkpoint、summary／MatchResult。
- `bots/protocol/message.schema.json`：init/ready/observe/action/shutdown，全觀察不含引擎 RNG。
- `model/visual_profiles/profile.schema.json`：獨立視覺合約，可使用小數；不納入權威狀態雜湊。

標準 JSON Schema draft 2020-12。核心 contracts.py 只實作交付合約需要的 vocabulary，遇到未知 keyword 會拒絕。視覺 number／變換驗證由 viewer/profile.cjs 處理，不擴張物理數值格式。
