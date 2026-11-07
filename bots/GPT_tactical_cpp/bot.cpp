// C++17 bot designed only from bots/BOT_REFERENCE.md.
// stdout is reserved for one compact, flushed JSON packet per request.
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <string>
#include <vector>

using json = nlohmann::json;
constexpr double Q = 4294967296.0;

struct Vec {
    double x = 0, y = 0, z = 0;
    Vec operator+(Vec b) const { return {x + b.x, y + b.y, z + b.z}; }
    Vec operator-(Vec b) const { return {x - b.x, y - b.y, z - b.z}; }
    Vec operator*(double k) const { return {x * k, y * k, z * k}; }
};

static double distance(Vec a, Vec b) { return std::hypot(a.x - b.x, a.y - b.y); }
static double scalar(const json& j, double fallback = 0) {
    try {
        if (j.is_string()) return std::stod(j.get<std::string>());
        if (j.is_number()) return j.get<double>();
    } catch (const std::exception&) {}
    return fallback;
}
static Vec vectorQ(const json& j, Vec fallback = {}) {
    if (!j.is_array() || j.size() < 2) return fallback;
    auto decode = [](const json& value) {
        // Preserve the full signed Q32.32 integer before converting to metres.
        const std::int64_t raw = value.is_string()
            ? std::stoll(value.get<std::string>()) : value.get<std::int64_t>();
        return static_cast<double>(raw) / Q;
    };
    return {decode(j[0]), decode(j[1]), j.size() > 2 ? decode(j[2]) : 0};
}
static Vec position(const json& j) {
    return j.contains("position_q") ? vectorQ(j["position_q"]) : Vec{};
}
static Vec velocity(const json& j) {
    return j.contains("velocity_q") ? vectorQ(j["velocity_q"]) : Vec{};
}
static std::string stringField(const json& j, const char* key,
                               const std::string& fallback = "") {
    auto it = j.find(key);
    return it != j.end() && it->is_string() ? it->get<std::string>() : fallback;
}
static int integerField(const json& j, const char* key, int fallback = 0) {
    auto it = j.find(key);
    return it == j.end() || it->is_null() ? fallback : static_cast<int>(scalar(*it, fallback));
}
static bool boolField(const json& j, const char* key, bool fallback = false) {
    auto it = j.find(key);
    return it != j.end() && it->is_boolean() ? it->get<bool>() : fallback;
}
static std::string normalized(std::string s) {
    std::string out;
    for (unsigned char c : s) {
        if (c >= 'A' && c <= 'Z') out += static_cast<char>(c - 'A' + 'a');
        else if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) out += c;
    }
    return out;
}

// Configuration is optional at each individual lookup. Q-valued settings are
// decoded at the boundary; all strategy calculations use metres and seconds.
struct Config {
    std::map<std::string, double> numbers;
    std::map<std::string, Vec> vectors;
    void read(const json& node) {
        if (!node.is_object()) return;
        for (auto it = node.begin(); it != node.end(); ++it) {
            const std::string key = normalized(it.key());
            if (it->is_object()) read(*it);
            else if (it->is_number() || it->is_string()) {
                double value = scalar(*it, std::numeric_limits<double>::quiet_NaN());
                if (!key.empty() && key.back() == 'q') value /= Q;
                if (std::isfinite(value)) numbers[key] = value;
            } else if (it->is_array() && it->size() >= 2 &&
                       !key.empty() && key.back() == 'q' &&
                       (it->at(0).is_string() || it->at(0).is_number())) {
                vectors[key] = vectorQ(*it);
            }
        }
    }
    double get(std::initializer_list<const char*> keys, double fallback) const {
        for (auto key : keys) {
            auto it = numbers.find(normalized(key));
            if (it != numbers.end()) return it->second;
        }
        return fallback;
    }
    double matching(const std::vector<std::string>& terms, double fallback) const {
        for (const auto& item : numbers) {
            bool match = true;
            for (const auto& term : terms)
                if (item.first.find(term) == std::string::npos) match = false;
            if (match) return item.second;
        }
        return fallback;
    }
};

struct Runner {
    std::string id;
    Vec pos;
    int last = 0, target = 0, force = 0, retouch = -1;
};

static int baseNumber(const json& value, int fallback) {
    if (value.is_number_integer() || value.is_string()) {
        int base = static_cast<int>(scalar(value, fallback));
        return base >= 0 && base <= 4 ? base : fallback;
    }
    if (value.is_object()) {
        for (const char* key : {"target_base", "base", "base_index", "required_base"})
            if (value.contains(key)) return baseNumber(value[key], fallback);
    }
    return fallback;
}

class Bot {
    std::string team;
    Config cfg;
    std::array<Vec, 4> bases{};
    std::map<std::string, Vec> formation;
    std::map<std::string, json> players;
    std::set<std::string> legal, used;
    json actions = json::array();
    std::uint64_t actionCounter = 0;
    double hz = 120, gravity = 9.81, runSpeed = 7, fieldSpeed = 7;
    double pitchSpeed = 32, throwSpeed = 30, catchHeight = 2.2, catchRadius = 1;
    double swingDelay = 0.05, swingDuration = 0.10, batRadius = 1.2;
    double zoneLow = 0.4, zoneHigh = 1.5;
    Vec contact;
    std::string lastHalf, previousPhase;
    Vec previousBallVelocity;
    int previousTick = -1;
    bool havePitchSample = false;

    bool can(const std::string& kind) const { return legal.count(kind) != 0; }
    bool ours(const std::string& id) const {
        auto it = players.find(id);
        return it != players.end() && stringField(it->second, "team_id") == team;
    }
    void add(const std::string& id, const std::string& kind, json fields = json::object()) {
        if (!can(kind) || !ours(id) || used.count(id) || actions.size() >= 9) return;
        fields["action_id"] = "tc-" + std::to_string(++actionCounter);
        fields["player_id"] = id;
        fields["kind"] = kind;
        actions.push_back(std::move(fields));
        used.insert(id);
    }
    static std::string fixed(double metres) {
        const double limit = static_cast<double>(std::numeric_limits<std::int64_t>::max()) / Q - 1;
        return std::to_string(static_cast<std::int64_t>(
            std::llround(std::clamp(metres, -limit, limit) * Q)));
    }
    void move(const std::string& id, Vec target) {
        // The engine applies the configured playable rectangle. Foul lines are
        // deliberately not treated as movement boundaries.
        add(id, "move", {{"target_q", {fixed(target.x), fixed(target.y)}},
                         {"catch_enabled", true}});
    }
    Vec base(int number) const { return bases[number == 4 ? 0 : std::clamp(number, 0, 3)]; }
    Vec projected(Vec p, Vec v, double seconds) const {
        Vec out = p + v * seconds;
        if (p.z > 0.10 || v.z > 0.10) {
            out.z -= 0.5 * gravity * seconds * seconds;
            out.z = std::max(0.0, out.z);
        } else {
            // Short-horizon rolling estimates are refreshed every observation.
            const double scale = (1 - std::exp(-0.6 * seconds)) / 0.6;
            out.x = p.x + v.x * scale;
            out.y = p.y + v.y * scale;
            out.z = 0;
        }
        return out;
    }
    json direction(Vec from, Vec target, double speed) const {
        Vec delta = target - from;
        const double horizontal = std::hypot(delta.x, delta.y);
        if (horizontal < 0.001) return json::array({0, 0, delta.z >= 0 ? 1000000 : -1000000});
        // Low ballistic arc; iterating accounts for the loss of horizontal
        // speed when the release direction has a vertical component.
        double t = std::max(0.015, horizontal / std::max(1.0, speed));
        for (int i = 0; i < 5; ++i) {
            const double vz = (delta.z + 0.5 * gravity * t * t) / t;
            const double vx = std::sqrt(std::max(speed * speed * 0.16, speed * speed - vz * vz));
            t = horizontal / vx;
        }
        Vec d{delta.x / t, delta.y / t, (delta.z + 0.5 * gravity * t * t) / t};
        const double scale = 900000 / std::max({std::abs(d.x), std::abs(d.y), std::abs(d.z), 0.001});
        return json::array({static_cast<int>(std::lround(d.x * scale)),
                            static_cast<int>(std::lround(d.y * scale)),
                            static_cast<int>(std::lround(d.z * scale))});
    }
    std::vector<Runner> runners(const json& state) const {
        std::vector<Runner> result;
        auto it = state.find("runners");
        if (it == state.end() || (!it->is_array() && !it->is_object())) return result;
        for (auto entry = it->begin(); entry != it->end(); ++entry) {
            const json& r = *entry;
            if (!r.is_object()) continue;
            Runner runner;
            runner.id = stringField(r, "player_id", stringField(r, "id", stringField(r, "runner_id")));
            if (runner.id.empty() && it->is_object()) runner.id = entry.key();
            auto player = players.find(runner.id);
            if (player == players.end()) continue;
            runner.pos = position(player->second);
            runner.last = integerField(r, "last_legal_base");
            if (r.contains("target_base")) runner.target = baseNumber(r["target_base"], 0);
            if (r.contains("force_obligation")) runner.force = baseNumber(r["force_obligation"], 0);
            if (r.contains("retouch_obligation")) runner.retouch = baseNumber(r["retouch_obligation"], -1);
            result.push_back(runner);
        }
        return result;
    }

    void batting(const json& state, const json& ball, const std::string& phase) {
        const std::string batter = stringField(state, "batter_id");
        if (phase == "PITCH_IN_FLIGHT" && !boolField(state, "swing_used") && can("swing")) {
            const Vec p = position(ball), v = velocity(ball);
            const double speed2 = v.x * v.x + v.y * v.y;
            if (speed2 > 1) {
                const double arrival = ((contact.x - p.x) * v.x + (contact.y - p.y) * v.y) / speed2;
                const Vec crossing = projected(p, v, std::max(0.0, arrival));
                const double halfWindow = swingDuration * 0.5;
                const double desired = swingDelay + halfWindow;
                const bool reachable = distance(crossing, contact) <= batRadius &&
                                       crossing.z >= zoneLow - 0.25 && crossing.z <= zoneHigh + 0.25;
                if (reachable && arrival >= swingDelay - 0.5 / hz &&
                    arrival <= desired + 1.5 / hz) {
                    // Aim at the largest gap between defenders in fair territory.
                    int bestAngle = 0;
                    double bestGap = -1;
                    for (int angle : {-34000, -20000, 0, 20000, 34000}) {
                        const double rad = angle * 3.14159265358979323846 / 180000;
                        Vec landing = base(0) + Vec{std::sin(rad), std::cos(rad), 0} * 65;
                        double gap = 1000;
                        for (const auto& item : players)
                            if (!ours(item.first)) gap = std::min(gap, distance(position(item.second), landing));
                        if (gap > bestGap) { bestGap = gap; bestAngle = angle; }
                    }
                    add(batter, "swing", {{"power_u16", 65535}, {"azimuth_mdeg", bestAngle},
                                          {"elevation_mdeg", 24000}});
                }
            }
        }
        if (phase != "BALL_IN_PLAY") return;
        auto active = runners(state);
        std::sort(active.begin(), active.end(), [](const Runner& a, const Runner& b) { return a.last > b.last; });
        const Vec ballPos = position(ball);
        const std::string holder = stringField(ball, "holder_id");
        const bool airborne = !boolField(ball, "has_touched_ground_since_bat", true) &&
                              holder.empty() && ballPos.z > 0.2;
        std::set<int> occupied;
        for (const Runner& r : active) {
            if (!ours(r.id) || r.last >= 4) continue;
            if (r.retouch >= 0 && can("return_to_base")) {
                add(r.id, "return_to_base", {{"target_base", r.retouch}});
                occupied.insert(r.retouch);
                continue;
            }
            const int next = std::clamp(std::max(r.last + 1, r.force), 1, 4);
            const bool mandatory = r.last == 0 || r.force > r.last;
            const double distanceToBase = distance(r.pos, base(next));
            double defenseTime = distance(ballPos, base(next)) / std::max(1.0, throwSpeed) + 0.25;
            if (holder.empty()) {
                double pickup = 1000;
                for (const auto& item : players) {
                    if (!ours(item.first))
                        pickup = std::min(pickup, distance(position(item.second), ballPos) / fieldSpeed);
                }
                defenseTime += pickup;
            }
            const double ourTime = distanceToBase / runSpeed;
            const bool unoccupied = next == 4 || !occupied.count(next);
            const bool advance = mandatory || (unoccupied && !airborne && ourTime + 0.9 < defenseTime);
            if (advance) {
                add(r.id, "run_to_base", {{"target_base", next}});
                if (next < 4) occupied.insert(next);
            } else {
                // Waiting on a fly ball avoids avoidable retouch obligations.
                if (r.target > r.last) add(r.id, "hold");
                occupied.insert(r.last);
            }
        }
    }

    struct OutTarget { int base = 0; std::string runner; double value = -1e9; };

    OutTarget chooseOut(const std::vector<Runner>& active, Vec ballPos) const {
        OutTarget best;
        for (const Runner& r : active) {
            if (ours(r.id) || r.last >= 4) continue;
            const int target = r.retouch >= 0 ? r.retouch : r.force;
            if (target < 0 || target > 4 || (target == 0 && r.retouch < 0)) continue;
            double receiverTime = 1000;
            for (const auto& item : players)
                if (ours(item.first)) receiverTime = std::min(receiverTime, distance(position(item.second), base(target)) / fieldSpeed);
            const double ballTime = distance(ballPos, base(target)) / throwSpeed + 0.15;
            const double runnerTime = distance(r.pos, base(target)) / runSpeed;
            // Prefer attainable outs and the lead runner when the margins tie.
            const double value = runnerTime - std::max(ballTime, receiverTime) + target * 0.04;
            if (value > best.value) best = {target, r.id, value};
        }
        return best;
    }

    void defense(const json& state, const json& ball, const std::string& phase, int tick) {
        const std::string holder = stringField(ball, "holder_id");
        const Vec ballPos = position(ball), ballVelocity = velocity(ball);
        if (phase == "PITCH_READY") {
            if (ours(holder) && stringField(players.at(holder), "role") == "P") {
                Vec target = contact;
                target.z = (zoneLow + zoneHigh) * 0.5;
                add(holder, "pitch", {{"direction_i32", direction(ballPos, target, pitchSpeed)},
                                      {"power_u16", 65535}});
            }
            for (const auto& item : players) {
                if (!ours(item.first) || stringField(item.second, "role") == "P") continue;
                auto home = formation.find(item.first);
                if (home != formation.end()) move(item.first, home->second);
            }
            return;
        }
        if (phase != "BALL_IN_PLAY") return;
        const auto active = runners(state);
        const OutTarget out = chooseOut(active, ballPos);

        std::map<std::string, Vec> targets;
        for (const auto& item : players) {
            if (!ours(item.first)) continue;
            const std::string role = stringField(item.second, "role");
            Vec target = position(item.second);
            auto original = formation.find(item.first);
            if (original != formation.end()) target = original->second;
            if (role == "1B") target = base(1);
            if (role == "2B") target = base(2);
            if (role == "3B") target = base(3);
            if (role == "C") target = base(0);
            targets[item.first] = target;
        }

        if (!holder.empty()) {
            if (ours(holder)) {
                const Vec holderPos = position(players.at(holder));
                bool decided = false;
                if (!out.runner.empty()) {
                    const Vec destination = base(out.base);
                    const double carryTime = distance(holderPos, destination) / fieldSpeed;
                    std::string receiver;
                    double receiverTime = 1000;
                    for (const auto& item : players) {
                        if (!ours(item.first) || item.first == holder) continue;
                        const double t = distance(position(item.second), destination) / fieldSpeed;
                        if (t < receiverTime) { receiverTime = t; receiver = item.first; }
                    }
                    if (!receiver.empty()) targets[receiver] = destination;
                    const double flight = distance(ballPos, destination) / throwSpeed;
                    if (distance(holderPos, destination) <= 0.7 && can("appeal_return")) {
                        for (const Runner& r : active) {
                            if (r.id == out.runner && r.retouch == out.base) {
                                add(holder, "appeal_return", {{"runner_id", r.id}});
                                decided = true;
                            }
                        }
                    }
                    if (!decided && carryTime > flight + 0.3 && receiverTime <= flight + 0.12 &&
                        distance(ballPos, destination) > 3 && can("throw")) {
                        Vec aim = destination;
                        aim.z = std::clamp(ballPos.z, 0.6, 1.3);
                        add(holder, "throw", {{"direction_i32", direction(ballPos, aim, throwSpeed)},
                                             {"power_u16", 65535}});
                        decided = true;
                    }
                    if (!decided) { move(holder, destination); decided = true; }
                }
                if (!decided) {
                    const Runner* nearest = nullptr;
                    double separation = 1000;
                    for (const Runner& r : active) {
                        if (ours(r.id) || r.last >= 4) continue;
                        // A runner standing on the last legal base is safe.
                        if (distance(r.pos, base(r.last)) < 1.0) continue;
                        double d = distance(holderPos, r.pos);
                        if (d < separation) { separation = d; nearest = &r; }
                    }
                    if (nearest && separation <= catchRadius + 0.35 && can("tag"))
                        add(holder, "tag", {{"runner_id", nearest->id}});
                    else if (nearest && separation < 5)
                        move(holder, nearest->pos);
                    else if (can("hold")) add(holder, "hold");
                }
            }
        } else {
            // Find the earliest reachable point along the current trajectory.
            // Replanning each tick also corrects bounce and drag approximation.
            std::vector<std::pair<double, std::string>> candidates;
            std::map<std::string, Vec> intercepts;
            for (const auto& item : players) {
                if (!ours(item.first)) continue;
                const Vec fielder = position(item.second);
                double earliest = 8;
                Vec intercept = ballPos;
                double bestMiss = 1e9;
                for (double t = 0; t <= 5.0; t += 0.04) {
                    const Vec predicted = projected(ballPos, ballVelocity, t);
                    const double miss = distance(fielder, predicted) - fieldSpeed * std::max(0.0, t - 0.10);
                    if (predicted.z <= catchHeight && miss < bestMiss) {
                        bestMiss = miss;
                        intercept = predicted;
                    }
                    if (predicted.z <= catchHeight && miss <= catchRadius) {
                        earliest = t;
                        intercept = predicted;
                        break;
                    }
                }
                if (earliest == 8) earliest += std::max(0.0, bestMiss) / fieldSpeed;
                candidates.push_back({earliest, item.first});
                intercepts[item.first] = intercept;
            }
            std::sort(candidates.begin(), candidates.end());
            const std::size_t chasers = std::min<std::size_t>(2, candidates.size());
            for (std::size_t i = 0; i < chasers; ++i) {
                const std::string& id = candidates[i].second;
                targets[id] = intercepts[id];
                const json& player = players.at(id);
                const double separation = distance(position(player), ballPos);
                if (i == 0 && separation > catchRadius && separation < catchRadius + 0.8 &&
                    ballPos.z <= catchHeight && can("dive") &&
                    integerField(player, "dive_ready_tick") <= tick &&
                    integerField(player, "dive_until_tick") <= tick &&
                    integerField(player, "catch_ready_tick") <= tick) {
                    // First ensure a catch intent exists; dive itself cannot
                    // carry catch_enabled under the action schema.
                    const auto intent = player.find("active_intents");
                    const bool catching = intent != player.end() && intent->is_object() &&
                                          boolField(*intent, "catch_enabled");
                    if (catching) add(id, "dive");
                }
            }
        }
        for (const auto& item : targets)
            if (item.first != holder) move(item.first, item.second);
    }

public:
    void init(const json& packet) {
        team = stringField(packet, "team_id");
        json capabilities = packet.value("capabilities", json::object());
        cfg.read(capabilities);
        hz = std::max(1.0, cfg.get({"tick_rate", "tick_hz", "ticks_per_second", "simulation_hz"},
                                  cfg.matching({"tick", "rate"}, 120)));
        gravity = std::abs(cfg.get({"gravity_q", "gravity_mps2_q", "gravity"}, 9.81));
        runSpeed = std::max(1.0, cfg.get({"runner_speed_q", "run_speed_q", "player_max_speed_q", "player_speed_q"}, 7));
        fieldSpeed = std::max(1.0, cfg.get({"fielder_speed_q", "fielder_max_speed_q", "player_max_speed_q", "player_speed_q"}, runSpeed));
        pitchSpeed = std::max(1.0, cfg.matching({"pitch", "max", "speed"},
                                   cfg.get({"pitch_speed_q", "pitch_speed_max_q"}, 32)));
        throwSpeed = std::max(1.0, cfg.matching({"throw", "max", "speed"},
                                   cfg.get({"throw_speed_q", "throw_speed_max_q"}, 30)));
        catchHeight = std::max(0.2, cfg.get({"catch_height_q", "catch_max_height_q", "fielder_catch_height_q"}, 2.2));
        catchRadius = std::max(0.1, cfg.get({"catch_radius_q", "fielder_catch_radius_q"}, 1));
        swingDelay = std::max(0.0, cfg.matching({"swing", "delay", "tick"}, 6) / hz);
        swingDuration = std::max(1.0 / hz, cfg.matching({"swing", "window", "tick"}, 12) / hz);
        batRadius = std::max(0.1, cfg.get({"bat_contact_radius_q", "swing_radius_q", "contact_radius_q"}, 1.2));
        zoneLow = cfg.get({"strike_zone_z_min_q", "strike_zone_min_z_q", "strike_zone_bottom_q"}, 0.4);
        zoneHigh = cfg.get({"strike_zone_z_max_q", "strike_zone_max_z_q", "strike_zone_top_q"}, 1.5);
        if (zoneHigh < zoneLow) std::swap(zoneHigh, zoneLow);

        // Bases are defined by the public field configuration, in home/1/2/3 order.
        json field = capabilities.value("field_config", json::object());
        if (field.contains("bases_q") && field["bases_q"].is_array() && field["bases_q"].size() >= 4) {
            for (int i = 0; i < 4; ++i) bases[i] = vectorQ(field["bases_q"][i]);
        }
        contact = base(0);
        for (const char* key : {"bat_contact_center_q", "contact_center_q", "batting_zone_center_q"}) {
            auto it = cfg.vectors.find(normalized(key));
            if (it != cfg.vectors.end()) { contact = it->second; break; }
        }
        formation.clear();
        lastHalf.clear();
        previousPhase.clear();
        previousTick = -1;
        havePitchSample = false;
    }

    json observe(const json& packet) {
        actions = json::array();
        legal.clear();
        used.clear();
        players.clear();
        if (packet.contains("legal_action_types") && packet["legal_action_types"].is_array())
            for (const auto& kind : packet["legal_action_types"])
                if (kind.is_string()) legal.insert(kind.get<std::string>());
        const json& state = packet.at("state");
        if (state.contains("players") && state["players"].is_array())
            for (const auto& player : state["players"])
                if (player.is_object()) players[stringField(player, "id")] = player;
        const std::string half = stringField(state, "half");
        const std::string phase = stringField(state, "phase");
        const bool offense = (half == "top" ? "away" : "home") == team;
        const int tick = integerField(packet, "sim_tick", integerField(state, "sim_tick"));
        const json ball = state.value("ball", json::object());
        if (half != lastHalf) {
            formation.clear();
            lastHalf = half;
        }
        if (!offense && formation.empty() &&
            (phase == "PITCH_READY" || phase == "PITCH_IN_FLIGHT" || phase == "PLATE_APPEARANCE_SETUP")) {
            for (const auto& item : players)
                if (ours(item.first)) formation[item.first] = position(item.second);
        }
        if (phase == "PITCH_IN_FLIGHT") {
            const Vec v = velocity(ball);
            const double speed = std::sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
            if (!offense && previousPhase == "PITCH_READY" && speed > 1) pitchSpeed = speed;
            if (havePitchSample && previousPhase == phase && tick > previousTick) {
                const double g = (previousBallVelocity.z - v.z) * hz / (tick - previousTick);
                if (g > 0.01 && g < 100) gravity = gravity * 0.9 + g * 0.1;
            }
            previousBallVelocity = v;
            havePitchSample = true;
        } else havePitchSample = false;
        if (offense) batting(state, ball, phase);
        else defense(state, ball, phase, tick);
        previousPhase = phase;
        previousTick = tick;
        return actions;
    }
};

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    Bot bot;
    std::string line;
    while (std::getline(std::cin, line)) {
        json packet = json::parse(line, nullptr, false);
        if (packet.is_discarded() || !packet.is_object()) continue;
        const std::string type = stringField(packet, "type");
        if (type == "shutdown") break;
        if (type == "init") {
            try { bot.init(packet); }
            catch (const std::exception& e) { std::cerr << "init: " << e.what() << '\n'; }
            std::cout << json({{"type", "ready"}, {"protocol_version", "1.0.0"}}).dump()
                      << '\n' << std::flush;
        } else if (type == "observe") {
            json actions = json::array();
            try { actions = bot.observe(packet); }
            catch (const std::exception& e) { std::cerr << "observe: " << e.what() << '\n'; }
            json response = {{"type", "action"}, {"protocol_version", "1.0.0"},
                             {"decision_id", packet.value("decision_id", json(nullptr))},
                             {"actions", std::move(actions)}};
            std::cout << response.dump() << '\n' << std::flush;
        }
    }
}
