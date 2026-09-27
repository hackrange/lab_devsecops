// Looks validated.  Is it?  The pattern matches any string with one character in it.
import http from 'node:http';
import { exec } from 'node:child_process';

const HOST = /./;

http.createServer((req, res) => {
  const host = new URL(req.url, 'http://localhost').searchParams.get('host') ?? '';
  if (!HOST.test(host)) {
    res.writeHead(400);
    return res.end('bad host');
  }
  exec(`ping -c 1 ${host}`, (err, stdout) => res.end(stdout || 'unreachable'));
}).listen(3002, '127.0.0.1');
