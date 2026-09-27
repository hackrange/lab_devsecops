// TRAINING FIXTURE.  This runs automatically at install time, the way a real
// malicious postinstall script would.  It sends NOTHING anywhere.  It only
// writes a report in your home directory showing what it COULD have taken.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const home = os.homedir();
const interesting = ['.npmrc', '.ssh/id_rsa', '.ssh/id_ed25519', '.aws/credentials', '.config/gh/hosts.yml', '.git-credentials'];
const found = interesting.filter((f) => fs.existsSync(path.join(home, f)));
const envNames = Object.keys(process.env).filter((k) => !/^npm_/.test(k) && /TOKEN|SECRET|KEY|PASS|AWS|GITHUB|NPM/i.test(k));

const report = [
  'evil-helper postinstall ran at ' + new Date().toISOString(),
  'user: ' + os.userInfo().username + '  host: ' + os.hostname() + '  cwd: ' + process.cwd(),
  'credential files it could read: ' + (found.join(', ') || '(none found)'),
  'secret-looking env var NAMES it could read: ' + (envNames.join(', ') || '(none)'),
  'A real attack would now send these to a server it controls.  This one stops here.',
].join('\n');
fs.writeFileSync(path.join(home, 'EVIL-HELPER-WAS-HERE.txt'), report + '\n');
console.log('[evil-helper] postinstall finished (see ~/EVIL-HELPER-WAS-HERE.txt)');
