// Protocol-only example. No batting, fielding or running strategy.
#include <iostream>
#include <string>
#include <nlohmann/json.hpp>

using Json = nlohmann::json;

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    std::string line, team_id;
    Json capabilities;
    try {
        while (std::getline(std::cin, line)) {
            const Json message = Json::parse(line);
            const std::string type = message.at("type").get<std::string>();
            if (type == "shutdown") break;
            Json reply;
            if (type == "init") {
                team_id = message.at("team_id").get<std::string>();
                const std::string seed = message.at("seed").get<std::string>();
                capabilities = message.at("capabilities");
                reply = {{"type", "ready"}, {"protocol_version", "1.0.0"}};
            } else if (type == "observe") {
                const Json& state = message.at("state");
                // state["players"]: both teams' stable IDs, roles, Q32.32
                // positions and velocities; state["ball"]: position/velocity.
                // Add your own decision function here. Empty actions are legal.
                const Json actions = Json::array();
                reply = {{"type", "action"}, {"protocol_version", "1.0.0"},
                         {"decision_id", message.at("decision_id")}, {"actions", actions}};
            } else {
                std::cerr << "unsupported message type\n";
                return 2;
            }
            std::cout << reply.dump() << '\n' << std::flush;
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
