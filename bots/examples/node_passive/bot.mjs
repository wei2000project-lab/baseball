import readline from 'node:readline';
const lines = readline.createInterface({input:process.stdin, crlfDelay:Infinity});
for await (const line of lines) {
  const m = JSON.parse(line);
  if (m.type === 'shutdown') break;
  const reply = m.type === 'init'
    ? {type:'ready', protocol_version:'1.0.0'}
    : {type:'action', protocol_version:'1.0.0', decision_id:m.decision_id, actions:[]};
  process.stdout.write(JSON.stringify(reply)+'\n');
}
