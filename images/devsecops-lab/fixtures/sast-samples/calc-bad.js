// A "calculator" endpoint.  Reads ?expr=... and evaluates it.  What could go wrong?
import http from 'node:http';

http.createServer((req, res) => {
  const expr = new URL(req.url, 'http://localhost').searchParams.get('expr') ?? '0';
  const result = eval(expr);                    // user input becomes code
  res.end(JSON.stringify({ result }));
}).listen(3001, '127.0.0.1');
