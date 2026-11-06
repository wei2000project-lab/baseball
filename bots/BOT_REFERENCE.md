# 給 AI 的 Bot 開發參考

本文件只定義遊戲規則、可見資料與輸入／輸出介面，不提供打擊、跑壘、守備或傳球策略。請把自行設計的 Bot 放在 `bots/<名稱>/`，不要修改引擎來替 Bot 決策。

目前遊戲規則／物理為 **2.1.0**，Bot 通訊協定為 **1.0.0**。完整且可機器讀取的格式以 [message.schema.json](protocol/message.schema.json) 與 [action.schema.json](../workspace/contracts/action.schema.json) 為準。

## 1. C++ 與啟動方式

支援下列任一入口：

```text
bots/my_bot/bot.cpp       # C++17，啟動對戰時先編譯，再啟動可執行檔
bots/my_bot/bot.py        # Python
bots/my_bot/bot.json      # 自訂 command 字串陣列，不經 shell
```

資料夾選擇順序為 `bot.json` → `bot.cpp` → `bot.py`。也可以直接指定 `.cpp`、`.py` 或已編譯的 `.exe` 路徑。已有 `bot.json` 時，依其 command 執行；command 的程式為 C++ 原始檔時也會先編譯。

C++ 預設尋找專案的 Zig、已安裝的 ziglang、Clang 或 GCC；可用 `BASEBALL_BOT_CXX` 環境變數指定編譯器執行檔。自動建置使用 C++17、`-O2`，一次編譯指定的主原始檔，可 `#include` 同資料夾內的標頭。多翻譯單元或其他建置系統可自行產生 `.exe`，再指定該執行檔。

目前正式對戰主機支援 Windows x64。C++ 原始檔請使用 UTF-8。

已附可離線使用的 `nlohmann/json` 標頭，直接 `#include <nlohmann/json.hpp>`；範例為 [examples/cpp_passive/bot.cpp](examples/cpp_passive/bot.cpp)，只完成協定並回覆空動作。依賴版本／授權見 [vendor/README.md](vendor/README.md)。

編譯在 Bot 的回覆計時與執行期資源限制開始前進行。原始檔／本地標頭／附帶 JSON 標頭／編譯器變動會使用新建置快取，產物位於忽略的 `workspace/build/cpp-bots/`，不寫回 Bot 原始碼目錄。只追蹤 Bot 資料夾內非 build／cache 目錄的 C/C++ 原始碼與標頭；引用外部標頭後若需強制更新，可執行 `build_bot.py --rebuild`。

在專案根目錄執行：

```powershell
$matchDir = 'results/cpp-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
python workspace/match.py --away bots/examples/cpp_passive --home bots/examples/minimal.py --seed 42 --regulation-ticks 1200 --output "$matchDir"
python workspace/viewer.py --record "$matchDir"

# 也可指定自己的單一 C++ 檔案；比賽會自動編譯。
# python workspace/match.py --away bots/my_bot/bot.cpp --home bots/base_bot --output results/my-cpp-match

# 單獨建置，只輸出產物路徑：
python workspace/build_bot.py bots/examples/cpp_passive/bot.cpp
```

範例不執行任何棒球動作，仍會依投球時鐘、保送與半局上限結束。它是協定測試，不是策略示範。

## 2. 通訊生命週期

一隊一個持續存活的程序，透過 stdin/stdout 傳遞 **UTF-8 JSONL**：每個封包一行 JSON。每次輸出後都要換行並 flush，不可 pretty-print 成多行，不可把日誌寫到 stdout。診斷使用 stderr。

1. 引擎送 `init`，Bot 回 `ready`。
2. 每次引擎送 `observe`，Bot 回且只回一個 `action` 封包，原樣帶回該次 `decision_id`。
3. 引擎送 `shutdown` 或 stdin EOF，Bot 結束；shutdown 不需要回覆。

`init` 包含 `team_id`（`away`／`home`）、`seed`（uint64 的十進位字串）、`protocol_version`、`capabilities`。capabilities 提供 `field_config`、`physics_config`、`rules_config` 與 `action_types`；以這些設定為準，不要把預設尺寸／速度當成永久常數。

握手回覆必須為：

```json
{"type":"ready","protocol_version":"1.0.0"}
```

`observe` 包含 `decision_id`、`sim_tick`、`team_id`、完整 `state` 與該隊當下的 `legal_action_types`。最小合法回覆如下；decision_id 必須換成剛收到的值：

```json
{"type":"action","protocol_version":"1.0.0","decision_id":"d000000001","actions":[]}
```

每次最多 9 個動作，每名球員最多一個動作；`move` 可同時包含 `catch_enabled`。少送動作不是取消所有意圖：合法的持續意圖會沿用，直到被取代、到達或由階段重置清除。

目前每 tick 提供一次決策機會，120 Hz 下約 **8.33 ms 模擬時間**。兩隊收到同 tick 快照，收齊回覆後才同時套用；沒有依回覆快慢取得先手。這不是每次只能計算 8.33 ms 牆鐘時間；回覆故障 watchdog 為 **2 秒**，啟動握手也須在 watchdog 內完成。

每行 stdout 最多 64 KiB；stderr 累計最多 1 MiB。Windows worker 與 Bot 合計 256 MiB committed memory、最多兩個程序（worker＋Bot），Bot 不應再開子程序。這是資源限制，不是檔案／網路安全沙箱。程序崩潰／超時會中止該場；格式或非法動作會被拒絕，不會由引擎代選策略。

## 3. 座標、球員編號與可見範圍

**可以在每次 observe 知道雙方全部 18 名球員的座標、速度、隊伍與固定編號。**不是只看得到隊友，也不是等回放才取得資料；更新頻率等於決策頻率，沒有另外一條背景即時串流。

`state.players` 每名球員包含：

| 欄位 | 意義 |
| --- | --- |
| `id` | 穩定 ID：`away.P01`～`away.P09`、`home.P01`～`home.P09` |
| `team_id` | `away`／`home`，與 init 的 team_id 相同者是隊友 |
| `role` | 初始角色：P、C、1B、2B、3B、SS、LF、CF、RF；P01～P09 依此對應 |
| `position_q` | `[x,y]`，地面邏輯座標 |
| `velocity_q` | `[vx,vy]`，地面速度 |
| `active_intents` | 已套用且仍持續的公開意圖 |
| `catch_recovery_until_tick` | 接球後恢復截止 tick，期間不可 move／throw／dive |
| `throw_release_tick`／`pending_throw` | 傳球準備截止 tick／已接受的傳球與啟動時跑速；null 表示無準備中的傳球 |
| `dive_until_tick`／`dive_ready_tick`／`catch_ready_tick` | 撲接持續／可再撲接／掉球後可再接的 tick |

同一球員擔任打者或跑者時仍使用原 ID，不產生新的球員。`role` 不代表現在一定站在該位置；跑者以 `state.runners`、當前打者以 `state.batter_id` 辨識。不要把顯示標籤或陣列索引當成 ID。

`state.half == "top"` 時 away 攻、home 守；`"bottom"` 時相反。換半局後 ID 與 team_id 不變。

球位於 `state.ball`：`position_q=[x,y,z]`、`velocity_q=[vx,vy,vz]`、`mode`、`holder_id`（沒有持球者為 null）、`origin`、`has_touched_ground_since_bat`、`fair_foul_status`。球員只有 2D 位置，球有 3D 位置。

座標與速度是 **Q32.32 十進位整數字串**：公尺或 m/s＝整數值／4294967296。用 int64 讀取位置，不能把字串直接當公尺，也不可輸出浮點位置。C++ 內部計算可使用 double；送給引擎的座標仍須轉回合法整數字串。seed 則是 uint64 字串，若轉成整數請用 `std::stoull`，不要用 int64 或浮點承接。

世界原點為本壘，+Y 朝二壘／中外野，+X 朝一壘側，+Z 向上。壘包、牆、矩形可比賽邊界、擊球／好球區與初始站位都在 `capabilities.field_config`。**界外區也可能是合法可比賽範圍**，不可將界外線當成移動牆。

以下程式可放入範例的 observe 分支，僅示範讀取資料：

```cpp
const std::string offense = state.at("half") == "top" ? "away" : "home";
const bool we_are_batting = (offense == team_id);
for (const auto& player : state.at("players")) {
    const std::string id = player.at("id").get<std::string>();
    const bool teammate = player.at("team_id").get<std::string>() == team_id;
    const auto xq = std::stoll(player.at("position_q").at(0).get<std::string>());
    const auto yq = std::stoll(player.at("position_q").at(1).get<std::string>());
    const double x_m = static_cast<double>(xq) / 4294967296.0;
    const double y_m = static_cast<double>(yq) / 4294967296.0;
}
```

觀察不提供引擎私有 `rng_stream_states`、另一個 Bot 的內部記憶體，或對手尚未套用的新回覆。資料是該 tick 的邏輯快照，不是回放畫面的插值／模型偏移。

## 4. 基本規則與狀態

- 九人固定打序，每半局三出局交換；預設每半局最多 10 分或 15 個完成打席。到達比賽時間後，仍公平完成目標局的上下半局；讀取 rules_config 的實際設定。
- 四壞球保送、三好球三振；兩好球後未接殺的界外球不增加第三好球。投手超過投球時鐘未出手，算一次壞球。揮棒每球只能啟動一次，接觸須符合時間窗與幾何。
- 擊球首次落地前被合法接住可接殺，界外飛球亦然；取得滾地球只改持球權，不會直接讓跑者出局。
- 強迫出局須持球有效觸碰目標壘，且早於跑者到壘；其他觸殺需要 tag 意圖與接觸。接殺提前離壘者可能有回壘義務。
- 界外未接殺、HR、傳球出場等依規則成死球／授壘。傳球是實際 3D 飛行，不是指定接球者後直接換持球權。
- 力度、時機、接觸位置與跑速影響物理結果；撲接有持續時間與冷卻。精確參數由 physics_config、rules_config 提供。
- 每打席開始直接把球放回投手，投手／捕手位置重置；**其他守備員保留當前位置**。半局開始重設防守初始站位。
- 每次接球後停在接觸點，速度歸零，恢復 catch_recovery_ticks（預設約 36 ticks）。恢復與傳球準備期間不可移動或再次傳球；hold 不會取消已準備的傳球。傳球方向／力度在接受時固定，跑速誤差依啟動傳球時的速度計算，出手後球正常飛行。死球會取消未出手的傳球。
- 持球移動上限乘 held_speed_multiplier_q（0.8），傳球上限約 28 m/s，跑者上限 8.0～8.5 m/s；實際數值讀取 capabilities。
- 跑者均合法安全停壘且守方持球，連續達 settle_ticks 才收球；有效跑壘／傳球會重置等待。第三出局或明確死球另行結束。

常用狀態欄位：`sim_tick`、`phase`、`inning`、`half`、`score`、`outs`、`balls`、`strikes`、`batter_id`、`swing_used`、`swing_windows`、`runners`、`pending_runs`、`regulation_expired`、`finish_after_inning`。runner 的 `last_legal_base`、`target_base`、`force_obligation`、`retouch_obligation` 等用來表達當下規則義務；null 表示無該目標／義務。

主要階段為 INIT → PLATE_APPEARANCE_SETUP → PITCH_READY → PITCH_IN_FLIGHT；球數未結束時經 PITCH_RESET 再投，擊球成活球時進 BALL_IN_PLAY，接著下一打席或 HALF_TRANSITION，終局為 GAME_OVER／ABORTED。不能把已換階段的上一份命令當成仍合法。

## 5. 可送出的動作

除 noop 外，每個動作都要 `action_id`、`player_id`、`kind`。action_id 為最多 128 字元的 `[A-Za-z0-9_.:-]+`，同批不得重複；player_id 必須是己方球員。表中只列額外欄位，沒有列出的欄位不要加入，未知欄位會遭拒絕。

| kind | 額外欄位 | 主要合法條件／效果 |
| --- | --- | --- |
| pitch | `direction_i32:[dx,dy,dz]`, `power_u16` | PITCH_READY，己方持球投手且在合法投球區；單次釋放 |
| swing | `power_u16`, `azimuth_mdeg`, `elevation_mdeg` | 攻方當前打者、準備／投球階段、此球尚未揮棒；依設定延遲後啟動窗口 |
| take | 無 | 攻方當前打者、準備／投球階段；不啟動揮棒 |
| move | `target_q:[x,y]`，可選 `catch_enabled:bool` | 守方合法可移動階段，持續移動目標；受速度、加速度與邊界限制 |
| catch | `enabled:bool` | 守方合法守備階段，設定持續接球意圖 |
| dive | 無 | 守方 BALL_IN_PLAY、非持球者、冷卻已完成；限時擴大接球範圍 |
| throw | `direction_i32:[dx,dy,dz]`, `power_u16` | 守方 BALL_IN_PLAY 的持球者且恢復已完成；先準備 throw_windup_ticks，再釋放並移除持球權 |
| tag | `runner_id` | 守方活球持球者，對存在的跑者設定觸殺意圖 |
| appeal_return | `runner_id` | 守方活球持球者，對存在跑者提出回壘申訴；須滿足規則接觸條件 |
| run_to_base | `target_base` | 攻方活球跑者，target_base 必須大於 last_legal_base |
| return_to_base | `target_base` | 攻方活球跑者，目標必須符合其 retouch_obligation |
| hold | 無 | 取消己方合法移動／跑壘目標，按物理減速，不能瞬間停下 |
| noop | 只要 `action_id`、`kind`，不含 player_id | 不改變意圖 |

方向各分量夾限在 [-1000000,1000000]，禁止全零；power_u16 夾限 [0,65535]。擊球角為整數毫度，方位夾限 ±80000、仰角 [-15000,75000]，方位 0 朝 +Y、正角朝 +X。`target_q` 是兩個 Q32.32 整數字串。跑壘目標 1／2／3／4 代表一／二／三／本壘；`field_config.bases_q` 索引 0／1／2／3 則是本／一／二／三壘。

每次以 legal_action_types 判斷可用種類，並檢查該球員、持球權、冷卻、跑者義務等條件；清單不保證任意參數／任意球員都合法。完整欄位與型別以 Schema 為準。

單一 move+catch 的格式示例（只示範序列化，不代表建議站位）：

```json
{"type":"action","protocol_version":"1.0.0","decision_id":"d000000123","actions":[{"action_id":"example-123","player_id":"away.P03","kind":"move","target_q":["0","0"],"catch_enabled":true}]}
```

使用時須替換 decision_id、己方 player_id 與自己的動作內容。Bot 可在程序中保留跨 tick 的資料；引擎仍是規則與判決的唯一權威。
