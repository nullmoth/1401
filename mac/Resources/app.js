"use strict";
const $ = (id) => document.getElementById(id);
const post = (m) => window.webkit.messageHandlers.nm.postMessage(m);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const S = { mac: null, pkg: "", previewed: false, installed: false, driverUpdate: false };

function row(k, v) { return `<tr><th>${esc(k)}</th><td>${v}</td></tr>`; }
function step(n, state) { const li = $("s" + n); li.classList.toggle("done", state === "done"); li.classList.toggle("now", state === "now"); }

// The "ARM apps (opt-in)" card: status (on/off, check, list), busy text, translation progress and every error.
// A.last: the outcome of the last action (an error, or a finished translation). A status refresh follows most actions
// and would otherwise overwrite it, so the refresh shows it above the status once.
const A = { on: false, ok: false, running: false, last: "" };
function armButtons() {
  $("armon").hidden = A.on; $("armoff").hidden = !A.on; $("armchk").hidden = !A.on;
  $("armon").disabled = false;
  $("armtr").hidden = !A.on; $("armtr").disabled = !(A.on && A.ok) || A.running;
  $("armprog").hidden = !A.running;
  $("armbrew").hidden = !A.on; $("armbrewgo").disabled = !A.on || A.running;
}
// nm-arm brew status: {"arm": {"installed", "ruby", "programs"}, "intel": {"installed"}} or {"why"}
function armBrewText(b) {
  if (!b) return "";
  if (b.why) return `<span class="warn">${esc(b.why)}</span>`;
  const side = (s, name, cmd) => s && s.installed ? `<span class="good">${name} ready</span> (${cmd})` : `${name} not set up`;
  let t = side(b.arm, "ARM Homebrew", "abrew") + " &middot; " + side(b.intel, "Intel Homebrew", "ibrew");
  const p = b.arm && b.arm.programs;
  if (p) t += `<br>Translated programs: ${esc(p.translated || 0)}; waiting for their first run: ${esc(p.stub || 0)}.`;
  if (b.arm && b.arm.installed && b.arm.ruby && !b.arm.ruby.launcher) t += `<br><span class="warn">The ARM Homebrew's Ruby is not prepared yet: run abrew once in Terminal.</span>`;
  return t;
}
function gmEvent(d) {
  $("gmon").hidden = !!d.installed; $("gmoff").hidden = !d.installed;
  $("gmon").disabled = false; $("gmoff").disabled = false;
  $("gmr").innerHTML = d.why ? `<span class="warn">${esc(d.why)}</span>`
    : d.installed ? (d.running ? "On: it switches itself on when a game is full screen." : "Installed but not running: restart the Mac, or turn it off and on.") : "";
}
function armEvent(d) {
  if (d.kind === "status") {
    A.on = !!d.installed; A.running = !!d.translating;
    const c = d.check || {};
    A.ok = A.on && c.ok === true;
    let t = (A.last ? A.last + "<br>" : "") + (d.note ? `<span class="good">${esc(d.note)}</span><br>` : "");
    A.last = "";
    if (!A.on) t += "Off. Nothing is installed.";
    else if (c.ok === true) t += `<span class="good">This Mac can run translated apps</span>` + (c.target ? ` (${esc(c.target)})` : "") + ".";
    else t += `<span class="warn">${esc(c.why || "This Mac did not pass the check.")}</span>`;
    // nm-arm check's "note": a sentence for the user when the system seems to hide CPU features (a VM, for example)
    if (A.on && c.note) t += `<br><span class="small">${esc(c.note)}</span>`;
    if (d.listWhy) t += `<br><span class="warn">${esc(d.listWhy)}</span>`;
    $("armr").innerHTML = t;
    $("armclt").hidden = !(A.on && c.prerequisites && c.prerequisites.clt === false);
    $("armbrewr").innerHTML = A.on ? armBrewText(d.brew) : "";
    const apps = d.apps || [];
    $("armapps").innerHTML = !A.on ? "" : apps.length
      ? "<table>" + apps.map((a) => `<tr><th>${esc(a.name)}</th><td><button type="button" class="b" data-op="open" data-path="${esc(a.path)}">Open</button> <button type="button" class="b" data-op="remove" data-name="${esc(a.name)}">Remove</button></td></tr>`).join("") + "</table>"
      : '<p class="small">No translated apps yet.</p>';
    armButtons();
    return;
  }
  if (d.kind === "request") {
    // 1401 for Windows asked for ARM apps: open Tools with this card first, the banner on top of it
    $("armreqt").textContent = d.text;
    $("armreqon").hidden = !d.canRun;
    $("armreq").hidden = false;
    const tab = document.querySelector('.tab[data-t="tools"]');
    if (tab) tab.click();
    const sec = $("t-tools"), card = $("armcard"), first = sec.querySelector(".card");
    if (first && first !== card) sec.insertBefore(card, first);
    card.scrollIntoView({ block: "start" });
    return;
  }
  if (d.kind === "busy") { A.last = ""; $("armr").textContent = d.text; return; }
  if (d.kind === "error") { A.last = `<span class="warn">${esc(d.why)}</span>`; $("armr").innerHTML = A.last; armButtons(); return; }
  if (d.kind === "progress") {
    A.running = true; armButtons(); $("armcancel").disabled = false;
    if (typeof d.pct === "number") $("armbar").value = d.pct; else $("armbar").removeAttribute("value");
    $("armmsg").textContent = `${d.app}: ${d.msg || d.stage || ""}`;
    return;
  }
  if (d.kind === "done") {
    A.running = false; armButtons();
    if (d.what === "brew")
      A.last = d.ok ? `<span class="good">${esc(d.msg || "Homebrew is set up. Open a new Terminal window.")}</span>`
                    : `<span class="warn">Homebrew: ${esc(d.why || "the setup did not finish")}</span>`;
    else
      A.last = d.ok ? `<span class="good">${esc(d.app)} is translated: it is in Applications &gt; NullMoth ARM.</span>`
                    : `<span class="warn">${esc(d.app)}: ${esc(d.why || "the translation did not finish")}</span>`;
    $("armr").innerHTML = A.last;
  }
}

function render(m) {
  S.mac = m;
  $("ver").textContent = m.version;
  const card = m.gpus.find((g) => g.supported) || m.gpus.find((g) => g.vendor === "10DE");
  const on = m.kexts >= 4 && m.metal.some((n) => /NVIDIA|GeForce|RTX/i.test(n));
  // The facts the kext publishes on the card: the BAR window it got and what the card offers, Above 4G, and the link power state
  function nvrmFactRows(m) {
    const g = m.gpus.find((x) => x.nvrm && Object.keys(x.nvrm).length); if (!g) return "";
    const f = g.nvrm, mb = (v) => (v === undefined || v === null ? "unknown" : Number(v) >= 1024 ? (Number(v) / 1024) + " GB" : Number(v) + " MB");
    const rb = f["nvrm-rebar"] === "on" ? "on" : f["nvrm-rebar"] === "off" ? "supported, off" : f["nvrm-rebar"] === "none" ? "not offered by the card" : "unknown";
    return row("Memory window (BAR1)", esc(mb(f["nvrm-bar1-mb"])) + " now, " + esc(mb(f["nvrm-bar1-firmware-mb"])) + " from the firmware") +
      row("Resizable BAR", esc(rb) + (Number(f["nvrm-rebar-max-mb"]) ? ", up to " + esc(mb(f["nvrm-rebar-max-mb"])) : "") + "; Above 4G Decoding: " + esc(String(f["nvrm-above-4g"] || "unknown"))) +
      row("PCIe link power (ASPM)", esc(String(f["nvrm-aspm"] || "unknown")));
  }
  $("mac").innerHTML =
    row("macOS", esc(m.macos) + ([15, 26].includes(m.major) ? "" : ' <span class="bad">(the driver is for macOS 15 and 26)</span>')) +
    row("Processor", m.arch === "x86_64" && !m.translated ? "x86_64" : '<span class="bad">Apple silicon - this driver is for Intel Macs and PCs</span>') +
    row("Graphics", m.gpus.length ? m.gpus.map((g) => esc(g.name) + (g.supported ? (g.tested ? ' <span class="good">listed device, model tested</span>' : ' <span class="warn">listed by NVIDIA, model not tested yet</span>') : g.vendor === "10DE" ? ' <span class="bad">not supported (needs RTX 20 series or newer)</span>' : "")).join("<br>") : "none found") +
    nvrmFactRows(m) +
    row("OpenCore", m.opencore ? esc(m.opencore) : m.nativeMacPro ? 'not needed: Mac Pro (2019) on Apple\'s firmware <span class="warn">(experimental, needs SIP off)</span>' : '<span class="warn">not detected</span>') +
    row("Installed driver package", m.installedDriverVersion ? esc(m.installedDriverVersion) : "No version record") +
    row("NullMoth driver", on ? '<span class="good">running</span> (' + esc(m.metal.join(", ")) + ")" : m.kexts >= 4 ? '<span class="warn">loaded, no NVIDIA Metal device yet</span>' : m.files ? '<span class="warn">installed, not running yet</span>' : "not installed");

  let why = "";
  if (m.arch !== "x86_64" || m.translated) why = "This Mac has Apple silicon. Its own graphics are already Apple's.";
  else if (![15, 26].includes(m.major)) why = `The driver is built for macOS 15 Sequoia and macOS 26 Tahoe (beta); this Mac runs ${esc(m.macos)}.`;
  else if (!card && (m.gpuHiding || []).some((a) => a !== "-wegnoigpu")) why = `No NVIDIA card is visible because this Mac starts with ${esc(m.gpuHiding.filter((a) => a !== "-wegnoigpu").join(" "))}, which hides discrete GPUs. Remove it from boot-args in OpenCore's config.plist, restart, and open 1401 again.`;
  else if (!card && (m.hiddenNvidia || []).length) why = `The NVIDIA card (${esc(m.hiddenNvidia.join(", "))}) is on the bus but switched off for macOS, usually by a disable-gpu property in OpenCore's DeviceProperties. Remove it, restart, and open 1401 again.`;
  else if (!card && /^MacBook/.test(m.hwModel || "")) why = "No NVIDIA card was found. On a laptop the card is often switched off before macOS starts: by the BIOS graphics mode (choose Hybrid/MSHybrid or Discrete, not iGPU only) or by a dGPU-off SSDT in OpenCore's ACPI folder. Fix that, restart, and open 1401 again.";
  else if (!card || !card.supported) why = "No supported NVIDIA card was found. The driver needs a GeForce RTX 20 series or newer.";
  else if (!m.opencore && !m.nativeMacPro) why = "This Mac does not report OpenCore. The driver's settings live in OpenCore's config, so 1401 will not install without it.";

  // Keep the checked package available when the driver is already running.
  const pk = m.packages.find((p) => p.ok === "yes"); if (pk) S.pkg = pk.path;
  // Tahoe: only from macOS 15, on a Mac the driver can be installed on, with the checked package (it carries both drivers)
  // (this scan's package, not S.pkg: an ejected disk image must not leave the button pointing at a path that is gone)
  $("upd").disabled = !pk || m.major !== 15 || !!why || !!m.nativeMacPro;   // a Mac Pro (2019) runs macOS 26 as it is
  $("updt").innerHTML = m.major === 26 ? "This Mac already runs macOS 26." : why ? "" : pk ? "" :
    'Needs the driver package: <button type="button" class="b" id="dl3">Download the driver package</button>';
  const d3 = $("dl3"); if (d3) d3.onclick = () => post({ act: "download" });
  if (on) {
    $("verdict").innerHTML = `<p class="good">NullMoth components are loaded and an NVIDIA Metal device is visible.</p><p>Use Check for a newer driver to update the driver. To remove the driver, use Remove the driver below.${m.major === 15 ? " To move to macOS 26 Tahoe, use <b>Prepare this Mac for Tahoe</b> below." : ""}</p>`;
    $("steps").hidden = true; return;
  }
  // No NVIDIA card but an AMD or Intel GPU: the NVIDIA steps do not apply, the AMD/Intel test driver below does. It needs
  // the driver package (that is where the test driver ships), so the download stays offered.
  const other = !card && m.arch === "x86_64" && !m.translated && [15, 26].includes(m.major) && m.gpus.some((g) => g.vendor === "1002" || g.vendor === "8086");
  // No GPU at all on an Intel-type Mac: OpenCore switched it off (disable-gpu or -wegnoigpu), and Lilu then takes it off
  // macOS's PCI list entirely, so the table says "none found" (2.0.3, a Core Ultra laptop, chat photo 10-16). The test
  // driver's setup turns an Intel GPU at the usual address back on, so it is offered here instead of the NVIDIA advice.
  const hiddenOwn = !card && m.arch === "x86_64" && !m.translated && [15, 26].includes(m.major) && !m.gpus.length && !(m.hiddenNvidia || []).length
    && !(m.gpuHiding || []).some((a) => a !== "-wegnoigpu");   // -wegnoegpu & co. hide the NVIDIA card: their advice stays
  if (hiddenOwn) {
    const pk3 = m.packages.find((p) => p.ok === "yes"); if (pk3) S.pkg = pk3.path;
    $("verdict").innerHTML = `<p class="warn">macOS sees no GPU at all on this Mac.</p><p>OpenCore most likely switches it off (a disable-gpu property${(m.gpuHiding || []).includes("-wegnoigpu") ? ", and -wegnoigpu in boot-args" : ""}). For the processor's own Intel or AMD GPU, <b>AMD / Intel GPU and NPU driver (test)</b> below turns it back on with the test driver, and <b>Turn it off</b> switches it off again. Turning it on downloads the AMD / Intel driver's own package and checks it.</p>`;
    $("steps").hidden = true; return;
  }
  if (why && other) {
    const pk2 = m.packages.find((p) => p.ok === "yes"); if (pk2) S.pkg = pk2.path;
    $("verdict").innerHTML = `<p class="warn">No NVIDIA card, so the NVIDIA driver does not apply here.</p><p>This Mac's ${esc(m.gpus.filter((g) => g.vendor !== "10DE").map((g) => g.name).join(", "))} can try the experimental AMD / Intel GPU driver: see <b>AMD / Intel GPU and NPU driver (test)</b> below. Turning it on downloads that driver's own package and checks it.</p>`;
    $("steps").hidden = true; return;
  }
  if (why) { $("verdict").innerHTML = `<p class="bad">Can't install here.</p><p>${why}</p>`; $("steps").hidden = true; return; }
  // All four kexts loaded but no NVIDIA Metal device is a different state from "not running" (#98: an Optimus laptop
  // whose kexts were loaded was told to restart and allow an extension that was never blocked).
  if (m.files && !S.installed && m.kexts >= 4) {
    $("verdict").innerHTML = '<p class="warn">The driver is loaded, but macOS shows no NVIDIA Metal device yet.</p><p>On a laptop whose built-in screen is wired to the Intel or AMD graphics (no MUX switch), the NVIDIA card draws only the displays plugged into its own HDMI or DisplayPort: connect one there and restart. Otherwise restart once; if it stays this way, use Send logs.</p>';
  } else if (m.files && !S.installed && m.driverOsMajor && m.driverOsMajor !== m.major) {
    // macOS was updated after the driver was set up (1401 #484): the new system parked the old kernel collection
    $("verdict").innerHTML = `<p class="warn">macOS was updated from ${esc(String(m.driverOsMajor))} to ${esc(String(m.major))} after the driver was set up, so the driver is not running.</p><p>It has to be set up again for this macOS: use the four steps below with a driver package that supports macOS ${esc(String(m.major))}. Your OpenCore settings stay as they are.</p>`;
  } else if (m.files && !S.installed) {
    $("verdict").innerHTML = '<p class="warn">The driver is installed but not running.</p><p>Restart. If macOS blocked a system extension, allow it in Privacy &amp; Security, then restart once more.</p>';
  } else {
    $("verdict").innerHTML = `<p>Your <b>${esc(card.name)}</b> has a driver configuration available. This machine still needs boot, display and application checks. Four steps, in order.</p>`;
  }
  $("steps").hidden = false;
  const good = m.packages.find((p) => p.ok === "yes");
  if (good) { S.pkg = good.path; $("s1t").innerHTML = `Found on ${esc(good.where)}, checksum OK.`; $("dl").hidden = true; step(1, "done"); }
  else { $("s1t").textContent = m.packages.length ? "A copy was found but its checksum is wrong. Download a fresh one." : "Not on this Mac yet."; $("dl").hidden = false; step(1, "now"); }
  $("dry").disabled = !S.pkg;
  goState();
  if (S.pkg && !S.previewed) step(2, "now");
}

// A greyed-out button with no reason sent users to Discord (10-13: "Install Driver is greyed out, what do I do"): the
// button says which step comes first.
function goState() {
  $("go").disabled = !S.pkg || !S.previewed;
  $("go").textContent = !S.pkg ? "Install the driver (get the driver first)" : !S.previewed ? "Install the driver (press Show me the changes first)" : "Install the driver";
  $("go").title = !S.pkg ? "Step 1 has not found the driver yet." : !S.previewed ? "Step 2 lists every change first; then this button turns on." : "";
}

function logLine(l) {
  const kind = l.split(" ")[0], rest = esc(l.slice(kind.length + 1));
  const cls = { STEP: "s", CHANGE: "c", OK: "k", STOP: "x", RESULT: "s" }[kind];
  const txt = kind === "STEP" ? "== " + rest : kind === "CHANGE" ? "will change: " + rest : kind === "OK" ? "ok  " + rest : kind === "STOP" ? "STOPPED: " + rest : kind === "NOTE" ? "    " + rest : kind === "RESULT" ? (rest === "ok" ? "done." : "stopped - nothing after the red line was changed.") : esc(l);
  $("log").insertAdjacentHTML("beforeend", (cls ? `<span class="${cls}">${txt}</span>` : txt) + "\n");
  $("log").scrollTop = $("log").scrollHeight;
  const m = l.match(/^NOTE candidate (\S+)/);
  if (m) { $("efirow").hidden = false; if (![...$("efi").options].some((o) => o.value === m[1])) $("efi").insertAdjacentHTML("beforeend", `<option value="${esc(m[1])}">${esc(m[1])}</option>`); }
}

const NM = {
  on({ event, data }) {
    if (event === "scan") render(data);
    if (event === "lines") data.forEach(logLine);
    if (event === "dl") {
      if (data.state === "progress") {
        // Update driver shows its own line; without this the progress went to step 1 and the update looked stuck.
        const mb = (n) => (n / 1048576).toFixed(1);
        const t = data.total > 0 ? `${Math.floor((100 * data.done) / data.total)}% (${mb(data.done)} of ${mb(data.total)} MB)` : `${mb(data.done)} MB`;
        $("dlp").textContent = t;
        if (S.driverUpdate) $("updr").textContent = `Downloading the newest driver: ${t}`;
      }
      if (data.state === "start") ["dl", "updchk", "upddrv"].forEach((b) => ($(b).disabled = true));
      if (data.state === "error" || data.state === "done") ["dl", "updchk", "upddrv"].forEach((b) => ($(b).disabled = false));
      if (data.state === "error") {
        $("dlp").innerHTML = `<span class="bad">${esc(data.why)}</span>`;
        if (S.driverUpdate) { S.driverUpdate = false; $("updr").innerHTML = `<span class="bad">${esc(data.why)}</span>`; }
      }
      if (data.state === "done") {
        $("dlp").textContent = "done, checksum OK";
        if (S.driverUpdate) { $("updr").textContent = "Download checked. Installing the driver..."; $("upddrv").disabled = true; }
        post({ act: "scan" });
      }
    }
    if (event === "upd") {
      if (data.state === "error") { $("updr").innerHTML = `<span class="bad">${esc(data.why)}</span>`; $("upddrv").hidden = true; }
      if (data.state === "checked") {
        const have = data.installed ? `installed ${esc(data.installed)}, ` : "";
        const kind = data.prerelease ? "early release " : "";
        $("updr").innerHTML = !data.installed
          ? `1401 could not tell which driver version is installed. The newest ${kind}is ${esc(data.latest)}; updating to it is safe either way.`
          : data.newer ? `${have}newest ${kind}${esc(data.latest)} - ready to update.` : `${have}you have the newest driver (${esc(data.latest)}).`;
        $("upddrv").hidden = !data.newer;
        $("upddrv").disabled = !data.newer;
        if (data.app) $("updr").innerHTML += data.appNewer ? ` App ${esc(data.appHave)} -> ${esc(data.app)} is ready.` : ` The app (${esc(data.appHave)}) is up to date.`;
        $("updapp").hidden = !data.appNewer;
        $("updapp").disabled = !data.appNewer;
      }
    }
    if (event === "appupd") {
      if (data.state === "error") { $("updapp").disabled = false; $("updr").innerHTML = `<span class="bad">${esc(data.why)}</span>`; }
      if (data.state === "start") $("updr").textContent = `Downloading 1401 ${data.version}...`;
      if (data.state === "restarting") $("updr").textContent = `1401 ${data.version} checked - restarting into it...`;
    }
    if (event === "run") {
      const busy = data.state === "start";
      ["dry", "go", "rm", "dl", "updchk", "upddrv", "upd", "updc"].forEach((b) => ($(b).disabled = busy));
      if (busy) { $("logwrap").hidden = false; $("log").textContent = ""; return; }
      if (data.why) { $("logwrap").hidden = false; logLine(data.why); }
      if (data.state === "cancelled") {
        if (S.driverUpdate) { S.driverUpdate = false; $("updr").textContent = "Driver update cancelled."; }
        logLine("NOTE cancelled - nothing was changed"); post({ act: "scan" }); return;
      }
      if (S.driverUpdate && data.mode === "install") {
        S.driverUpdate = false;
        if (data.ok) {
          $("updr").textContent = "Driver installed. Restart to load it.";
          $("upddrv").hidden = true;
          $("upddrv").disabled = true;
        } else { $("updr").textContent = "Driver update stopped. Review the setup log below."; }
      }
      if (data.mode === "dry" && data.ok) { S.previewed = true; step(2, "done"); step(3, "now"); }
      if (data.mode === "install" && data.ok) { S.installed = true; step(3, "done"); step(4, "now"); $("rs").disabled = false; }
      if (data.mode === "tahoe") {
        if (data.ok) { $("swu").hidden = false; $("updt").textContent = "Ready for Tahoe. Open Software Update and install macOS 26."; logLine("OK ready for Tahoe - click Open Software Update and install macOS 26"); }
        else $("updt").textContent = "Tahoe preparation stopped. Review the setup log above.";
      }
      if (data.mode === "tahoecancel") { $("swu").hidden = true; $("updt").textContent = data.ok ? "Done: the driver is set to start. Restart the Mac to load it." : "Stopped. Review the setup log above."; }
      post({ act: "scan" });
    }
  },
};
window.NM = NM;

$("cfgpick").onclick = () => post({ act: "pickconfig" });
const efi = () => ($("efirow").hidden ? "auto" : $("efi").value);
$("efi").onchange = () => {
  S.previewed = false;
  goState();
  step(2, "now"); step(3, "waiting");
};
$("dl").onclick = () => post({ act: "download" });
$("upd").onclick = () => post({ act: "osupdate", cancel: false, pkg: S.pkg, efi: efi() });
$("swu").onclick = () => post({ act: "swupdate" });
$("updc").onclick = () => post({ act: "osupdate", cancel: true, efi: efi() });
$("updchk").onclick = () => { $("updr").textContent = "Checking..."; post({ act: "checkUpdate" }); };
$("updapp").onclick = () => { $("updapp").disabled = true; post({ act: "updateApp" }); };
$("upddrv").onclick = () => { S.driverUpdate = true; $("upddrv").disabled = true; $("updr").textContent = "Downloading the newest driver..."; post({ act: "updateDriver", efi: efi() }); };
$("ocg").onclick = (e) => { e.preventDefault(); post({ act: "open", url: "https://dortania.github.io/OpenCore-Install-Guide/" }); };
$("dry").onclick = () => post({ act: "run", mode: "dry", pkg: S.pkg, efi: efi() });
$("go").onclick = () => post({ act: "run", mode: "install", pkg: S.pkg, efi: efi() });
$("rm").onclick = () => { if (confirm("Remove the NullMoth driver and put your OpenCore config back the way it was?")) post({ act: "run", mode: "remove", pkg: "", efi: efi() }); };
$("rs").onclick = () => post({ act: "restart" });
$("vbon").onclick = () => post({ act: "verbose", on: true, efi: efi() });
$("vboff").onclick = () => post({ act: "verbose", on: false, efi: efi() });
$("blon").onclick = () => post({ act: "backlight", on: true, efi: efi() });
$("bloff").onclick = () => post({ act: "backlight", on: false, efi: efi() });
$("hdon").onclick = () => post({ act: "hidpi", on: true, efi: efi() });
$("hdoff").onclick = () => post({ act: "hidpi", on: false, efi: efi() });
$("gpuon").onclick = () => post({ act: "gputest", on: true, efi: efi() });
$("gpuoff").onclick = () => post({ act: "gputest", on: false, efi: efi() });
$("hybcopy").onclick = () => post({ act: "hybrid", level: "copy", pkg: S.pkg || "", efi: efi() });
$("hybimport").onclick = () => post({ act: "hybrid", level: "import", pkg: S.pkg || "", efi: efi() });
$("hyboff").onclick = () => post({ act: "hybrid", level: "off", efi: efi() });
// Select all and Deselect all only tick and untick; nothing changes until Apply
for (const [id, on] of [["expall", true], ["expnone", false]]) $(id).onclick = () => { for (const c of document.querySelectorAll(".expitem")) c.checked = on; };
$("expapply").onclick = () => post({ act: "experimental", items: Array.from(document.querySelectorAll(".expitem")).filter((c) => c.checked).map((c) => c.dataset.id), efi: efi() });
$("boston").onclick = () => post({ act: "gpuboost", op: "on", pkg: S.pkg || "", efi: efi() });
$("bostoff").onclick = () => post({ act: "gpuboost", op: "off", efi: efi() });
$("bostrm").onclick = () => post({ act: "gpuboost", op: "remove", efi: efi() });
$("bostat").onclick = () => post({ act: "gpuboost", op: "status" });
const ryNum = (id) => Number($(id).value);
$("ryzon").onclick = () => post({ act: "ryzenpower", on: true, stapm: ryNum("ryst"), slow: ryNum("rysl"), fast: ryNum("ryfa"), temp: ryNum("rytm"), pkg: S.pkg || "", efi: efi() });
$("ryzstat").onclick = () => post({ act: "ryzenpower", status: true, efi: efi() });
$("ryzoff").onclick = () => post({ act: "ryzenpower", on: false, efi: efi() });
$("xeon").onclick = () => post({ act: "xe", on: true, efi: efi() });
$("xeoff").onclick = () => post({ act: "xe", on: false, efi: efi() });
$("armon").onclick = () => { $("armon").disabled = true; post({ act: "arm", op: "on" }); };
$("armoff").onclick = () => post({ act: "arm", op: "off" });
$("armreqon").onclick = () => { $("armreq").hidden = true; $("armon").disabled = true; post({ act: "arm", op: "on", from: "windows" }); };
$("armreqno").onclick = (e) => { e.preventDefault(); $("armreq").hidden = true; post({ act: "arm", op: "notNow" }); };
$("gmon").onclick = () => { $("gmon").disabled = true; $("gmr").textContent = "Waiting for your Mac password..."; post({ act: "gm", op: "on" }); };
$("gmoff").onclick = () => { $("gmoff").disabled = true; $("gmr").textContent = "Waiting for your Mac password..."; post({ act: "gm", op: "off" }); };
$("armchk").onclick = () => post({ act: "arm", op: "check" });
$("armclt").onclick = () => post({ act: "arm", op: "clt" });
$("armtr").onclick = () => { $("armtr").disabled = true; post({ act: "arm", op: "translate" }); };
$("armbrewgo").onclick = () => { $("armbrewgo").disabled = true; post({ act: "arm", op: "brew", pick: $("armbrewpick").value, primary: $("armbrewprim").value }); };
$("armcancel").onclick = () => { $("armcancel").disabled = true; $("armmsg").textContent = "Cancelling..."; post({ act: "arm", op: "cancel" }); };
$("armapps").onclick = (e) => {
  const b = e.target.closest("button[data-op]");
  if (b) post({ act: "arm", op: b.dataset.op, name: b.dataset.name, path: b.dataset.path });
};
post({ act: "arm", op: "status" });
post({ act: "gm", op: "status" });
$("teston").onclick = () => post({ act: "tester", on: true });
$("testoff").onclick = () => post({ act: "tester", on: false });
$("earlyon").onclick = () => post({ act: "early", on: true });
$("earlyoff").onclick = () => post({ act: "early", on: false });
post({ act: "early" });
$("efichk").onclick = () => { $("efichk").disabled = true; $("efichkr").textContent = "Reading the EFI..."; $("efiout").textContent = ""; post({ act: "checkEfi" }); };
$("tccg").onclick = () => { $("tccr").textContent = "Pick the app..."; post({ act: "tccGrant" }); };
$("settings").onclick = () => post({ act: "settings" });
$("gpumap").onclick = () => { $("gpumap").disabled = true; $("gpumapr").textContent = "Starting..."; post({ act: "gpumap" }); };
$("priv").onclick = (e) => { e.preventDefault(); post({ act: "privacy" }); };
$("logs").onclick = (e) => { e.preventDefault(); post({ act: "logs" }); };
$("src").onclick = (e) => { e.preventDefault(); post({ act: "open", url: "https://github.com/nullmoth/nvidia-macos-driver" }); };
post({ act: "scan" });

document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === b));
  ["drv", "efi", "tools", "usb", "crash"].forEach((t) => ($("t-" + t).hidden = t !== b.dataset.t));
  $("ttl").textContent = "1401 — " + b.dataset.title;
  if (b.dataset.t !== "usb") post({ act: "usbStop" });
}));
// Light or dark: the switch in the title bar, remembered on this Mac; until it is used, the system's setting decides.
// Storage can be unavailable; the switch still works for the session.
function setTheme(light) {
  $("desk").classList.toggle("light", light);
  try { localStorage.setItem("theme", light ? "light" : "dark"); } catch (e) { /* the switch still works this session */ }
}
(() => {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) { /* no stored choice */ }
  const prefersLight = typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: light)").matches;
  $("desk").classList.toggle("light", saved ? saved === "light" : prefersLight);
})();
$("theme").onclick = () => setTheme(!$("desk").classList.contains("light"));
$("efimount").onclick = () => { $("efimount").disabled = true; $("efimountr").textContent = "Finding the EFI..."; post({ act: "mountEfi" }); };
const CONN = [[0, "USB 2 Type-A"], [3, "USB 3 Type-A"], [9, "USB-C (flips)"], [10, "USB-C (one way)"], [255, "Inside the case"]];
function usbConnectorDefault(port) {
  if (port.connectorKnown === true && CONN.some(([value]) => value === port.connector)) return port.connector;
  return port.usb3 ? 3 : 0;
}
const U = { ctrls: [], seen: {}, pick: {}, off: new Set(), last: "" };
function usbRender() {
  let h = "";
  for (const c of U.ctrls) {
    const name = c.key || c.controller, seen = new Set(U.seen[name] || []);
    const n = Object.keys(U.pick[name] || {}).length;
    h += `<table class="pc ports" border="1" cellspacing="2" cellpadding="3"><caption>Controller ${esc(c.controller)} (${esc(c.vendor)}:${esc(c.device)}) &mdash; <span class="${n > 15 ? "bad" : ""}">${n} of 15 picked</span></caption><tr><th>Use</th><th>Port</th><th>Seen</th><th>Plug</th><th>Device now</th></tr>`;
    for (const p of c.ports) {
      const on = seen.has(p.name), pk = (U.pick[name] || {})[p.name];
      const def = usbConnectorDefault(p);
      h += `<tr><td><input type="checkbox" data-c="${esc(name)}" data-p="${esc(p.name)}" ${pk !== undefined ? "checked" : ""}></td><td>${esc(p.name)}${p.usb3 ? " (USB 3)" : ""}</td><td class="${on ? "on" : "off"}">${on ? "yes" : "no"}</td>` +
        `<td><select data-c="${esc(name)}" data-p="${esc(p.name)}">${CONN.map(([v, t]) => `<option value="${v}" ${(pk ?? def) === v ? "selected" : ""}>${t}</option>`).join("")}</select></td><td>${esc((p.devices || []).join(", "))}</td></tr>`;
    }
    h += "</table>";
  }
  $("ports").innerHTML = h;
  $("ports").querySelectorAll("input").forEach((i) => (i.onchange = () => {
    const c = i.dataset.c, p = i.dataset.p; U.pick[c] = U.pick[c] || {};
    if (i.checked) { U.off.delete(c + "/" + p); U.pick[c][p] = +i.closest("tr").querySelector("select").value; } else { U.off.add(c + "/" + p); delete U.pick[c][p]; }
    usbRender();
  }));
  $("ports").querySelectorAll("select").forEach((s) => (s.onchange = () => {
    const c = s.dataset.c, p = s.dataset.p; U.pick[c] = U.pick[c] || {};
    // choosing a plug type is choosing the port: an unticked row is ticked with that type rather than reset on redraw
    U.off.delete(c + "/" + p); U.pick[c][p] = +s.value; usbRender();
  }));
}
$("uw").onclick = () => { U.pick = {}; U.off = new Set(); U.last = ""; post({ act: "usbStart" }); $("uw").textContent = "Watching..."; $("uw").disabled = true; };
$("uwr").onclick = () => { $("uerr").textContent = ""; post({ act: "usbStop" }); post({ act: "usbWrite", sel: U.pick, efi: efi() }); };
$("mk").onclick = () => post({ act: "crashReport" });
$("cf").onclick = () => post({ act: "open", url: "https://buymeacoffee.com/nullmoth" });
// every project 1401 is built on or downloads, with its author and licence
$("cr").onclick = () => post({ act: "open", url: "https://github.com/nullmoth/1401/blob/main/NOTICE.md" });
$("sl").onclick = () => { $("sl").disabled = true; $("slr").textContent = "Collecting and sending..."; post({ act: "sendLogs" }); };
$("fl").onclick = () => { $("sl").disabled = true; $("fl").disabled = true; $("slr").textContent = "Recording the display for 20 seconds, then sending..."; post({ act: "sendLogs", sample: "flicker" }); };
$("od").onclick = () => post({ act: "optionalDiagnostics" });
$("dr").onclick = () => post({ act: "importDiagnosticReceipt" });
$("up").onclick = () => post({ act: "open", url: "https://nullmothsystems.com/#send" });
const prevOn = NM.on;
NM.on = (m) => {
  if (m.event === "diagnosticsStatus") { $("odr").textContent = m.data.text; return; }
  if (m.event === "diagnosticReceipt") { $("drr").textContent = m.data.text; return; }
  if (m.event === "usb") {
    // The scan reports every second. Rebuilding the table each time closed a plug-type list while it was open and put
    // back the default plug on rows not yet ticked, so choices looked like they changed by themselves (10-23 chat).
    // The table is rebuilt only when the controllers, their devices or the ports seen have changed.
    const snap = JSON.stringify([m.data.controllers, m.data.seen]);
    if (snap === U.last) return;
    U.last = snap;
    U.ctrls = m.data.controllers; U.seen = m.data.seen;
    for (const c of U.ctrls) {   // a port that has been seen is ticked automatically, with its default plug type
      const key = c.key || c.controller;
      U.pick[key] = U.pick[key] || {};
      for (const p of c.ports) if ((U.seen[key] || []).includes(p.name) && !(p.name in U.pick[key]) && !U.off.has(key + "/" + p.name)) U.pick[key][p.name] = usbConnectorDefault(p);
    }
    usbRender(); return;
  }
  if (m.event === "usbErr") { $("uerr").textContent = m.data; return; }
  if (m.event === "early") {
    $("earlyr").textContent = m.data.on ? "On: new drivers reach this Mac first, before they are offered to everyone." : "Off: this Mac gets releases once they have held up for everyone who went first.";
    $("earlyon").hidden = m.data.on; $("earlyoff").hidden = !m.data.on;
    return;
  }
  if (m.event === "arm") { armEvent(m.data); return; }
  if (m.event === "gm") { gmEvent(m.data); return; }
  if (m.event === "tester") {
    $("testr").innerHTML = m.data.ok ? `<span class="good">${m.data.on ? "Joined: a report goes out after each restart." : "Left: nothing runs any more."}</span>`
                                     : `<span class="warn">${esc(m.data.why)}</span>`;
    return;
  }
  if (m.event === "logsStatus") { $("slr").textContent = m.data.text; return; }
  if (m.event === "efiCheck") {
    const d = m.data;
    $("efichk").disabled = false;
    $("efiout").textContent = "";
    if (d.cancelled) { $("efichkr").textContent = ""; return; }
    if (!d.ok) { $("efichkr").innerHTML = `<span class="warn">${esc(d.why || "The check did not finish.")}</span>`; return; }
    const n = d.issues.length;
    $("efin").hidden = !n; $("efin").textContent = n;
    $("efichkr").innerHTML = n ? `<span class="warn">${n} thing${n === 1 ? "" : "s"} to change in ${esc(d.partition)}</span>`
                               : `<span class="good">No problems found in ${esc(d.partition)}</span>`;
    // built from text nodes: the titles and steps come from the rule file, never parsed as HTML
    for (const i of d.issues) {
      const box = document.createElement("details"), sum = document.createElement("summary"), b = document.createElement("b");
      b.textContent = i.title; sum.appendChild(b); box.appendChild(sum);
      const what = document.createElement("p"); what.textContent = i.what + (i.restart ? " Takes effect at the next restart." : ""); box.appendChild(what);
      // the exact values in this Mac's config and what each must become
      if ((i.now || []).length) {
        const now = document.createElement("div"); now.className = "now";
        const lab = document.createElement("b"); lab.textContent = "On this Mac: "; now.appendChild(lab);
        now.appendChild(document.createTextNode(i.now.join(" ")));
        box.appendChild(now);
      }
      const ol = document.createElement("ol");
      for (const s of i.steps) { const li = document.createElement("li"); li.textContent = s; ol.appendChild(li); }
      box.appendChild(ol);
      $("efiout").appendChild(box);
    }
    if (n) {
      const note = document.createElement("p");
      note.textContent = "Before you edit config.plist, keep a copy of it. If a change stops this Mac from starting, start from your 1401 stick and put the copy back.";
      $("efiout").appendChild(note);
    }
    return;
  }
  if (m.event === "efiMount") {
    $("efimount").disabled = false;
    $("efimountr").innerHTML = m.data.cancelled ? "" : m.data.ok ? `<span class="good">Mounted ${esc(m.data.partition)} at ${esc(m.data.where)}</span>`
                                                              : `<span class="warn">${esc(m.data.why || "The EFI could not be mounted.")}</span>`;
    return;
  }
  if (m.event === "configPicked") {
    const o = document.createElement("option"); o.value = "config:" + m.data.path; o.textContent = "config file: " + m.data.path;
    $("efi").appendChild(o); $("efi").value = o.value; return;
  }
  if (m.event === "scan" && Array.isArray(m.data.experimentalOn)) for (const c of document.querySelectorAll(".expitem")) c.checked = m.data.experimentalOn.includes(c.dataset.id);
  if (m.event === "scan" && $("vmdpane")) $("vmdpane").hidden = !m.data.vmdOrRaid;
  if (m.event === "boostStatus") { $("bostr").textContent = m.data.text; return; }
  if (m.event === "tccStatus") { $("tccr").innerHTML = m.data.text ? `<span class="${m.data.ok ? "good" : "warn"}">${esc(m.data.text)}</span>` : ""; return; }
  if (m.event === "gpumapStatus") { $("gpumapr").textContent = m.data.text; if (m.data.done) $("gpumap").disabled = false; return; }
  if (m.event === "logsDone") {
    const d = m.data;
    $("sl").disabled = false; $("fl").disabled = false;
    $("slr").innerHTML = d.ok ? `<span class="good">Sent. Report ID ${esc(d.ids.join(", "))}</span> - quote it when you ask for help.` + (d.errors.length ? `<br><span class="warn">Not sent: ${esc(d.errors.join("; "))}</span>` : "")
                              : `<span class="warn">${esc(d.why || ("Nothing was sent: " + (d.errors || []).join("; ")))}</span>`;
    if (d.localPath) $("slr").innerHTML += "<br>Report files are saved locally. Open Logs to find them or retry Send logs.";
    return;
  }
  if (m.event === "crashDone") { $("cr").innerHTML = m.data.ok ? `<span class="good">Saved to your Desktop:</span> ${esc(m.data.path.split("/").pop())}` : `<span class="warn">${esc(m.data.why)}</span>`; return; }
  if (m.event === "scan" && m.data.crashes) $("cr").textContent = m.data.crashes.length ? `${m.data.crashes.length} crash file(s) on this Mac name the driver.` : "No crash that names the driver is on this Mac.";
  if (m.event === "scan" && m.data.itlwmNeedsHeliPort) {
    setTimeout(() => $("verdict").insertAdjacentHTML("beforeend", '<p class="warn">Wi-Fi: this Mac\'s Intel Wi-Fi runs on itlwm, which joins networks through its own app, HeliPort, not the Wi-Fi menu. Download HeliPort from github.com/OpenIntelWireless/HeliPort/releases, move it to Applications, open it, and pick your network there. To start it with the Mac, turn on Launch at Login in its menu.</p>'), 0);
  }
  // 2.7.1: shown for every Mac started with -nvoff, not only ones with an install record. 10 of 34 "driver did not come
  // up" reports on 2.7 were parked this way with no way back on screen; setup finds the booted OpenCore partition itself.
  if (m.event === "scan" && m.data.autologinByApp && $("autologin")) {
    $("autologin").hidden = false;
    $("autologinoff").onclick = () => post({ act: "autologinoff" });
  }
  if (m.event === "scan" && m.data.safemode) {
    setTimeout(() => {
      $("verdict").insertAdjacentHTML("afterbegin", '<p class="warn">This Mac started with the NVIDIA driver switched off: -nvoff is in the boot arguments. 1401 puts it there while macOS updates, and some people add it after a black screen. If you prepared for the macOS 26 update, update macOS now from System Settings and the driver comes back by itself after it. To turn the driver back on without updating, or if it stayed off after the update, click Turn the driver on, then restart. If the screen went black with the driver on, send the logs first (Send logs to NullMoth, below). To take the driver out for good, click Remove the driver below.</p><p class="row"><button type="button" class="b go" id="nvon">Turn the driver on</button></p>');
      $("nvon").onclick = () => { $("nvon").disabled = true; post({ act: "osupdate", cancel: true, efi: efi() }); };
    }, 0);
  }
  prevOn(m);
};
window.NM = NM;

// Chinese or English: same contract as Loc.cs and p1401/loc.py (the English string is the key; an untranslated line
// falls back to itself). The switch in the title bar is remembered in localStorage; until it is used, the system
// language decides when running in a browser window.
const ZH = {
  "1401 — This Mac": "1401 — 本机",
  "Switch language": "切换语言",
  "Switch between light and dark": "切换深色与浅色模式",
  "Sections": "栏目",
  "This Mac": "本机",
  "Issues": "问题检查",
  "Tools": "工具",
  "Tools · Mount EFI": "工具 · 挂载 EFI",
  "USB ports": "USB 端口",
  "Send a report": "发送报告",
  "Driver ": "驱动版本 ",
  "Source code": "源代码",
  "OpenCore guide": "OpenCore 指南",
  "Your Mac, mapped": "本机硬件概览",
  "1401 sets up the NullMoth driver on OpenCore Macs running macOS 15.5 or later, or macOS 26 Tahoe. ": "1401 用于在运行 macOS 15.5 及更高版本或 macOS 26 Tahoe 的 OpenCore Mac 上配置 NullMoth 驱动。",
  "Keep the USB stick or disk OpenCore started this Mac from plugged in": "请保持启动本机的 OpenCore U 盘或磁盘处于插入状态",
  ": 1401 changes the settings on that one.": "：1401 会修改该分区上的配置。",
  "Looking...": "正在检测...",
  "one second": "请稍候",
  "What happens": "安装步骤",
  "Get the driver.": "获取驱动。",
  "Download it": "下载驱动",
  "Look before touching anything.": "改前预览。",
  " 1401 reads your OpenCore config and lists every change it would make. Nothing is changed. (macOS asks for your password.) ": " 1401 会读取你的 OpenCore 配置并列出将要进行的全部修改，不会实际改动任何内容（macOS 会要求输入密码）。",
  "Show me the changes": "查看将要进行的修改",
  "Install.": "安装。",
  " Backs up your OpenCore config, makes exactly the changes listed, installs the driver, and adds ": " 备份你的 OpenCore 配置，执行上面列出的修改，安装驱动，并在启动菜单中添加 ",
  " to your boot picker. ": " 启动项。",
  "Install the driver": "安装驱动",
  "Install the driver (get the driver first)": "安装驱动（请先完成第 1 步获取驱动）",
  "Install the driver (press Show me the changes first)": "安装驱动（请先点击“查看将要进行的修改”）",
  "Step 1 has not found the driver yet.": "第 1 步尚未找到驱动包。",
  "Step 2 lists every change first; then this button turns on.": "请先在第 2 步查看将要进行的修改，随后此按钮即可点击。",
  "Restart.": "重启。",
  " If macOS says a system extension was blocked, open ": " 如果 macOS 提示系统扩展被拦截，请打开",
  "Privacy & Security": "隐私与安全性",
  ", click Allow, and restart once more. ": "，点击“允许”，然后再重启一次。",
  "Restart now": "立即重启",
  "The startup partition could not be confirmed. Select the OpenCore partition this Mac started from: ": "无法确认启动分区。请选择本机启动所用的 OpenCore 分区：",
  "Choose the config.plist file myself...": "手动选择 config.plist 文件...",
  "What 1401 is doing": "1401 操作日志",
  "Open the log folder": "打开日志文件夹",
  "Updates": "更新",
  "1401 checks for the newest NullMoth driver and the newest 1401 app. The app updates itself and reopens. The driver is downloaded, checked against its published SHA-256 and installed the same way as above, with your OpenCore config backed up first.": "1401 会检查最新的 NullMoth 驱动和最新的 1401 应用。应用会自动更新并重新打开；驱动会下载并校验公开的 SHA-256，在备份 OpenCore 配置后按上述相同方式完成安装。",
  "Check for updates": "检查更新",
  "Update driver": "更新驱动",
  "Update the app": "更新应用",
  "Early updates.": "先行更新。",
  " A new driver goes first to people who turn this on, and reaches everyone once their machines show it made nothing worse. Turn it on to get releases a day or two early and send logs when something is off.": " 新版驱动会优先推送给开启此项的用户，待验证稳定后再向所有人发布。开启后可提前一两天获取新版本，并在遇到问题时发送日志。",
  "Turn early updates on": "开启先行更新",
  "Turn early updates off": "关闭先行更新",
  "Update to macOS 26 Tahoe": "升级到 macOS 26 Tahoe",
  "From macOS 15, ": "在 macOS 15 下，",
  "Prepare this Mac for Tahoe": "为 Tahoe 准备本机",
  " installs or updates the driver, parks it, and gives the installer the small GPU BAR it needs so its screens show. Then install macOS 26 from Software Update; the first start after the update sets the driver up for Tahoe and restarts once by itself. ": " 会安装或更新驱动并暂时停用它，同时为安装器设置所需的小容量显卡 BAR 窗口以正常显示画面。随后请在“软件更新”中安装 macOS 26；更新后首次启动会自动完成 Tahoe 驱动配置并重启一次。",
  "Cancel the Tahoe preparation": "取消 Tahoe 准备状态",
  " puts everything back.": " 可恢复全部原始设置。",
  "Open Software Update": "打开软件更新",
  "If something goes wrong after you restart": "重启后如果遇到问题",
  "In the OpenCore boot picker choose ": "在 OpenCore 启动菜单中选择 ",
  ", then your macOS disk. 1401 removes the driver and restarts, and this Mac comes back as it was before the install, OpenCore config included. The screen may stay dark until that second restart.": "，然后选择你的 macOS 磁盘。1401 会移除驱动并重启，将本机（包括 OpenCore 配置）恢复到安装前的状态。在第二次重启前屏幕可能会保持黑屏。",
  "Remove the driver": "卸载驱动",
  "Check my EFI": "检查我的 EFI",
  "Checks the OpenCore setup this Mac starts from against the settings that work on PCs like yours, and explains anything that needs changing, with the steps. It only reads: nothing is changed. Asks for your password once.": "对照同类 PC 的有效设置检查本机启动所用的 OpenCore 配置，并列出需要修改的项及具体步骤。仅读取而不做任何改动，需要输入一次密码。",
  "Mount EFI": "挂载 EFI",
  "The EFI partition holds your boot setup. 1401 finds the one this Mac started from, mounts it and opens it in Finder. Asks for your password once.": "EFI 分区保存着你的引导配置。1401 会找到本机启动所用的 EFI 分区，将其挂载并在访达中打开。需要输入一次密码。",
  "Startup text (verbose mode)": "启动文字（啰嗦模式 Verbose）",
  "Shows what macOS is doing while it starts instead of the Apple logo. Useful if a start hangs. Takes effect at the next restart.": "启动时显示 macOS 的详细加载日志而非 Apple 标志，便于排查卡死问题。下次重启时生效。",
  "Turn verbose on": "开启啰嗦模式",
  "Turn verbose off": "关闭啰嗦模式",
  "Built-in screen brightness (laptops)": "内置屏幕亮度调节（笔记本）",
  "For a laptop whose built-in screen is wired to the NVIDIA GPU (MUX set to Discrete or dGPU). It lets the driver read the panel's brightness controls from the laptop's firmware. It is off by default because that call stopped some PCs at GPU start; if yours stops there, choose ": "适用于内置屏幕直连 NVIDIA 独显（MUX 设为独显直连 / dGPU）的笔记本，允许驱动从固件读取屏幕亮度控制。因该调用会导致部分机器在显卡初始化时卡住，故默认关闭；若你的机器卡住，请在启动菜单选择 ",
  " in the boot picker and turn it off here.": " 启动并在本页将其关闭。",
  "Turn brightness control on": "开启亮度调节",
  "Turn it off": "关闭",
  "HiDPI (Retina) modes": "HiDPI（视网膜）缩放模式",
  "Lets HiDPI \"looks like\" sizes work, for example 1920 x 1080 on a 2560 x 1440 screen, including ones added with a tool such as BetterDisplay. Without it such a size is refused and switches back. The driver draws the desktop at up to twice the screen's size, which uses more video memory. Takes effect at the next restart.": "允许使用 HiDPI 缩放分辨率（例如在 2560 x 1440 屏幕上使用“看起来像 1920 x 1080”，包括通过 BetterDisplay 等工具添加的分辨率）。未开启时此类分辨率会被拒绝并回退。驱动会以最高两倍于屏幕的分辨率渲染桌面，因此会占用更多显存。下次重启时生效。",
  "Turn HiDPI modes on": "开启 HiDPI 模式",
  "Turn them off": "关闭",
  "Automatic login": "自动登录",
  "1401 turned on automatic login so this Mac could reach the desktop while the driver was missing. That stores your password in a form anyone who can read the disk can recover. Once the driver works, turn it off.": "此前在未安装驱动时，1401 开启了自动登录以便本机能进入桌面。这会将密码以可被读取磁盘者还原的形式保存。驱动正常工作后请将其关闭。",
  "Turn automatic login off": "关闭自动登录",
  "Hybrid laptop (the built-in screen runs on the Intel or AMD processor graphics)": "混合显卡笔记本（内置屏幕连接在 Intel 或 AMD 核显上）",
  "Most gaming laptops wire the built-in screen to the graphics in the processor, so the NVIDIA card has nothing to draw it on. This installs a panel driver beside the NVIDIA driver (the Intel one on Intel graphics, the AMD one on a Ryzen with Radeon graphics): the NVIDIA card does the rendering and each finished frame goes to the screen through the processor graphics. On Ryzen laptops turn the OpenCore Fix PAT patch off first (docs/HYBRID-LAPTOPS.md); only copy is available there. ": "大多数游戏本将内置屏幕连接在处理器核显上，因此 NVIDIA 显卡无法直接向其输出画面。此功能会在 NVIDIA 驱动旁安装一个内屏驱动（Intel 核显安装 Intel 版，带 Radeon 核显的锐龙安装 AMD 版）：由 NVIDIA 显卡负责渲染，每帧完成后通过核显输出到内屏。在锐龙笔记本上请先关闭 OpenCore 的 Fix PAT 补丁（见 docs/HYBRID-LAPTOPS.md），且仅支持复制模式。",
  "Copy": "复制（Copy）",
  " works on Intel 11th generation and newer; ": " 适用于 11 代及更新的 Intel；",
  "scan out in place": "就地扫描输出（scan out in place）",
  " is the faster level for 12th and 13th generation. It has not run on a hybrid laptop yet, so your Send logs are how it gets fixed. It needs the NVIDIA driver already installed and the driver package checked above.": " 是面向 12 代与 13 代的更快模式。如有异常请通过“发送日志”反馈。需要先安装 NVIDIA 驱动并在上方校验驱动包。",
  "If the screen stays dark, choose ": "如果屏幕保持黑屏，请在启动菜单中选择 ",
  " in the boot picker and turn it off here. Turning it off also takes the panel driver out again.": "，然后在此处将其关闭。关闭时也会一并移除内屏驱动。",
  "Turn on (copy)": "开启（复制模式）",
  "Turn on (scan out in place)": "开启（就地扫描输出）",
  "Drives behind Intel VMD or RAID": "处于 Intel VMD 或 RAID 下的磁盘",
  "macOS can only use drives the firmware shows as plain AHCI or NVMe disks. This PC has Intel VMD or RAID storage, so its internal drives may be hidden from macOS. Two ways round it:": "macOS 只能使用固件以普通 AHCI 或 NVMe 呈现的磁盘。本机启用了 Intel VMD 或 RAID 存储，因此内置磁盘可能对 macOS 不可见。有两种解决方法：",
  "Install on an external drive.": "安装在外置磁盘上。",
  " Plug in a USB SSD (or an SSD that is not behind VMD) and install macOS on it from the 1401 stick. The internal drive and Windows are not touched. In 1401 for Windows tick ": " 插入移动固态硬盘（或未挂载在 VMD 下的 SSD），从 1401 启动盘将 macOS 安装到该盘上，内置磁盘与 Windows 不受影响。在 Windows 版 1401 构建前请勾选 ",
  " before you build.": "。",
  "Turn VMD off.": "关闭 VMD。",
  " In 1401 for Windows the build shows the BIOS path for your board and offers ": " Windows 版 1401 构建时会显示对应主板的 BIOS 路径，并提供 ",
  ": Prepare makes a restore point, pauses BitLocker and sets the standard drivers, you switch VMD off in the BIOS, Finish returns Windows to a normal start, and Undo puts every value back. These steps run on Windows only, so this app only explains them.": "：Prepare 会创建还原点、暂停 BitLocker 并配置标准驱动，随后你在 BIOS 中关闭 VMD，Finish 让 Windows 恢复正常启动，Undo 则可将所有设置还原。这些步骤仅在 Windows 下运行，此处仅作说明。",
  "Experimental drivers and features": "实验性驱动与功能",
  "Select all": "全选",
  "Deselect all": "取消全选",
  "Written and tested offline, not yet measured on every machine. Each is ": "已完成离线编写与测试，尚未在所有机型上实测。每项默认均为",
  "off": "关闭",
  " until you tick it and press Apply, and each needs a ": "状态，勾选并点击“应用”后启用，且需要",
  "restart": "重启",
  ". Untick and Apply to put things back exactly as they were; arguments you set yourself are never removed.": "后生效。取消勾选并点击“应用”即可原样恢复；你自己手动设置的参数不会被移除。",
  "Keyboard backlight": "键盘背光",
  " Laptop keyboard backlight keys and level (the NMKbdBacklight kext). A driver OpenCore loads: an EFI built by 1401 2.9 already carries it switched off, and Apply switches it on there (on an older EFI it is copied in from the installed NVIDIA driver first). Needs VirtualSMC. Built and checked offline; it has not yet run on a laptop.": " 笔记本键盘背光快捷键与亮度调节（NMKbdBacklight kext）。由 OpenCore 加载：1401 2.9 构建的 EFI 已内置该驱动（默认关闭），点击“应用”即可启用（旧版 EFI 会先从已安装的 NVIDIA 驱动中复制）。需要 VirtualSMC。",
  "NVIDIA display sound with volume (macOS 15)": "支持音量调节的 NVIDIA 显示器音频（macOS 15）",
  " HDMI and DisplayPort sound from the NVIDIA card through Apple's HD Audio driver, with a working volume slider and mute (the NMHDA driver). A driver OpenCore loads, handled like the keyboard backlight. macOS 15 only: macOS 26 uses NMXAudio.": " 通过 Apple HD Audio 驱动输出 NVIDIA 显卡的 HDMI 与 DisplayPort 音频，支持音量滑块与静音（NMHDA 驱动）。仅限 macOS 15：macOS 26 使用 NMXAudio。",
  "Keyboard backlight, HID route": "键盘背光（HID 通道）",
  " The same through the HID route some laptops use. Needs the item above.": " 通过部分笔记本使用的 HID 通道控制键盘背光。需要同时勾选上方键盘背光项。",
  "Laptop GPU power budget": "笔记本显卡功耗上限（Dynamic Boost）",
  " Lets the NVIDIA GPU use the platform's full power limit while on mains power (Dynamic Boost); released on battery.": " 接通电源时允许 NVIDIA 显卡使用平台完整功耗上限（Dynamic Boost）；使用电池时自动释放。",
  "Panel on the integrated GPU": "核显内屏代理输出",
  " Hybrid laptops: shows the built-in screen through a proxy head when the panel is wired to the integrated GPU.": " 混合显卡笔记本：当内屏连接在核显上时，通过代理输出头显示内置屏幕。",
  "AMD / Intel video decode": "AMD / Intel 硬件视频解码",
  " AV1 and VP9 hardware decode on AMD and Intel GPUs.": " 在 AMD 与 Intel 显卡上启用 AV1 和 VP9 硬件解码。",
  "Hybrid laptops: newest Intel graphics": "混合显卡笔记本：最新一代 Intel 核显支持",
  " Lets the hybrid panel driver replay a wake on Lunar Lake and Panther Lake graphics. Only matters with hybrid laptop mode on; written from Linux's display code and not yet run on that hardware.": " 允许混合内屏驱动在 Lunar Lake 与 Panther Lake 核显上重放唤醒流程。仅在开启混合笔记本模式时生效。",
  "Idle GPU deep sleep": "空闲显卡深度休眠（RTD3）",
  " Lets the NVIDIA card drop into its deepest idle power state (runtime D3) when nothing is using it. Written and tested offline; its savings and its wake-up are measured on the studio machine before it is recommended.": " 当没有程序使用 NVIDIA 显卡时，允许其进入最深的空闲低功耗状态（runtime D3）。",
  "Idle link power saving": "空闲 PCIe 链路省电（ASPM L1）",
  " Asks the PCIe link between the NVIDIA card and the motherboard to rest (ASPM L1) while the card is idle, where both ends support it. Off by default: the driver leaves the link as the firmware set it, because a link that rests on a board not built for it can stall or drop the card. Turn it off again if the screen freezes when the machine is idle.": " 在显卡空闲且两端均支持时，让 NVIDIA 显卡与主板之间的 PCIe 链路进入休眠（ASPM L1）。默认关闭；若机器空闲时画面卡死，请将其关闭。",
  "Game GPU priority": "游戏 GPU 优先级提升",
  " Raises a game's GPU priority.": " 提高游戏的 GPU 调度优先级。",
  "Hardware ray queries": "硬件光线追踪查询（RT Cores）",
  " Ray queries on the RT cores through NullMoth's own acceleration structures.": " 通过 NullMoth 自有加速结构在 RT 核心上执行光线查询。",
  "Curve primitives in ray tracing": "光线追踪曲线图元",
  " Curves in ray queries (software traversal, so slower).": " 支持光线查询中的曲线图元（软件遍历，速度较慢）。",
  "Metal tile shading": "Metal 分块着色（Tile Shading）",
  " Tile shading for apps that use it.": " 为使用该特性的应用提供分块着色支持。",
  "GPU-encoded command lists": "GPU 编码命令列表（ICB）",
  " Indirect command buffers written by the GPU.": " 支持由 GPU 写入的间接命令缓冲区（Indirect Command Buffers）。",
  "Apply": "应用",
  "GPU boost": "显卡高频保持（GPU Boost）",
  "Holds the NVIDIA card at its maximum clocks while this is on, for work that is limited by the GPU's idle-to-busy ramp-up. It costs power and heat, so it is off until you turn it on. It installs a small background job from the checked driver package; the package's file list is verified before anything runs as root. Turning it off stops it holding the boost; Remove takes the job off this Mac.": "开启期间使 NVIDIA 显卡保持最高频率运行，适用于受显卡空闲升频延迟影响的工作负载。会增加功耗与发热，故默认关闭。开启时会从已校验的驱动包中安装一个后台任务；关闭即停止锁频，“移除任务”则会将其从本机卸载。",
  "Turn on": "开启",
  "Turn off": "关闭",
  "Remove the job": "移除任务",
  "Status": "状态",
  "Ryzen laptop power profile": "锐龙笔记本功耗配置",
  "A Ryzen laptop runs at the processor's default power limits, which are loud and hot on a battery. This sets a quieter profile (by default 13 W sustained, 14 W slow, 15 W fast, 70 °C; change the limits below before you turn it on) through NullMoth's RyzenAdj build. It installs a small kernel extension that can talk to the processor's power controller only after you turn this on, and a job that runs as root. It is off until you choose it.": "锐龙笔记本默认按处理器原厂功耗上限运行，使用电池时风扇较吵且发热明显。此功能通过 NullMoth 的 RyzenAdj 构建设置更安静的功耗配置（默认持续 13 W、慢速 14 W、快速 15 W、温度上限 70 °C；可在开启前于下方修改）。仅在开启后才会安装与处理器电源控制器通信的内核扩展及后台任务。",
  "If anything goes wrong, turn it off here: that removes the job, the kernel extension and the boot setting.": "如果出现任何问题，在此处将其关闭即可：这会一并移除后台任务、内核扩展和启动参数。",
  "Watts: sustained ": "功率（W）：持续 ",
  " slow ": " 慢速 ",
  " fast ": " 快速 ",
  " \u00a0 Temperature limit ": " \u00a0 温度上限 ",
  " °C (watts 5 to 65, sustained at most slow at most fast; temperature 50 to 100)": " °C（功率 5 至 65，持续 ≤ 慢速 ≤ 快速；温度 50 至 100）",
  "AMD / Intel GPU and NPU driver (test)": "AMD / Intel 显卡与 NPU 驱动（测试版）",
  "For the AMD and Intel GPUs macOS has no driver for (Ryzen APUs, Radeon RX 7000/9000, Intel Iris Xe and Arc graphics), and the NPU in Intel Core Ultra and AMD Ryzen AI processors. An early test build: your Send logs are how it gets fixed. It downloads only the firmware your GPU and NPU need from linux-firmware (every file checked) and takes effect at the next restart.": "面向 macOS 无原生驱动的 AMD 与 Intel 显卡（锐龙 APU、Radeon RX 7000/9000、Intel Iris Xe 与 Arc 显卡），以及 Intel Core Ultra 和 AMD Ryzen AI 处理器中的 NPU。当前为早期测试版，请通过“发送日志”帮助完善。它仅从 linux-firmware 下载你的显卡和 NPU 所需的固件（逐个校验），并在下次重启时生效。",
  "If that GPU drives your screen, the screen can stay dark. Then choose ": "如果该显卡直接驱动屏幕，重启后可能会黑屏。届时请在启动菜单中选择 ",
  " in the boot picker (it parks this driver too) and turn it off here.": "（同样会停用此驱动），然后回到此处将其关闭。",
  "Turn the test driver on": "开启测试版驱动",
  "Test program.": "测试计划。",
  " While the test driver is on, 1401 sends a short report after every restart: the driver's kernel messages, any crash, and which GPU and build you have (names and serial numbers removed). Leave at any time.": " 开启测试版驱动期间，1401 会在每次重启后发送一份简短报告：包含驱动内核日志、崩溃记录以及显卡型号与版本（已移除用户名和序列号）。可随时退出。",
  "Join the test program": "加入测试计划",
  "Leave it": "退出计划",
  "Intel Xe graphics (WhateverXe, test)": "Intel Xe 核显（WhateverXe，测试版）",
  "For Tiger Lake, Alder Lake and Raptor Lake Intel graphics on macOS 15.8 or 26.7 and later. It uses ": "适用于运行 macOS 15.8 或 26.7 及更高版本的 Tiger Lake、Alder Lake 和 Raptor Lake Intel 核显。它使用 b00t0x 开发的 ",
  " by b00t0x: 1401 adds it to OpenCore, you restart, then press ": "：1401 会先将其加入 OpenCore，你重启后再次点击 ",
  "Turn it on": "开启",
  " again to install its graphics package. Those parts come straight from the author's GitHub, each checked. WhateverGreen is turned off while it is on; ": " 以安装其图形组件包（直接从作者 GitHub 下载并逐一校验）。开启期间会自动停用 WhateverGreen；点击 ",
  "If the screen stays dark after the restart, choose ": "如果重启后屏幕黑屏，请在启动菜单中选择 ",
  " in the boot picker: that start also leaves WhateverXe off. Then turn it off here.": "：该启动方式同样会停用 WhateverXe，随后在此处将其关闭即可。",
  "Game Mode": "游戏模式（Game Mode）",
  "While a game is in front and full screen, this gives it the processor first, holds back background indexing and other apps' use of the graphics card, and puts everything back when you leave the game. A game controller shows in the menu bar while it is on. It stays off until you turn it on, and turning it off removes it.": "当游戏处于前台全屏运行时，优先为其分配处理器资源，抑制后台索引及其他应用对显卡的占用，并在退出游戏时恢复原状。开启期间菜单栏会显示游戏手柄图标。默认关闭，关闭时即完全移除。",
  "Microphone and camera": "麦克风与摄像头权限",
  "With the driver installed, macOS does not ask before an app uses the microphone or camera, so apps such as Discord get silence and never appear under Privacy & Security. Pick the app here to allow it the microphone, camera and screen recording.": "安装驱动后，macOS 不会在应用调用麦克风或摄像头前弹出授权询问，导致 Discord 等应用无声且不会出现在“隐私与安全性”列表中。在此处选择应用即可授予其麦克风、摄像头与屏幕录制权限。",
  "Allow an app...": "授权应用...",
  "Driver settings": "驱动设置",
  "HDR, 10-bit colour, variable refresh, colour range, scaling, surround, frame-rate limit and more, with your GPUs' link and memory facts. Every change is shown in full and asked for first.": "包含 HDR、10-bit 色深、可变刷新率（VRR）、色彩范围、缩放、多屏拼接、帧率限制等选项，以及显卡链路与显存状态。每项修改都会先完整展示并征得你的确认。",
  "Open driver settings...": "打开驱动设置...",
  "Map my GPU (experimental)": "测量我的显卡（实验性）",
  "A few minutes of measurements on this Mac's GPU: what Metal reports, a correctness check, memory and compute speed, and small test shaders. Nothing is changed and no display mode is touched. The result goes in the log folder, and Send logs uploads it so the next driver can be tuned for your card.": "用几分钟时间对本机显卡进行测量：包含 Metal 报告信息、正确性检查、显存与计算速度以及小型测试着色器。不会改动任何系统设置或显示模式。结果保存在日志文件夹中，并通过“发送日志”上传，以便后续驱动针对你的显卡进行优化。",
  "Map my GPU": "测量我的显卡",
  "ARM apps (opt-in)": "ARM 应用支持（可选）",
  "Not now": "暂不开启",
  "Apps built only for Apple silicon can be translated to run on this Mac. An iPhone or iPad app you built yourself (an .ipa that is not App Store encrypted) is first made into a Mac app, then translated. Translation takes minutes for a small app and up to an hour or more for a big one. The original app is never changed: the translated copy goes to Applications > NullMoth ARM. Turning this off removes the translator and the translated copies, and your 2.7 driver keeps working.": "将仅支持 Apple 芯片（ARM）的应用转译为可在本机运行的版本。你自己构建的 iPhone 或 iPad 应用（未加 App Store 加密的 .ipa）会先转换为 Mac 应用再进行转译。小型应用转译需数分钟，大型应用可能需一小时以上。原应用不会被改动，转译后的副本保存在“应用程序 > NullMoth ARM”。关闭此功能会移除转译器及转译副本，不影响显卡驱动。",
  "Check this Mac": "检测本机兼容性",
  "Install Command Line Tools": "安装 Command Line Tools",
  "Translate an app...": "转译应用...",
  "Cancel": "取消",
  "Two Homebrews side by side, as on a Mac with Apple silicon: the ARM one in /opt/homebrew installs Homebrew's Apple-silicon packages and translates them for this Mac; the Intel one in /usr/local runs natively but mostly builds from source, because Homebrew stopped publishing Intel packages. In Terminal, ": "像 Apple 芯片 Mac 一样并存两套 Homebrew：位于 /opt/homebrew 的 ARM 版用于安装 Apple 芯片软件包并自动转译；位于 /usr/local 的 Intel 版原生运行（但因 Homebrew 已停止发布 Intel 预编译包，大多需从源码编译）。在终端里，",
  " is always ARM, ": " 始终代表 ARM 版，",
  " always Intel, and ": " 始终代表 Intel 版，而 ",
  " is the one you pick here.": " 则指向你在下方选择的默认版本。",
  "ARM and Intel": "同时安装 ARM 与 Intel 版",
  "ARM only (/opt/homebrew)": "仅安装 ARM 版 (/opt/homebrew)",
  "Intel only (/usr/local)": "仅安装 Intel 版 (/usr/local)",
  "Set up Homebrew": "配置 Homebrew",
  "Map your USB ports": "定制 USB 端口映射",
  "macOS only uses 15 ports per USB controller and has no idea which ones your case actually has. 1401 watches the ports while you plug things in, then writes a map for the ports you select. Test them again after restarting, including USB-C both ways round and wake from sleep.": "macOS 对每个 USB 控制器最多只启用 15 个端口，且无法自动获知机箱实际连接的物理接口。1401 会在你插拔设备时监听端口变化，并为你勾选的端口生成映射驱动。重启后请再次测试各端口（包括正反插 USB-C 及睡眠唤醒）。",
  "Start watching.": "开始监听。",
  "Start": "开始监听",
  "Watching...": "正在监听...",
  "Plug something into each port you use, one at a time.": "在每个常用端口上逐一插拔设备。",
  " A USB 3 stick is best; do each USB-C port both ways round. A port turns ": " 建议使用 USB 3 U 盘；每个 USB-C 口请正反两面各插一次。识别到的端口会变为",
  "green": "绿色",
  " when 1401 sees it.": "。",
  "Check the list": "核对列表",
  ", pick the plug type for each port, and ": "，为每个端口选择接口类型，然后点击 ",
  "Write the map": "写入端口映射",
  " (macOS asks for your password; your OpenCore config is backed up first).": "（macOS 会要求输入密码；写入前会先备份你的 OpenCore 配置）。",
  "Something still wrong?": "仍然遇到问题？",
  "Send logs": "发送日志",
  "1401 sends what it did, the driver's state, crash reports, OpenCore's startup logs and a numeric device map, with names, serial numbers and addresses removed. You get a report ID to post in the NullMoth Discord.": "1401 会发送操作记录、驱动状态、崩溃报告、OpenCore 启动日志以及数字化的设备映射表（已移除用户名、序列号和硬件地址）。发送后你会获得一个报告 ID，可发到 NullMoth Discord 寻求帮助。",
  "If the driver could not translate a shader, up to 24 of those shaders (at most 4 MB, from the apps you ran) are attached so the failure can be reproduced. They are sent only when you press the button. To stop the driver keeping them, create the empty file /Library/GPUBundles/nvmtl/no-failed-air.": "如果驱动未能成功转译某个着色器，最多会附带 24 个失败的着色器文件（总计不超过 4 MB，来自你运行过的应用）以便复现问题。它们仅在你点击发送按钮时才会上传。若不想让驱动保留这些文件，可创建空文件 /Library/GPUBundles/nvmtl/no-failed-air。",
  "Send logs to NullMoth": "发送日志至 NullMoth",
  "Record the flicker": "录制屏幕闪烁",
  "Record the flicker: press it while the screen flickers. 1401 records 20 seconds of how the driver puts frames on the display and sends it with your logs.": "录制屏幕闪烁：请在屏幕发生闪烁时点击。1401 会录制 20 秒内驱动向显示器提交帧画面的时序数据，并随日志一并发送。",
  "Crash report": "崩溃报告",
  "If the driver ever crashes this Mac, 1401 asks at the next login whether to make a report. It is a text file on your Desktop with your hardware and what failed, with your name, your Mac's name, serial numbers, addresses and file paths taken out. ": "如果驱动曾导致本机崩溃，1401 会在下次登录时询问是否生成崩溃报告。报告是保存在桌面上的文本文件，记录硬件信息与故障详情（已移除你的名字、Mac 名称、序列号、地址和文件路径）。",
  "1401 never sends it by itself.": "1401 绝不会自行上传该文件。",
  "Make a report": "生成本地报告",
  "Open the upload page": "打开上传页面",
  "Buy me a coffee": "请作者喝杯咖啡",
  "Credits": "致谢",
  "Optional diagnostics": "可选诊断",
  "Capture is unavailable in this version. Send logs still collects hardware, kernel and panic evidence. No security settings have changed.": "当前版本不可用追踪捕获。“发送日志”仍会收集硬件、内核与崩溃日志。未更改任何安全设置。",
  "Check optional diagnostics": "检查可选诊断",
  "Import saved receipt": "导入已保存的回执",
  "Checking availability starts no trace. A saved receipt needs its own session upload permission and a separate Send logs confirmation.": "检查可用性不会启动任何追踪。已保存的回执需要其所属会话的上传许可，并在“发送日志”时单独确认。",
  "© 2026 NullMoth Systems. NullMoth and the moth logo are trademarks of NullMoth Systems.": "© 2026 NullMoth Systems。NullMoth 与飞蛾标志是 NullMoth Systems 的商标。",
  "Checking...": "正在检查...",
  "Reading the EFI...": "正在读取 EFI...",
  "Finding the EFI...": "正在查找 EFI...",
  "Pick the app...": "请选择应用...",
  "Starting...": "正在启动...",
  "Cancelling...": "正在取消...",
  "Waiting for your Mac password...": "正在等待输入 Mac 密码...",
  "Collecting and sending...": "正在收集并发送日志...",
  "Recording the display for 20 seconds, then sending...": "正在录制 20 秒显示状态并发送...",
  "Measuring (1 of 5): identity...": "正在测量（1 / 5）：设备识别...",
  "Measuring (2 of 5): correct...": "正在测量（2 / 5）：正确性检查...",
  "Measuring (3 of 5): bench...": "正在测量（3 / 5）：显存与计算基准...",
  "Measuring (4 of 5): corpus...": "正在测量（4 / 5）：测试着色器...",
  "Measuring (5 of 5): displays and driver state...": "正在测量（5 / 5）：显示器与驱动状态...",
  "Not on this Mac yet.": "本机尚未下载驱动包。",
  "A copy was found but its checksum is wrong. Download a fresh one.": "找到了驱动包副本，但校验和不一致。请重新下载。",
  "This Mac already runs macOS 26.": "本机已在运行 macOS 26。",
  "Download the driver package": "下载驱动包",
  "No crash that names the driver is on this Mac.": "本机没有与该驱动相关的崩溃记录。",
  "On: new drivers reach this Mac first, before they are offered to everyone.": "已开启：新版驱动会在向所有人推送前优先提供给本机。",
  "Off: this Mac gets releases once they have held up for everyone who went first.": "已关闭：本机将在新版驱动经先行用户验证稳定后接收更新。",
  "Before you edit config.plist, keep a copy of it. If a change stops this Mac from starting, start from your 1401 stick and put the copy back.": "编辑 config.plist 前请先备份一份副本。如果修改后无法启动，可从 1401 启动盘引导并还原该副本。",
  "WhateverGreen can crash macOS 26 with your AMD graphics card": "WhateverGreen 在搭载 AMD 显卡的 macOS 26 上可能导致崩溃",
  "On macOS 26 Tahoe, WhateverGreen's AMD display patching can panic at startup. Machines with an AMD card and no Intel graphics run without it.": "在 macOS 26 Tahoe 下，WhateverGreen 的 AMD 显示补丁可能在启动时触发内核崩溃。配备 AMD 独显且无 Intel 核显的机器无需加载它即可正常运行。",
  "Intel Bluetooth needs one boot setting on macOS 26": "Intel 蓝牙在 macOS 26 下需要添加一项启动参数",
  "The Intel Bluetooth driver only loads on macOS 26 Tahoe with -ibtcompatbeta in boot-args.": "Intel 蓝牙驱动在 macOS 26 Tahoe 下需要在 boot-args 中添加 -ibtcompatbeta 才会加载。",
  "macOS 26 updates can stop at the prohibited sign": "macOS 26 更新可能会卡在禁止符号界面",
  "macOS 26 checks the Mac model during startup and updates. RestrictEvents answers that check when revpatch includes sbvmm.": "macOS 26 在启动与更新时会检查机型。当 revpatch 包含 sbvmm 时，RestrictEvents 会响应该检查。",
  "CpuTopologyRebuild freezes desktop Arrow Lake installs": "CpuTopologyRebuild 会导致桌面端 Arrow Lake 安装卡死",
  "With CpuTopologyRebuild loaded, the installer froze right after \"PCI configuration end\" on Core Ultra 200 desktops. The configuration that installed and runs macOS 15 on a Core Ultra 5 225F does not load it.": "加载 CpuTopologyRebuild 时，Core Ultra 200 桌面端会在“PCI configuration end”后卡死。实测成功运行 macOS 15 的配置不加载该驱动。",
  "Core Ultra PCs freeze before macOS starts with VT-d on": "开启 VT-d 时 Core Ultra 电脑会在 macOS 启动前卡死",
  "Every Core Ultra PC that reached the desktop had VT-d off. Dropping VT-d's table in OpenCore does the same for macOS, and works where the BIOS hides the switch. Windows and Linux keep VT-d.": "在 OpenCore 中忽略 VT-d 的 DMAR 表可让 macOS 不使用 VT-d（即便 BIOS 隐藏了开关也有效），同时不影响 Windows 和 Linux 使用 VT-d。",
  "VT-d has to stay out of macOS on Core Ultra": "Core Ultra 在 macOS 下需要禁用 VT-d 映射",
  "DisableIoMapper keeps macOS from using VT-d, which Core Ultra PCs need to start.": "DisableIoMapper 可阻止 macOS 使用 VT-d，这是 Core Ultra 电脑正常启动所必需的。",
  "12th-gen and newer Intel laptops stop at EXITBS:START with DevirtualiseMmio on": "12 代及更新的 Intel 笔记本开启 DevirtualiseMmio 时会卡在 EXITBS:START",
  "On Intel laptops with performance and efficiency cores, startup can fault before macOS starts with DevirtualiseMmio on. Six of seven public laptop setups that run macOS on these CPUs have it off.": "在带有大小核的 Intel 笔记本上，开启 DevirtualiseMmio 可能导致启动异常。绝大多数成功运行 macOS 的同代笔记本配置均将其关闭。",
  "Core Ultra 200 desktops start with DevirtualiseMmio on": "Core Ultra 200 台式机需要开启 DevirtualiseMmio",
  "A Core Ultra 5 225F desktop runs macOS 26 with DevirtualiseMmio on, and in our reports Arrow Lake desktops reached the installer only with it on (2 of 20 on, 0 of 11 off).": "实测 Arrow Lake 台式机仅在开启 DevirtualiseMmio 时能顺利进入安装器并运行 macOS 26。",
  "This EFI can wipe your installed system's boot settings": "当前 EFI 可能会抹掉已安装系统的启动参数",
  "With boot-args under NVRAM > Delete, one start from this EFI replaces the boot flags an installed macOS needs, and it can then refuse to start.": "当 NVRAM > Delete 中包含 boot-args 时，从该 EFI 启动会清除已安装 macOS 所需的启动标志。",
  "A failed start leaves no log": "启动失败时未保存日志文件",
  "With file logging on, OpenCore saves its log and any macOS panic to the EFI partition, so 1401 can tell you why a start failed instead of you photographing the screen.": "开启文件日志后，OpenCore 会将引导日志和 macOS 崩溃记录保存到 EFI 分区，方便 1401 直接分析启动失败原因，无需拍照排错。",
  "The macOS installer is hidden in the boot menu": "启动菜单中隐藏了 macOS 安装器条目",
  "The installer is a recovery entry, which OpenCore hides with HideAuxiliary on. The boot menu then shows only Windows.": "安装器属于辅助恢复条目，开启 HideAuxiliary 时会被 OpenCore 隐藏，导致启动菜单只显示 Windows。",
  "The boot menu never appears": "启动菜单未设置为自动显示",
  "Without the boot menu you can't pick the installer, or the Remove NVIDIA driver entry if the driver ever stops your desktop.": "不显示启动菜单时，你将无法选择安装器，也无法在驱动异常时选择“Remove NVIDIA driver”恢复条目。",
  "The boot menu can't show the Remove driver entry": "当前启动菜单样式无法显示“移除驱动”工具项",
  "Apple's boot menu style lists only systems, never OpenCore tools, so the driver's Remove entry can't appear in it.": "Apple 原生风格的启动菜单仅列出操作系统而不显示 OpenCore 工具项，因此无法显示驱动移除条目。",
  "1401 can't tell which EFI your Mac started from": "1401 无法识别本机是从哪个 EFI 分区启动的",
  "OpenCore shares which partition it started from only when ExposeSensitiveData includes 1. It shares the boot path only, no serial numbers.": "只有当 ExposeSensitiveData 包含位 1 时，OpenCore 才会向系统提供启动分区路径（仅公开路径，不含序列号）。",
  "A file is listed twice in config.plist": "config.plist 中存在重复列出的文件条目",
  "OpenCore's validator refuses a config that lists the same SSDT or kext twice. The second copy never did anything.": "OpenCore 校验器会拒绝重复列出相同 SSDT 或 kext 的配置文件，多余的重复项没有任何作用。",
  "USBInjectAll and USBToolBox are both on": "同时启用了 USBInjectAll 与 USBToolBox",
  "Both kexts map USB ports, and configs with both on crashed at startup with \"element modified after free\", sometimes before the NVIDIA driver loaded. USBToolBox with its UTBMap.kext is the one to keep.": "这两个驱动都会映射 USB 端口，同时开启会在启动时引发“element modified after free”内核崩溃。请保留 USBToolBox 及其 UTBMap.kext。",
  "IntelMausi and IntelSnowMausi are both on": "同时启用了 IntelMausi 与 IntelSnowMausi",
  "Both kexts drive the same Intel Ethernet controller, and configs with both on crashed at startup with \"element modified after free\". Keep one: IntelMausi is the one for current macOS.": "这两个驱动控制同一个 Intel 有线网卡，同时启用会在启动时引发内核崩溃。当前 macOS 请只保留 IntelMausi。",
  "Ryzen startup stops at EB.MM.AKM with SetupVirtualMap on": "锐龙平台开启 SetupVirtualMap 时启动会卡在 EB.MM.AKM",
  "On Ryzen boards newer than the 300 series, boot.efi can't place the kernel in memory with SetupVirtualMap on (EB.MM.AKM, STOP 0x16).": "在 300 系列之后的锐龙主板上，开启 SetupVirtualMap 会导致 boot.efi 无法在内存中安置内核（EB.MM.AKM）。",
  "Ryzen startup stops at EB.MM.AKM with DevirtualiseMmio on": "锐龙平台开启 DevirtualiseMmio 时启动会卡在 EB.MM.AKM",
  "Every Ryzen 1000 to 5000 stick that passed boot.efi had DevirtualiseMmio off (1 stop in more than 150 boots).": "锐龙 1000 至 5000 系列需要关闭 DevirtualiseMmio 才能顺利通过 boot.efi。",
  "Ryzen 7000, 8000 and 9000 stop at EB.MM.AKM without two memory settings": "锐龙 7000/8000/9000 需要同时开启两项内存设置",
  "On Zen 4 and Zen 5, startup stopped at EB.MM.AKM in 60 boots and passed in 14 with DevirtualiseMmio off. With it and SetupVirtualMap on, boards that had stopped passed on their next start.": "在 Zen 4 与 Zen 5 平台上，需要同时开启 DevirtualiseMmio 和 SetupVirtualMap 才能避免卡在 EB.MM.AKM。",
  "Ryzen 9000 installs froze about 19 minutes in": "锐龙 9000 安装过程可能会在约第 19 分钟时卡死",
  "The installer froze while writing settings to the board's firmware. With DisableVariableWrite on, the install finished. macOS then can't save its own startup disk choice; OpenCore still sets it at every start.": "安装器在向主板固件写入变量时可能卡死，开启 DisableVariableWrite 后即可顺利完成安装。",
  "MmioWhitelist entries are on without DevirtualiseMmio": "启用了 MmioWhitelist 条目但未开启 DevirtualiseMmio",
  "Whitelist entries only do something with DevirtualiseMmio on, and OpenCore's validator refuses them without it.": "白名单条目仅在开启 DevirtualiseMmio 时生效，否则 OpenCore 校验器会报错。",
  "Startup can stop with STOP 0x16 when low memory is full": "低位内存不足时启动可能会停在 STOP 0x16",
  "AllowRelocationBlock gives boot.efi a way to load the kernel when no memory slot fits. It's used only then, so machines that already start never touch it.": "AllowRelocationBlock 可在常规内存空间不足时允许 boot.efi 重定位加载内核。",
  "A kernel patch fails OpenCore's validator": "存在未通过 OpenCore 校验器的内核补丁（Kernel Patch）",
  "Some patch bytes sit outside ReplaceMask, so they're never written and the validator refuses the config. Clearing them changes nothing OpenCore does.": "部分补丁的 Replace 字节超出了 ReplaceMask 范围，导致校验器报错。",
  "macOS can write to your board's firmware in a way that stopped boards from starting": "macOS 向主板固件写入变量可能导致部分 AMD 主板无法开机",
  "With the memory map rewritten, settings macOS saved to firmware stopped several AMD boards from powering on, some needing a BIOS flashback. DisableVariableWrite blocks those writes.": "在重写内存映射的情况下，macOS 向固件写入 NVRAM 变量曾导致部分 AMD 主板无法自检开机。开启 DisableVariableWrite 可拦截此类写入。",
  "macOS 26 stops at the Apple logo with your Realtek Ethernet setup": "macOS 26 在当前 Realtek 有线网卡配置下会卡在 Apple 标志",
  "macOS 26 adds its own Realtek driver, which needs a system part your Wi-Fi setup blocks. Lucy already drives the port, so Apple's driver is blocked too.": "macOS 26 新增了原生 Realtek 驱动，会与无线网卡降级屏蔽的 IOSkywalkFamily 冲突。既然已由 Lucy 驱动有线网卡，屏蔽 Apple 原生驱动即可。",
  "Your NVMe drive can drop out under macOS": "你的 NVMe 固态硬盘在 macOS 下可能会掉盘",
  "This drive model can disappear under macOS power management. NVMeFix clears that on the drive families it's known to help.": "该型号固态硬盘在 macOS 电源管理下可能会掉盘，启用 NVMeFix.kext 可改善此问题。",
  "Open config.plist in EFI/OC.": "打开 EFI/OC 中的 config.plist。",
  "Restart.": "重启电脑。",
  "Under Misc > Debug, add 65 to Target (logging on, written to a file).": "在 Misc > Debug 下，将 Target 加上 65（开启日志并写入文件）。",
  "Set AppleDebug and ApplePanic to true.": "将 AppleDebug 和 ApplePanic 设为 true。",
  "Under Misc > Boot, set ShowPicker to true.": "在 Misc > Boot 下，将 ShowPicker 设为 true。",
  "Under Misc > Boot, set PickerMode to Builtin (or External).": "在 Misc > Boot 下，将 PickerMode 设为 Builtin（或 External）。",
  "Under Misc > Boot, set HideAuxiliary to false.": "在 Misc > Boot 下，将 HideAuxiliary 设为 false。",
  "Under Misc > Security, add 1 to ExposeSensitiveData (6 becomes 7).": "在 Misc > Security 下，给 ExposeSensitiveData 加上 1（例如 6 改为 7）。",
  "Under ACPI > Add and Kernel > Add, delete the second entry of any file listed twice.": "在 ACPI > Add 和 Kernel > Add 下，删除任何重复列出的第二个文件条目。",
  "Under Kernel > Add, set Enabled to false on WhateverGreen.kext.": "在 Kernel > Add 下，将 WhateverGreen.kext 的 Enabled 设为 false。",
  "If boot-args has agdpmod=pikera, remove it and add the AGDP board-id patch under Kernel > Patch instead.": "如果 boot-args 中有 agdpmod=pikera，请将其移除，改为在 Kernel > Patch 下添加 AGDP board-id 补丁。",
  "Under NVRAM > Add > 7C436110-AB2A-4BBB-A880-FE41995C9F82, add -ibtcompatbeta to boot-args.": "在 NVRAM > Add > 7C436110-AB2A-4BBB-A880-FE41995C9F82 下，向 boot-args 添加 -ibtcompatbeta。",
  "In boot-args, add revpatch=sbvmm (or add ,sbvmm to an existing revpatch=).": "在 boot-args 中添加 revpatch=sbvmm（或在已有的 revpatch= 后追加 ,sbvmm）。",
  "Under Kernel > Add, set Enabled to false on CpuTopologyRebuild.kext.": "在 Kernel > Add 下，将 CpuTopologyRebuild.kext 的 Enabled 设为 false。",
  "Remove any ctrsmt option from boot-args.": "从 boot-args 中移除任何 ctrsmt 参数。",
  "Under ACPI > Delete, add an entry with TableSignature DMAR, All true, Enabled true.": "在 ACPI > Delete 下添加一项：TableSignature 设为 DMAR，All 设为 true，Enabled 设为 true。",
  "Or turn VT-d off in the BIOS (sometimes on the overclocking page).": "或者在 BIOS 中关闭 VT-d（有时位于超频页面）。",
  "Under Kernel > Quirks, set DisableIoMapper to true.": "在 Kernel > Quirks 下，将 DisableIoMapper 设为 true。",
  "Under Booter > Quirks, set DevirtualiseMmio to false.": "在 Booter > Quirks 下，将 DevirtualiseMmio 设为 false。",
  "Turn VT-d off in the BIOS; if it still stops at EXITBS:START, turn off Hyper-Threading too.": "在 BIOS 中关闭 VT-d；若仍卡在 EXITBS:START，请一并关闭超线程（Hyper-Threading）。",
  "Under Booter > Quirks, set DevirtualiseMmio to true.": "在 Booter > Quirks 下，将 DevirtualiseMmio 设为 true。",
  "Make sure VT-d is off in the BIOS.": "确保已在 BIOS 中关闭 VT-d。",
  "Under NVRAM > Delete > 7C436110-AB2A-4BBB-A880-FE41995C9F82, remove boot-args.": "在 NVRAM > Delete > 7C436110-AB2A-4BBB-A880-FE41995C9F82 下，移除 boot-args。",
  "Under Kernel > Add, set Enabled to false on USBInjectAll.kext.": "在 Kernel > Add 下，将 USBInjectAll.kext 的 Enabled 设为 false。",
  "Under Kernel > Add, set Enabled to false on IntelSnowMausi.kext.": "在 Kernel > Add 下，将 IntelSnowMausi.kext 的 Enabled 设为 false。",
  "Under Booter > Quirks, set SetupVirtualMap to false.": "在 Booter > Quirks 下，将 SetupVirtualMap 设为 false。",
  "Under Booter > Quirks, set DevirtualiseMmio and SetupVirtualMap to true.": "在 Booter > Quirks 下，将 DevirtualiseMmio 和 SetupVirtualMap 均设为 true。",
  "Under Booter > Quirks, set DisableVariableWrite to true.": "在 Booter > Quirks 下，将 DisableVariableWrite 设为 true。",
  "Under Booter > MmioWhitelist, set Enabled to false on every entry.": "在 Booter > MmioWhitelist 下，将每一项的 Enabled 设为 false。",
  "Under Booter > Quirks, set AllowRelocationBlock to true.": "在 Booter > Quirks 下，将 AllowRelocationBlock 设为 true。",
  "Under Kernel > Patch, make each Replace equal to Replace AND ReplaceMask.": "在 Kernel > Patch 下，使每项的 Replace 等于 Replace 与 ReplaceMask 按位与的结果。",
  "Under Kernel > Block, add com.apple.driver.AppleEthernetRL with Strategy Exclude, MinKernel 25.0.0, Enabled true.": "在 Kernel > Block 下添加 com.apple.driver.AppleEthernetRL（Strategy 设为 Exclude，MinKernel 设为 25.0.0，Enabled 设为 true）。",
  "Under Kernel > Add, set Enabled to true on NVMeFix.kext.": "在 Kernel > Add 下，将 NVMeFix.kext 的 Enabled 设为 true。"
};

const ZH_HTML = [
  ["<th>Processor</th>", "<th>处理器</th>"],
  ["<th>Graphics</th>", "<th>显卡</th>"],
  ["<th>Memory window (BAR1)</th>", "<th>显存映射窗口 (BAR1)</th>"],
  ["<th>PCIe link power (ASPM)</th>", "<th>PCIe 链路电源 (ASPM)</th>"],
  ["<th>Installed driver package</th>", "<th>已安装驱动包版本</th>"],
  ["<th>NullMoth driver</th>", "<th>NullMoth 驱动状态</th>"],
  ["(the driver is for macOS 15 and 26)", "（驱动仅适用于 macOS 15 和 26）"],
  ["Apple silicon - this driver is for Intel Macs and PCs", "Apple 芯片 — 此驱动仅适用于 Intel Mac 与 PC"],
  ["listed device, model tested", "已支持设备，该型号已实测"],
  ["listed by NVIDIA, model not tested yet", "NVIDIA 已列出，该型号尚未实测"],
  ["not supported (needs RTX 20 series or newer)", "不支持（需要 RTX 20 系列或更新型号）"],
  ["not needed: Mac Pro (2019) on Apple's firmware", "无需 OpenCore：使用 Apple 原厂固件的 Mac Pro (2019)"],
  ["(experimental, needs SIP off)", "（实验性，需关闭 SIP）"],
  [">none found<", ">未检测到<"],
  [">not detected<", ">未检测到<"],
  [">No version record<", ">无版本记录<"],
  ['<span class="good">running</span>', '<span class="good">运行中</span>'],
  ["loaded, no NVIDIA Metal device yet", "已加载，尚未出现 NVIDIA Metal 设备"],
  ["installed, not running yet", "已安装，尚未运行"],
  [">not installed<", ">未安装<"],
  ["NullMoth components are loaded and an NVIDIA Metal device is visible.", "NullMoth 驱动组件已加载，且已识别到 NVIDIA Metal 设备。"],
  ["Use Check for a newer driver to update the driver. To remove the driver, use Remove the driver below.", "可使用下方的“检查更新”来更新驱动；如需卸载，请点击下方的“卸载驱动”。"],
  [" To move to macOS 26 Tahoe, use <b>Prepare this Mac for Tahoe</b> below.", " 如需升级到 macOS 26 Tahoe，请使用下方的<b>为 Tahoe 准备本机</b>。"],
  ["No NVIDIA card, so the NVIDIA driver does not apply here.", "未检测到 NVIDIA 显卡，因此 NVIDIA 驱动不适用于本机。"],
  ["This Mac's ", "本机的 "],
  [" can try the experimental AMD / Intel GPU driver: see <b>AMD / Intel GPU and NPU driver (test)</b> below. Turning it on downloads that driver's own package and checks it.", " 可以尝试实验性的 AMD / Intel 显卡驱动：请见“工具”页中的 <b>AMD / Intel 显卡与 NPU 驱动（测试版）</b>。开启时会自动下载并校验该驱动专属的组件包。"],
  ["macOS sees no GPU at all on this Mac.", "macOS 在本机上未检测到任何显卡。"],
  ["OpenCore most likely switches it off (a disable-gpu property", "很可能是被 OpenCore 屏蔽了（例如设置了 disable-gpu 属性"],
  [", and -wegnoigpu in boot-args", "，且 boot-args 中含有 -wegnoigpu"],
  ["). For the processor's own Intel or AMD GPU, <b>AMD / Intel GPU and NPU driver (test)</b> below turns it back on with the test driver, and <b>Turn it off</b> switches it off again. Turning it on downloads the AMD / Intel driver's own package and checks it.", "）。若要启用处理器自带的 Intel 或 AMD 核显，可在“工具”页开启 <b>AMD / Intel 显卡与 NPU 驱动（测试版）</b>重新启用它，点击<b>关闭</b>则会再次屏蔽。开启时会自动下载并校验对应的驱动包。"],
  ["Needs the driver package: ", "需要驱动包："],
  ["Download the driver package", "下载驱动包"],
  ["Found on the 1401 stick or disk image, checksum OK.", "已在 1401 启动盘或磁盘映像中找到，校验通过。"],
  ["Found on Downloads, checksum OK.", "已在“下载”文件夹中找到，校验通过。"],
  ["Found on an earlier download, checksum OK.", "已在之前的下载记录中找到，校验通过。"],
  ["Can't install here.", "无法在此机器上安装。"],
  ["This Mac has Apple silicon. Its own graphics are already Apple's.", "这是一台 Apple 芯片的 Mac，已自带 Apple 原生图形驱动。"],
  ["No NVIDIA card was found. On a laptop the card is often switched off before macOS starts: by the BIOS graphics mode (choose Hybrid/MSHybrid or Discrete, not iGPU only) or by a dGPU-off SSDT in OpenCore's ACPI folder. Fix that, restart, and open 1401 again.", "未找到 NVIDIA 显卡。笔记本上的独显常在 macOS 启动前被关闭：例如 BIOS 显卡模式设为了仅核显（请改为混合 Hybrid/MSHybrid 或独显直连 Discrete），或 OpenCore 的 ACPI 文件夹中有屏蔽独显的 SSDT。请修正后重启并重新打开 1401。"],
  ["No supported NVIDIA card was found. The driver needs a GeForce RTX 20 series or newer.", "未找到受支持的 NVIDIA 显卡。本驱动需要 GeForce RTX 20 系列或更新型号。"],
  ["This Mac does not report OpenCore. The driver's settings live in OpenCore's config, so 1401 will not install without it.", "未检测到 OpenCore。驱动配置保存在 OpenCore 的 config.plist 中，因此无法在无 OpenCore 的环境下安装。"],
  ["The driver is installed but not running.", "驱动已安装但尚未运行。"],
  ["Restart. If macOS blocked a system extension, allow it in Privacy &amp; Security, then restart once more.", "请重启电脑。如果 macOS 拦截了系统扩展，请在“隐私与安全性”中点击允许，然后再重启一次。"],
  ["The driver is loaded, but macOS shows no NVIDIA Metal device yet.", "驱动内核扩展已加载，但 macOS 中尚未显示 NVIDIA Metal 设备。"],
  ["On a laptop whose built-in screen is wired to the Intel or AMD graphics (no MUX switch), the NVIDIA card draws only the displays plugged into its own HDMI or DisplayPort: connect one there and restart. Otherwise restart once; if it stays this way, use Send logs.", "如果笔记本内屏连接在 Intel 或 AMD 核显上（无 MUX 独显直连开关），NVIDIA 显卡默认仅驱动连接在其自身 HDMI 或 DisplayPort 接口上的外接显示器：请连接外接显示器并重启，或前往“工具”开启混合显卡笔记本模式。否则请重启一次；若仍如此，请使用“发送日志”。"],
  ["has a driver configuration available. This machine still needs boot, display and application checks. Four steps, in order.", "有可用的驱动配置。请按顺序完成下方四个步骤。"],
  ["Your <b>", "你的 <b>"],
  ["Wi-Fi: this Mac's Intel Wi-Fi runs on itlwm, which joins networks through its own app, HeliPort, not the Wi-Fi menu. Download HeliPort from github.com/OpenIntelWireless/HeliPort/releases, move it to Applications, open it, and pick your network there. To start it with the Mac, turn on Launch at Login in its menu.", "Wi-Fi 提示：本机的 Intel 无线网卡正在使用 itlwm 驱动，需要通过专用的 HeliPort 客户端（而非系统右上角 Wi-Fi 菜单）连接无线网络。请从 github.com/OpenIntelWireless/HeliPort/releases 下载 HeliPort，拖入“应用程序”并打开以连接网络。可在其菜单中勾选“登录时启动”。"],
  ["This Mac started with the NVIDIA driver switched off: -nvoff is in the boot arguments. 1401 puts it there while macOS updates, and some people add it after a black screen. If you prepared for the macOS 26 update, update macOS now from System Settings and the driver comes back by itself after it. To turn the driver back on without updating, or if it stayed off after the update, click Turn the driver on, then restart. If the screen went black with the driver on, send the logs first (Send logs to NullMoth, below). To take the driver out for good, click Remove the driver below.", "本机启动时已停用 NVIDIA 驱动（启动参数中含有 -nvoff）。1401 在准备系统更新时会添加该参数，部分用户也会在遇到黑屏后手动添加。如果你刚准备好升级 macOS 26，现在去“系统设置”更新系统即可，更新后驱动会自动恢复；若不更新系统想直接恢复驱动，请点击下方“重新启用驱动”并重启。"],
  [">Turn the driver on<", ">重新启用驱动<"],
  ["Off. Nothing is installed.", "已关闭，未安装任何组件。"],
  ["This Mac can run translated apps", "本机支持运行转译后的 ARM 应用"],
  ["No translated apps yet.", "暂无已转译的应用。"],
  ["On: it switches itself on when a game is full screen.", "已开启：当游戏全屏运行时会自动生效。"],
  ["Installed but not running: restart the Mac, or turn it off and on.", "已安装但未运行：请重启 Mac，或先关闭再重新开启。"],
  ["Joined: a report goes out after each restart.", "已加入：每次重启后会自动发送简短报告。"],
  ["Left: nothing runs any more.", "已退出：不再运行任何后台报告任务。"],
  ["<tr><th>Use</th><th>Port</th><th>Seen</th><th>Plug</th><th>Device now</th></tr>", "<tr><th>启用</th><th>端口</th><th>已识别</th><th>接口类型</th><th>当前设备</th></tr>"],
  ["USB-C (flips)", "USB-C（支持正反插）"],
  ["USB-C (one way)", "USB-C（单向）"],
  ["Inside the case", "机箱内部接口"]
];

let lang = "en";
let textNodes = null;
let lastEfiCheck = null;
function collectTextNodes() {
  if (textNodes || typeof document.createTreeWalker !== "function") return;
  textNodes = [];
  const w = document.createTreeWalker($("desk"), 4);
  let n;
  while ((n = w.nextNode())) {
    const p = n.parentNode && n.parentNode.tagName;
    if (p === "SCRIPT" || p === "STYLE" || n.parentNode === $("ttl") || n.parentNode === $("lang")) continue;
    if (ZH[n.nodeValue]) textNodes.push({ node: n, en: n.nodeValue });
  }
}
function localizeEfiOut() {
  if (lang !== "zh" || typeof document.querySelectorAll !== "function") return;
  const r = $("efichkr");
  if (r && r.innerHTML) {
    r.innerHTML = r.innerHTML
      .replace(/(\d+) things? to change in /, "$1 项配置建议修改 — 分区 ")
      .replace(/No problems found in /, "未发现问题 — 分区 ");
  }
  const out = $("efiout");
  if (!out || !out.querySelectorAll) return;
  out.querySelectorAll("summary b, li, p, .now b").forEach((el) => {
    const t = el.textContent;
    if (t === "On this Mac: ") { el.textContent = "本机当前值："; return; }
    if (ZH[t]) { el.textContent = ZH[t]; return; }
    if (t.endsWith(" Takes effect at the next restart.")) {
      const base = t.slice(0, -(" Takes effect at the next restart.".length));
      el.textContent = (ZH[base] || base) + " 下次重启时生效。";
    }
  });
}
function applyDynamicZh() {
  if (lang !== "zh") return;
  for (const id of ["mac", "verdict", "s1t", "updt", "updr", "armr", "armapps", "armmsg", "gmr", "earlyr", "testr", "ports", "go", "efichkr", "efimountr", "tccr", "gpumapr", "slr", "odr", "drr"]) {
    const el = $(id);
    if (!el) continue;
    if (id === "go") {
      if (ZH[el.textContent]) el.textContent = ZH[el.textContent];
      if (ZH[el.title]) el.title = ZH[el.title];
      continue;
    }
    if (ZH[el.textContent] && !el.innerHTML.includes("<")) { el.textContent = ZH[el.textContent]; continue; }
    let h = el.innerHTML;
    for (const [en, zh] of ZH_HTML) if (h.includes(en)) h = h.split(en).join(zh);
    if (h !== el.innerHTML) el.innerHTML = h;
  }
  localizeEfiOut();
}
function updateTitleBar() {
  const on = typeof document.querySelector === "function" ? document.querySelector(".tab.on") : null;
  if (on && on.dataset) $("ttl").textContent = "1401 — " + (lang === "zh" ? (ZH[on.dataset.title] || on.dataset.title) : on.dataset.title);
}
function setLang(next) {
  lang = next === "zh" ? "zh" : "en";
  collectTextNodes();
  $("desk").classList.toggle("zh", lang === "zh");
  $("lang").textContent = lang === "zh" ? "EN" : "中文";
  try { localStorage.setItem("lang", lang); } catch (e) { /* works for the session */ }
  if (textNodes) for (const item of textNodes) item.node.nodeValue = lang === "zh" ? (ZH[item.en] || item.en) : item.en;
  updateTitleBar();
  goState();
  if (S.mac) render(S.mac);
  if (U.ctrls.length) usbRender();
  if (lastEfiCheck) origOn({ event: "efiCheck", data: lastEfiCheck });
  if (lang === "en") {
    if ($("earlyr") && !$("earlyon").hidden) $("earlyr").textContent = "Off: this Mac gets releases once they have held up for everyone who went first.";
    if ($("earlyr") && $("earlyon").hidden) $("earlyr").textContent = "On: new drivers reach this Mac first, before they are offered to everyone.";
  }
  applyDynamicZh();
  setTimeout(applyDynamicZh, 10);
}
const origOn = NM.on;
NM.on = (m) => {
  if (m && m.event === "efiCheck") lastEfiCheck = m.data;
  origOn(m);
  applyDynamicZh();
  setTimeout(applyDynamicZh, 10);
};
window.NM = NM;
document.querySelectorAll(".tab").forEach((b) => {
  const prev = b.onclick;
  b.onclick = () => { if (prev) prev(); updateTitleBar(); };
});
for (const id of ["updchk", "upddrv", "gmon", "gmoff", "armcancel", "efichk", "tccg", "gpumap", "efimount", "uw", "sl", "fl"]) {
  const b = $(id);
  if (b && b.onclick) {
    const prev = b.onclick;
    b.onclick = (e) => { prev(e); applyDynamicZh(); };
  }
}
(() => {
  let saved = null;
  try { saved = localStorage.getItem("lang"); } catch (e) { /* no stored choice */ }
  const sysZh = typeof navigator !== "undefined" && /^zh/i.test(navigator.language || "");
  if ((saved ? saved === "zh" : sysZh) && typeof document.createTreeWalker === "function") setLang("zh");
})();
$("lang").onclick = () => setLang(lang === "zh" ? "en" : "zh");
