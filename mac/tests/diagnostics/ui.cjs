const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
const html = fs.readFileSync(process.argv[3], 'utf8');
const nodes = new Map();
for (const id of ['od', 'dr', 'odr', 'drr', 'sl', 'slr']) assert(html.includes(`id="${id}"`));
function node(id) {
  if (!nodes.has(id)) nodes.set(id, { textContent: '', innerHTML: '', disabled: false, hidden: true,
    options: [], classList: { toggle() {} }, querySelectorAll() { return []; }, insertAdjacentHTML() {} });
  return nodes.get(id);
}
const messages = [], window = { webkit: { messageHandlers: { nm: { postMessage(m) { messages.push(m); } } } } };
const context = vm.createContext({ window, document: { getElementById: node, querySelectorAll() { return []; } }, confirm() { return false; }, setTimeout() {} });
vm.runInContext(source, context);
assert.deepStrictEqual(messages.map(m => m.act), ['scan']);
node('od').onclick(); assert.strictEqual(messages.at(-1).act, 'optionalDiagnostics');
assert(!messages.some(m => /trace|capture|install|sendLogs/i.test(m.act)));
const hostile = '<img src=x onerror=fetch("secret")>';
window.NM.on({ event: 'diagnosticsStatus', data: { text: hostile } });
assert.strictEqual(node('odr').textContent, hostile); assert.strictEqual(node('odr').innerHTML, '');
node('dr').onclick(); assert.strictEqual(messages.at(-1).act, 'importDiagnosticReceipt');
window.NM.on({ event: 'diagnosticReceipt', data: { text: hostile } });
assert.strictEqual(node('drr').textContent, hostile); assert.strictEqual(node('drr').innerHTML, '');
assert(!messages.some(m => m.act === 'sendLogs'));
node('sl').onclick(); assert.strictEqual(messages.at(-1).act, 'sendLogs');
window.NM.on({ event: 'logsDone', data: { ok: false, errors: [], why: 'Not sent.' } });
assert.strictEqual(node('sl').disabled, false);
assert(html.includes('Capture is unavailable in this version') && html.includes('separate Send logs confirmation') && html.includes('Check optional diagnostics'));
for (const jargon of ['mutable resources', 'privileged installer', 'kernel integrity', 'control-port']) assert(!html.includes(jargon));
console.log('PASS: real UI script requires explicit actions, receipt import never sends, status text is inert, and ordinary Send logs remains separate.');
