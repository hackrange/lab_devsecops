// A network "ping" helper.  Taint flows from the query string (source) to a shell (sink).
import http from 'node:http';
import { exec } from 'node:child_process';

http.createServer((req, res) => {
  const host = new URL(req.url, 'http://localhost').searchParams.get('host');
  exec(`ping -c 1 ${host}`, (err, stdout) => res.end(stdout || String(err)));
}).listen(3002, '127.0.0.1');
