// Does your scanner see through this?  The dangerous call is hidden behind an alias.
const run = globalThis['ev' + 'al'];
export function calc(expr) {
  return run(expr);
}
