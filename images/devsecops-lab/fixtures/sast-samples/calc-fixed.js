// The same endpoint, rebuilt so user input can only ever be data.
import http from 'node:http';

const OPS = { add: (a, b) => a + b, sub: (a, b) => a - b, mul: (a, b) => a * b };

http.createServer((req, res) => {
  const q = new URL(req.url, 'http://localhost').searchParams;
  const op = OPS[q.get('op')];
  const a = Number(q.get('a'));
  const b = Number(q.get('b'));
  if (!op || !Number.isFinite(a) || !Number.isFinite(b)) {
    res.writeHead(400);
    return res.end(JSON.stringify({ error: 'Invalid request' }));
  }
  res.end(JSON.stringify({ result: op(a, b) }));
}).listen(3001, '127.0.0.1');
