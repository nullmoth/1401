"""Arms for nm_cpuinfo: python3 -I test_cpuinfo.py <fixtures binary>. Each scenario is the real core on a fake CPU."""
import json, subprocess, sys

out = subprocess.run([sys.argv[1]], capture_output=True, text=True, timeout=60).stdout
rows = {}
for line in out.splitlines():
    parts = line.split("\t")
    rows[parts[0]] = parts[1:]
res = []


def arm(name, ok, detail=""):
    res.append(bool(ok))
    print(("  ok   " if ok else "  FAIL ") + name + (f"   [{detail}]" if detail else ""))


def load(name):
    j, meta = rows[name]
    return json.loads(j), json.loads(meta)


for name in ("intel_hybrid", "amd_zen", "old_cpu", "osxsave_clear", "pin_refused", "restore_refused", "time_cap", "two_groups", "lp_cap", "output_cap"):
    try:
        j, m = load(name)
        arm(f"{name}: output is valid JSON and leaf 3 was never executed", m["leaf3_calls"] == 0, f"leaf3={m['leaf3_calls']}")
    except Exception as e:  # noqa: BLE001
        arm(f"{name}: output is valid JSON", False, repr(e)[:120])

j, m = load("intel_hybrid")
cores = [p.get("core_type", {}).get("name") for p in j["per_logical_processor"]["processors"]]
arm("hybrid: core type is measured on every logical processor (8 Core, 8 Atom), not inferred from one sample",
    cores.count("Intel Core") == 8 and cores.count("Intel Atom") == 8, str(cores.count("Intel Core")) + "/" + str(cores.count("Intel Atom")))
arm("hybrid: leaf 1FH domains SMT then Core", [d["type"] for d in j["topology"]["domains"]] == [1, 2] and j["topology"]["leaf"] == "0x1F")
arm("hybrid: XCR0 read; AVX OS-enabled, AVX-512 reported by the CPU but NOT OS-enabled",
    j["xcr0"]["os_enabled_avx"] is True and j["xcr0"]["os_enabled_avx512"] is False and j["xcr0"]["cpu_reports_avx512f"] == 1)
arm("hybrid: affinity restored to exactly the prior value", j["per_logical_processor"]["affinity_restored"] is True and m["final_mask"] == m["prior_mask"])
arm("hybrid: no serial value anywhere", "12345678" not in rows["intel_hybrid"][0] and "9ABCDEF0" not in rows["intel_hybrid"][0])

j, m = load("amd_zen")
p0 = j["per_logical_processor"]["processors"][0]
arm("AMD: 0BH used when 1FH is absent; 8000001E read per processor because TopologyExtensions is set",
    j["topology"]["leaf"] == "0xB" and "amd_leaf8000001e_raw" in p0 and p0["core_type"]["status"] == "unavailable")
arm("AMD: hypervisor bit reported as an observation", j["leaf1"]["hypervisor_bit"] == 1 and "not proof" in j["leaf1"]["hypervisor_meaning"])
arm("AMD: XCR0 0xE7 with no AVX-512F in the CPU -> AVX-512 not OS-enabled", j["xcr0"]["os_enabled_avx512"] is False)

j, m = load("old_cpu")
arm("old CPU: leaf 7 and topology unavailable with reasons; XGETBV not executed (no XSAVE)",
    j["leaf7"]["status"] == "unavailable" and j["topology"]["status"] == "unavailable" and "no XSAVE" in j["xcr0"].get("error", "") and m["xgetbv_calls"] == 0)

j, m = load("osxsave_clear")
arm("XSAVE without OSXSAVE: XGETBV never executed", m["xgetbv_calls"] == 0 and "OSXSAVE clear" in j["xcr0"].get("error", ""))

j, m = load("pin_refused")
st = [p["status"] for p in j["per_logical_processor"]["processors"]]
arm("refused affinity on one processor: recorded there, others still measured, prior affinity restored",
    st.count("affinity refused") == 1 and st.count("measured") == 15 and j["per_logical_processor"]["affinity_restored"] is True
    and m["final_mask"] == m["prior_mask"])

j, m = load("restore_refused")
arm("a failed restore is reported as affinity_restored=false (never claimed)", j["per_logical_processor"]["affinity_restored"] is False)

j, m = load("time_cap")
pl = j["per_logical_processor"]
arm("time cap: stops early, says so, still restores", pl["stopped"] == "time cap reached" and pl["visited"] < 16 and pl["affinity_restored"] is True,
    f"visited {pl['visited']}")

j, m = load("two_groups")
groups = {p["group"] for p in j["per_logical_processor"]["processors"]}
arm("two processor groups (64 + 8) are both visited with their real group numbers", groups == {0, 1} and j["per_logical_processor"]["visited"] == 72)

j, m = load("lp_cap")
arm("576 active processors: stops at the 512 cap and says so", j["per_logical_processor"]["stopped"] == "logical-processor cap reached"
    and j["per_logical_processor"]["visited"] == 512)

j, m = load("output_cap")
arm("output cap: JSON still parses, marked truncated, affinity restored", j["truncated"] is True and j["per_logical_processor"]["affinity_restored"] is True
    and j["per_logical_processor"]["stopped"] == "output cap reached")
arm("a buffer below 8 KiB is refused", rows["tiny_cap_rc"][0] == "-1")
al = json.loads(rows["allow"][0])
arm("allow-list: leaf 3 refused (and 2, 4); 1, 1FH, 8000001E allowed", al == {"leaf3": 0, "leaf2": 0, "leaf4": 0, "leaf1": 1, "leaf1F": 1, "e1E": 1}, str(al))
ar = json.loads(rows["args"][0])
arm("no arguments accepted", ar == {"none": 1, "one": 0})
for name in ['mixed_vendors','leaf1_absent_on_some','location_mismatch','unknown_vendor']:
    j, m = load(name)
    arm(name+': no unavailable leaf or serial query', m['invalid_leaf_calls'] == 0 and m['leaf3_calls'] == 0)
    arm(name+': restores prior affinity', j['per_logical_processor']['affinity_restored'] is True and m['final_mask'] == m['prior_mask'])
j, m = load('mixed_vendors')
processors = j['per_logical_processor']['processors']
arm('per processor vendor and AMD TopologyExtensions are read on that processor', processors[8]['vendor'] == 'AuthenticAMD' and 'amd_leaf8000001e_raw' in processors[8] and 'amd_leaf8000001e_raw' not in processors[9])
j, m = load('leaf1_absent_on_some')
arm('max leaf zero processors never query leaf1', all(p['leaf1']['status'] == 'unavailable' for p in j['per_logical_processor']['processors'][8:]))
j, m = load('location_mismatch')
arm('actual location mismatch is partial without wrongly attributed CPUID', j['per_logical_processor']['location_unavailable'] == 1 and j['per_logical_processor']['affinity_refused'] == 0 and j['per_logical_processor']['processors'][5]['status'] == 'location unavailable' and 'signature' not in j['per_logical_processor']['processors'][5])
j, m = load('unknown_vendor')
arm('unknown vendor bytes are a fixed marker, not JSON/identity content', j['basic']['vendor'] == 'unknown' and all(p['vendor'] == 'unknown' for p in j['per_logical_processor']['processors']))
print(f"nm_cpuinfo fixtures: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
