// Electron 45 exposes an explicit installer instead of an npm postinstall.
const path=require('node:path');
process.env.electron_config_cache=path.resolve(__dirname,'../build/electron-cache');
require('../node_modules/electron/install.js');
