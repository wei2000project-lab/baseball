# 視覺資產約定

此目錄只供視覺使用，不影響規則或碰撞。首版不需要 Blender 資產。
世界座標單位為公尺，Z 向上，本壘為原點、Y 指向中外野。
未來使用 GLB/glTF，角色原點設於腳底中心。手套與球棒掛點只用於動畫。
視覺偏移、模型比例與模型原點修正必須留在 viewer；禁止回寫權威狀態。

`visual_profiles/default.json` 是目前可用設定，合約在 `visual_profiles/profile.schema.json`；viewer/profile.cjs 在載入時驗證，缺少或無效則回到基本幾何。支援 model_scale、model_origin_correction、visual_offset_local、角色偏移及視覺錨點。數值可為有限小數，與 Q32.32 權威資料分離。

model_asset_id 為未來資產 ID，不會當作可執行程式或任意檔案路徑。首版不匯入 GLB、不製作骨架動畫。改變比例或偏移，可開啟邏輯區域確認腳下錨點；比分、事件與狀態雜湊不變。
