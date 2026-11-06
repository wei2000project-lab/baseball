# C++ JSON dependency

Vendored unmodified `nlohmann/json` **v3.11.3**, under MIT (see nlohmann/LICENSE.MIT).

- Upstream release: https://github.com/nlohmann/json/releases/tag/v3.11.3
- Header: https://raw.githubusercontent.com/nlohmann/json/v3.11.3/single_include/nlohmann/json.hpp
- SHA-256: `9bea4c8066ef4a1c206b2be5a36302f8926f7fdc6087af5d20b417d0cf103ea6` (verified against upstream release).

`build_bot.py` adds this directory to the C++ include path. Bots may use
`#include <nlohmann/json.hpp>` without fetching a package at match startup.
