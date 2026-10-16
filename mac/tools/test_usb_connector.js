/* Run the production connector default against known internal and USB-C ports. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../Resources/app.js'), 'utf8');
const defaults = source.slice(source.indexOf('const CONN ='), source.indexOf('const U ='));
const context = vm.createContext({});
vm.runInContext(defaults, context);
const choose = (port) => { context.port = port; return vm.runInContext('usbConnectorDefault(port)', context); };
for (const connector of [0, 3, 9, 10, 255]) {
  assert.equal(choose({ connectorKnown: true, connector, usb3: connector !== 3 }), connector);
}
assert.equal(choose({ connectorKnown: false, connector: 255, usb3: true }), 3);
assert.equal(choose({ connectorKnown: false, connector: 255, usb3: false }), 0);
assert.equal(choose({ connectorKnown: true, connector: 7, usb3: true }), 3);
assert.equal(choose({ usb3: true }), 3);
assert.equal(choose({ usb3: false }), 0);
console.log('Known internal/USB-C metadata preserved; unknown/invalid metadata keeps existing fallback.');
