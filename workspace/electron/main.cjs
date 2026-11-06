'use strict';
const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const ROOT = path.resolve(__dirname, '..');
const acceptance = process.argv.includes('--background-test');
if(acceptance)app.commandLine.appendSwitch('force-device-scale-factor','1');
const userData=path.join(ROOT,'build',acceptance?'viewer-test-data':'viewer-user-data');
require('node:fs').mkdirSync(userData,{recursive:true});
app.setPath('userData',userData);
app.setPath('sessionData',path.join(userData,'session'));
const VIEWER_URL = pathToFileURL(path.join(ROOT, 'viewer.html')).href;
let window, worker, selection = null, metadata = null, cacheRoot = null, requestId = 0;
let loading = null;
const pending = new Map();

function send(channel, value) { if (window && !window.isDestroyed()) window.webContents.send(channel, value); }
function checkSender(event) {
  if (!window || event.sender !== window.webContents || event.senderFrame?.url !== VIEWER_URL) throw new Error('Unauthorized IPC sender');
}
function stopWorker(reason = '已取消重算') {
  const previous = worker; worker = null;
  if (previous) previous.kill();
  if (loading) { loading.reject(new Error(reason)); loading = null; }
  for (const item of pending.values()) item.reject(new Error(reason));
  pending.clear();
}
async function ensureCache(root) {
  for (const relative of ['cache', path.join('cache', 'frames')]) {
    const target = path.join(root, relative);
    try { if ((await fs.lstat(target)).isSymbolicLink()) throw new Error('記錄內 cache 不可為符號連結'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    await fs.mkdir(target, { recursive: true });
    const actual = await fs.realpath(target);
    if (!actual.toLowerCase().startsWith(root.toLowerCase() + path.sep)) throw new Error('快取路徑超出記錄目錄');
  }
  return path.join(root, 'cache', 'frames');
}
async function loadDirectory(directory) {
  const root = await fs.realpath(directory);
  if (!(await fs.stat(root)).isDirectory()) throw new Error('請選取一場比賽的記錄目錄');
  stopWorker('切換記錄'); metadata = null; selection = root; cacheRoot = await ensureCache(root);
  send('record:progress', { sim_tick: 0, total_ticks: 0, message: '檢查版本、完整性與動作索引…' });
  const process = spawn(global.process.env.BASEBALL_PYTHON || 'python', [path.join(ROOT, 'viewer_worker.py'), '--input', root], {
    cwd: ROOT, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
  });
  worker = process;
  let buffer = '', diagnostic = '';
  const promise = new Promise((resolve, reject) => { loading = { resolve, reject }; });
  process.stderr.on('data', data => { diagnostic = (diagnostic + data.toString('utf8')).slice(-4096); });
  process.stdout.setEncoding('utf8');
  process.stdout.on('data', text => {
    if (worker !== process) return;
    buffer += text;
    if (buffer.length > 8 * 1024 * 1024) { fail('重算輸出過大'); return; }
    let newline;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
      try {
        const packet = JSON.parse(line);
        if (packet.type === 'progress') send('record:progress', packet);
        else if (packet.type === 'loaded') {
          metadata = packet.metadata;
          if (metadata.format !== 'bb-frames-v1' || metadata.cache_status !== 'ready') throw new Error('不支援的影格快取');
          const data = current(); send('record:loaded', data);
          if (loading) { loading.resolve(data); loading = null; }
        } else if (packet.type === 'seek_result' || packet.type === 'request_error') {
          const item = pending.get(packet.id); if (!item) continue;
          pending.delete(packet.id);
          if (packet.type === 'seek_result') item.resolve(packet);
          else item.reject(new Error(JSON.stringify(packet.report)));
        } else if (packet.type === 'error') fail(JSON.stringify(packet.report));
      } catch (error) { fail(error.message); return; }
    }
  });
  function fail(reason) {
    if (worker !== process) return;
    send('record:error', String(reason).slice(0, 4096));stopWorker(reason);
  }
  process.on('error', error => fail(`無法啟動 Python：${error.message}`));
  process.on('exit', code => { if (worker === process) fail(`重算程序已結束 (${code}) ${diagnostic}`); });
  return promise;
}
function current() { return metadata ? { name: path.basename(selection), metadata } : null; }
function handle(channel, callback) { ipcMain.handle(channel, (event, ...args) => { checkSender(event); return callback(...args); }); }
handle('record:open', async () => {
  const result = await dialog.showOpenDialog(window, { title: '選取 results 內的一場比賽', properties: ['openDirectory'] });
  return result.canceled ? null : loadDirectory(result.filePaths[0]);
});
handle('record:reload', () => selection ? loadDirectory(selection) : null);
handle('record:current', current);
handle('record:cancel', () => { stopWorker();metadata=null; return true; });
handle('record:chunk', async index => {
  if (!metadata || !Number.isInteger(index) || index < 0 || index >= metadata.chunks.length) throw new Error('無效的影格區塊');
  const expected=metadata.chunks[index].sha256;
  const filename = path.join(cacheRoot, `chunk-${String(index).padStart(6, '0')}.json`);
  if ((await fs.lstat(filename)).isSymbolicLink() || (await fs.stat(filename)).size > 12 * 1024 * 1024) throw new Error('不安全的快取區塊');
  const bytes = await fs.readFile(filename);
  if (crypto.createHash('sha256').update(bytes).digest('hex') !== expected) throw new Error('快取損壞，請重新載入重建');
  return JSON.parse(bytes.toString('utf8'));
});
handle('record:seek', tick => {
  if (!worker || !metadata || !Number.isInteger(tick) || tick < 0 || tick > metadata.total_ticks || pending.size >= 64) throw new Error('無效的定位要求');
  const id = ++requestId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.stdin.write(JSON.stringify({ id, type: 'seek', tick }) + '\n', error => { if (error) { pending.delete(id); reject(error); } });
  });
});
handle('viewer:profile', async () => {
  const file = path.join(ROOT, '..', 'model', 'visual_profiles', 'default.json');
  const {validateProfile,DEFAULT_PROFILE}=require('../viewer/profile.cjs');
  try { return validateProfile(JSON.parse(await fs.readFile(file, 'utf8'))); }
  catch { return {...structuredClone(DEFAULT_PROFILE),load_warning:'視覺設定無效或缺少，使用基本幾何'}; }
});
app.whenReady().then(() => {
  window = new BrowserWindow({ width: acceptance?1920:1450, height: acceptance?1080:960, show:!acceptance, frame:!acceptance, minWidth: 1100, minHeight: 760, backgroundColor: '#08151b', title: 'Diamond · 棒球 Bot 回放',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true, offscreen:acceptance, backgroundThrottling:!acceptance },
  });
  window.removeMenu();
  if(acceptance)window.setContentSize(1920,1080);
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (url !== VIEWER_URL) event.preventDefault(); });
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
  window.webContents.on('did-finish-load', () => {
    if(acceptance){
      require('./background-test.cjs').run({window,loadDirectory,getMetadata:()=>metadata,stopWorker,root:ROOT})
        .then(()=>app.exit(0)).catch(error=>{console.error(error.stack);app.exit(1);});
      return;
    }
    const index = global.process.argv.indexOf('--record');
    if (!selection && index >= 0 && global.process.argv[index + 1]) loadDirectory(path.resolve(global.process.argv[index + 1])).catch(error => send('record:error', error.message));
  });
  window.loadFile(path.join(ROOT, 'viewer.html'));
});
app.on('window-all-closed', () => { stopWorker(); app.quit(); });
app.on('before-quit', () => stopWorker());
