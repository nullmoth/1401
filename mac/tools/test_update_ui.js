const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const elements = new Map();
const sent = [];
function element(id) {
  if (!elements.has(id)) elements.set(id, { hidden: false, disabled: false, value: '', textContent: '', innerHTML: '', options: [], classList: { toggle() {} }, insertAdjacentHTML() {}, querySelectorAll() { return [] } });
  return elements.get(id);
}
const sandbox = {document: {getElementById: element, querySelectorAll() {return []}}, window: {webkit: {messageHandlers: {nm: {postMessage(m) {sent.push(m)}}}}}, confirm: () => true, setTimeout};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname + '/../Resources/app.js', 'utf8'), sandbox);
const event = (event, data) => sandbox.window.NM.on({event, data});
event('upd', {state:'checked', newer:true, latest:'1.0.9', installed:'1.0.8'});
assert.equal(element('upddrv').disabled,false);
event('dl', {state:'start'});
for (const name of ['dl','updchk','upddrv']) assert.equal(element(name).disabled,true);
event('dl', {state:'error', why:'network failed'});
for (const name of ['dl','updchk','upddrv']) assert.equal(element(name).disabled,false);
event('dl', {state:'start'});
event('dl', {state:'done',path:'/tmp/driver.tar.gz'});
assert.equal(element('updchk').disabled,false);
assert.equal(sent.at(-1).act,'scan');
event('upd', {state:'checked', newer:false, latest:'1.0.8', installed:'1.0.8'});
assert.equal(element('upddrv').hidden,true);
assert.equal(element('upddrv').disabled,true);
console.log('Update download failure, retry, completion and version controls passed.');

const machine = (major) => ({version:'1.1', macos:String(major), major, arch:'x86_64', translated:false,
  gpus:[{vendor:'10DE', name:'NVIDIA RTX 5060', supported:true, tested:true}],
  kexts:4, metal:['NVIDIA RTX 5060'], opencore:'1.0.6', files:true,
  packages:[{ok:'yes',path:'/tmp/driver.tar.gz'}]});
// The Tahoe button (back in 2.0.4, now that Tahoe is released): offered on macOS 15 with the checked package only
event('scan',machine(15));
assert(element('verdict').innerHTML.includes('Check for a newer driver'));
assert(element('verdict').innerHTML.includes('Prepare this Mac for Tahoe'));
assert.equal(element('upd').disabled,false);
event('scan',machine(26));
assert(!element('verdict').innerHTML.includes('Prepare'));
assert.equal(element('upd').disabled,true);
assert(element('updt').innerHTML.includes('already runs macOS 26'));
const nopkg = machine(15); nopkg.packages = [];
event('scan',nopkg);
assert.equal(element('upd').disabled,true);
assert(element('updt').innerHTML.includes('Download the driver package'));
event('scan',machine(15));
element('upd').onclick();
assert.deepEqual({act:sent.at(-1).act, cancel:sent.at(-1).cancel, pkg:sent.at(-1).pkg}, {act:'osupdate', cancel:false, pkg:'/tmp/driver.tar.gz'});
element('updc').onclick();
assert.deepEqual({act:sent.at(-1).act, cancel:sent.at(-1).cancel}, {act:'osupdate', cancel:true});
event('run',{state:'start', mode:'tahoe'});
assert.equal(element('upd').disabled,true);
event('run',{state:'end', mode:'tahoe', ok:true});
assert.equal(element('swu').hidden,false);
element('swu').onclick();
assert.equal(sent.at(-1).act,'swupdate');
event('run',{state:'end', mode:'tahoe', ok:false});
assert(element('updt').textContent.includes('stopped'));
// A Mac whose only GPU OpenCore switched off has an empty GPU list (Core Ultra laptop, 2.0.3): it is pointed at the
// test driver, not told to look for an NVIDIA card; -wegnoegpu (which hides the NVIDIA card) keeps its own advice.
const bare = (extra) => Object.assign(machine(15), {gpus:[], kexts:0, metal:[], files:false, hwModel:'MacBookPro16,2', gpuHiding:[], hiddenNvidia:[]}, extra);
event('scan',bare({}));
assert(element('verdict').innerHTML.includes('sees no GPU at all'));
assert(!element('verdict').innerHTML.includes('No NVIDIA card was found'));
event('scan',bare({gpuHiding:['-wegnoigpu']}));
assert(element('verdict').innerHTML.includes('-wegnoigpu in boot-args'));
event('scan',bare({gpuHiding:['-wegnoegpu']}));
assert(!element('verdict').innerHTML.includes('sees no GPU at all'));
assert(element('verdict').innerHTML.includes('-wegnoegpu'));
console.log('A Mac with no visible GPU is offered the test driver; NVIDIA-hiding boot-args keep their advice.');
const html=fs.readFileSync(__dirname+'/../Resources/index.html','utf8');
for (const name of ['upd','swu','updc']) assert(html.includes('id="'+name+'"'));
const native=fs.readFileSync(__dirname+'/../Sources/main.swift','utf8');
assert(native.includes('case "osupdate":'));
assert(native.includes('case "swupdate":'));
assert(native.includes('extra: ["--update", "prepare"]'));
assert(native.includes('extra: ["--update", "cancel"]'));
assert(native.includes('"tahoe", "tahoecancel"].contains(mode)'));
assert(native.includes('AppActions.directRunMode(b["mode"])'));
console.log('Tahoe preparation: offered on macOS 15 with the package, refused on 26 and without it, prepare/cancel/Software Update wired.');

event('run',{state:'done', mode:'dry', ok:true});
element('efi').value='disk2s1';
element('efi').onchange();
assert.equal(element('go').disabled,true);
assert.equal(vm.runInContext('S.previewed',sandbox),false);
console.log('Changing the selected EFI requires a fresh preview before install.');

// The install button says why it is greyed out (10-13: "Install Driver is greyed out, what do I do").
const fresh = () => Object.assign(machine(15), {kexts:0, metal:[], files:false});
event('scan', fresh());
assert.equal(element('go').disabled, true);
assert(element('go').textContent.includes('Show me the changes first'), element('go').textContent);
event('run', {state:'start', mode:'dry'});
event('run', {state:'done', mode:'dry', ok:true});
event('scan', fresh());
assert.equal(element('go').disabled, false);
assert.equal(element('go').textContent, 'Install the driver');
console.log('Install button names the step that comes first, and reads plainly once it is ready.');

// A macOS update that skipped "Prepare this Mac for Tahoe" leaves the driver parked (1401 #484): the page says the macOS
// changed, instead of "installed but not running, restart".
const updated = machine(26); updated.files = true; updated.kexts = 0; updated.metal = []; updated.driverOsMajor = 15;
event('scan', updated);
assert(element('verdict').innerHTML.includes('updated from 15 to 26'), element('verdict').innerHTML);
assert(!element('verdict').innerHTML.includes('installed but not running'));
const same = machine(26); same.files = true; same.kexts = 0; same.metal = []; same.driverOsMajor = 26;
event('scan', same);
assert(element('verdict').innerHTML.includes('installed but not running'));
const unknown = machine(26); unknown.files = true; unknown.kexts = 0; unknown.metal = [];
event('scan', unknown);
assert(element('verdict').innerHTML.includes('installed but not running'));
console.log('A macOS update after the driver was set up is named; a Mac with no record or the same macOS keeps the old advice.');

// The facts the kext publishes on the card are shown: the BAR window it got, Resizable BAR, Above 4G, link power.
const facts = machine(26); facts.gpus[0].nvrm = {'nvrm-bar1-mb': 8192, 'nvrm-bar1-firmware-mb': 16384, 'nvrm-rebar': 'on', 'nvrm-rebar-max-mb': 32768, 'nvrm-above-4g': 'yes', 'nvrm-aspm': 'L1'};
event('scan', facts);
const mac = element('mac').innerHTML;
assert(mac.includes('8 GB now, 16 GB from the firmware'), mac);
assert(mac.includes('on, up to 32 GB') && mac.includes('Above 4G Decoding: yes') && mac.includes('L1'), mac);
event('scan', machine(26));
assert(!element('mac').innerHTML.includes('Memory window'));
// hybrid laptop mode buttons post the level and the checked package
event('scan', machine(15));
element('hybcopy').onclick();
assert.deepEqual({act: sent.at(-1).act, level: sent.at(-1).level, pkg: sent.at(-1).pkg}, {act: 'hybrid', level: 'copy', pkg: '/tmp/driver.tar.gz'});
element('hyboff').onclick();
assert.deepEqual({act: sent.at(-1).act, level: sent.at(-1).level}, {act: 'hybrid', level: 'off'});
console.log('Card facts and hybrid laptop mode controls passed.');

// Ryzen laptop power profile: ONE pane. Turn on posts the four limits and the checked package; Status and Turn it off post their own.
element('ryst').value = '15'; element('rysl').value = '20'; element('ryfa').value = '25'; element('rytm').value = '75';
event('scan', machine(26));
element('ryzon').onclick();
assert.deepEqual({act: sent.at(-1).act, on: sent.at(-1).on, stapm: sent.at(-1).stapm, slow: sent.at(-1).slow, fast: sent.at(-1).fast, temp: sent.at(-1).temp, pkg: sent.at(-1).pkg},
  {act: 'ryzenpower', on: true, stapm: 15, slow: 20, fast: 25, temp: 75, pkg: '/tmp/driver.tar.gz'});
element('ryzoff').onclick(); assert.deepEqual({act: sent.at(-1).act, on: sent.at(-1).on}, {act: 'ryzenpower', on: false});
element('ryzstat').onclick(); assert.deepEqual({act: sent.at(-1).act, status: sent.at(-1).status}, {act: 'ryzenpower', status: true});
console.log('Ryzen power profile controls passed.');

// The user's own config.plist, for a Mac whose startup partition cannot be confirmed: the picker asks the app, the answer joins the list.
const optsSeen = [];
element('efi').appendChild = (o) => { optsSeen.push(o); };
element('cfgpick').onclick();
assert.equal(sent.at(-1).act, 'pickconfig');
console.log('Config file picker passed.');

// Intel VMD / RAID: the Mac app explains the external-drive route and the Windows-only steps; nothing to press.
element('vmdpane').hidden = true;
const v = machine(26); v.vmdOrRaid = true; event('scan', v);
assert.equal(element('vmdpane').hidden, false);
event('scan', machine(26));
assert.equal(element('vmdpane').hidden, true);
console.log('VMD / RAID explanation passed.');

// GPU boost: on carries the checked package, off and remove do not, status asks without a password and shows the answer.
event('scan', machine(26));
element('boston').onclick();
assert.deepEqual({act: sent.at(-1).act, op: sent.at(-1).op, pkg: sent.at(-1).pkg}, {act: 'gpuboost', op: 'on', pkg: '/tmp/driver.tar.gz'});
element('bostoff').onclick(); assert.deepEqual({op: sent.at(-1).op, pkg: sent.at(-1).pkg}, {op: 'off', pkg: undefined});
element('bostrm').onclick(); assert.equal(sent.at(-1).op, 'remove');
element('bostat').onclick(); assert.equal(sent.at(-1).op, 'status');
event('boostStatus', {text: 'On: the daemon holds the GPU at its maximum boost.'});
assert(element('bostr').textContent.startsWith('On:'));
console.log('GPU boost controls passed.');
