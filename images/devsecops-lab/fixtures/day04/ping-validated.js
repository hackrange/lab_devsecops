// Still uses exec (a shell), but only after the host passes a strict allowlist
// pattern.  A taint rule that trusts HOST.test() as a sanitizer lets this pass.
import http from 'node:http';
import { exec } from 'node:child_process';

const HOST = /^[a-z0-9.-]{1,253}$/i;

http.createServer((req, res) => {
  const host = new URL(req.url, 'http://localhost').searchParams.get('host') ?? '';
  if (!HOST.test(host)) {
    res.writeHead(400);
    return res.end('bad host');
  }
  exec(`ping -c 1 ${host}`, (err, stdout) => res.end(stdout || 'unreachable'));
}).listen(3002, '127.0.0.1');
