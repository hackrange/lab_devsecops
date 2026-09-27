// execFile passes arguments as an array, so no shell ever parses them, and the
// host is validated against a strict pattern first.
import http from 'node:http';
import { execFile } from 'node:child_process';

const HOST = /^[a-z0-9.-]{1,253}$/i;

http.createServer((req, res) => {
  const host = new URL(req.url, 'http://localhost').searchParams.get('host') ?? '';
  if (!HOST.test(host)) {
    res.writeHead(400);
    return res.end('bad host');
  }
  execFile('ping', ['-c', '1', host], (err, stdout) => res.end(stdout || 'unreachable'));
}).listen(3002, '127.0.0.1');
