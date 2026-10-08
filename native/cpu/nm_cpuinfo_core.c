/* Portable logic for nm_cpuinfo (see nm_cpuinfo.h). No platform calls here: everything goes through nm_backend. */
#include "nm_cpuinfo.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

int nm_args_ok(int argc) { return argc == 1; }

int nm_leaf_allowed(uint32_t leaf) {
    switch (leaf) {
    case 0x0: case 0x1: case 0x7: case 0xB: case 0x1A: case 0x1F:
    case 0x80000000u: case 0x80000001u: case 0x80000008u: case 0x8000001Eu:
        return 1;
    default:
        return 0;                       /* leaf 3 (processor serial number) and every other leaf */
    }
}

static int safe_cpuid(const nm_backend *b, uint32_t leaf, uint32_t sub, nm_regs *r) {
    memset(r, 0, sizeof *r);
    if (!nm_leaf_allowed(leaf)) return -1;
    b->cpuid(b->ctx, leaf, sub, r);
    return 0;
}

/* JSON writer: a hard cap, with room kept for the closing text so a cut document still parses. */
#define NM_TAIL_RESERVE 96
static void put(nm_out *o, const char *fmt, ...) {
    char tmp[512];
    va_list ap;
    int n;
    if (o->truncated) return;
    va_start(ap, fmt);
    n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sizeof tmp || o->len + (size_t)n + NM_TAIL_RESERVE >= o->cap) { o->truncated = 1; return; }
    memcpy(o->buf + o->len, tmp, (size_t)n);
    o->len += (size_t)n;
    o->buf[o->len] = 0;
}
static void put_tail(nm_out *o, const char *s) {        /* closing text uses the reserve */
    size_t n = strlen(s);
    if (o->len + n + 1 > o->cap) return;
    memcpy(o->buf + o->len, s, n);
    o->len += n;
    o->buf[o->len] = 0;
}

static void vendor_of(const nm_regs *r0, char v[13]) {
    memcpy(v, &r0->b, 4); memcpy(v + 4, &r0->d, 4); memcpy(v + 8, &r0->c, 4); v[12] = 0;
    static const char *known[] = {"GenuineIntel", "AuthenticAMD", "HygonGenuine", "CentaurHauls", "  Shanghai  ", "VIA VIA VIA "};
    int recognized = 0;
    for (unsigned i = 0; i < sizeof known / sizeof known[0]; i++) if (!memcmp(v, known[i], 12)) recognized = 1;
    if (!recognized) { memset(v, 0, 13); memcpy(v, "unknown", sizeof "unknown" - 1); }
}

typedef struct { int use1f, use0b, has1a, has1e; } nm_caps;

static void topo_walk(const nm_backend *b, nm_out *o, uint32_t leaf) {
    put(o, "\"leaf\":\"0x%X\",\"domains\":[", leaf);
    uint32_t s;
    for (s = 0; s < NM_MAX_TOPO_SUBLEAF; s++) {
        nm_regs r;
        safe_cpuid(b, leaf, s, &r);
        uint32_t type = (r.c >> 8) & 0xFF;
        if (type == 0 || (r.b & 0xffff) == 0) break;                                    /* invalid domain ends the list */
        put(o, "%s{\"subleaf\":%u,\"type\":%u,\"shift\":%u,\"logical\":%u}", s ? "," : "", s, type, r.a & 0x1F, r.b & 0xFFFF);
    }
    put(o, s == NM_MAX_TOPO_SUBLEAF ? "],\"partial\":true,\"error\":\"topology subleaf cap reached\"" : "]");
}

static void per_lp(const nm_backend *b, nm_out *o) {
    nm_regs r0, r1, r, e0, e1;
    char vendor[13];
    nm_caps caps = {0, 0, 0, 0};
    safe_cpuid(b, 0, 0, &r0);
    vendor_of(&r0, vendor);
    put(o, "\"vendor\":\"%s\",\"max_basic_leaf\":\"0x%X\"", vendor, r0.a);
    if (r0.a >= 1) {
        safe_cpuid(b, 1, 0, &r1);
        put(o, ",\"initial_apic_id\":%u,\"signature\":\"0x%08X\",\"leaf1_ecx\":\"0x%08X\",\"leaf1_edx\":\"0x%08X\"", r1.b >> 24, r1.a, r1.c, r1.d);
    } else put(o, ",\"leaf1\":{\"status\":\"unavailable\",\"error\":\"max basic leaf below 1\"}");
    if (r0.a >= 0x1F) { safe_cpuid(b, 0x1F, 0, &r); caps.use1f = (r.b & 0xffff) != 0; }
    if (!caps.use1f && r0.a >= 0xB) { safe_cpuid(b, 0xB, 0, &r); caps.use0b = (r.b & 0xffff) != 0; }
    if (!strcmp(vendor, "GenuineIntel") && r0.a >= 0x1A) {
        safe_cpuid(b, 0x1A, 0, &r); caps.has1a = r.a != 0;
    }
    if (caps.use1f || caps.use0b) {
        safe_cpuid(b, caps.use1f ? 0x1F : 0xB, 0, &r);
        put(o, ",\"x2apic_id\":%u,\"topology\":{", r.d);
        topo_walk(b, o, caps.use1f ? 0x1F : 0xB); put(o, "}");
    } else put(o, ",\"topology\":{\"status\":\"unavailable\",\"error\":\"topology leaves absent on this processor\"}");
    if (caps.has1a) {
        safe_cpuid(b, 0x1A, 0, &r);
        uint32_t t = r.a >> 24;
        put(o, ",\"core_type\":{\"raw\":\"0x%02X\",\"name\":\"%s\",\"native_model_id\":\"0x%06X\"}", t,
            t == 0x20 ? "Intel Atom" : t == 0x40 ? "Intel Core" : "reserved or unknown", r.a & 0xFFFFFF);
    } else put(o, ",\"core_type\":{\"status\":\"unavailable\",\"error\":\"Intel leaf 1AH absent or zero on this processor\"}");
    safe_cpuid(b, 0x80000000u, 0, &e0);
    uint32_t maxe = e0.a >= 0x80000000u ? e0.a : 0;
    put(o, ",\"max_extended_leaf\":\"0x%X\"", maxe);
    if (maxe >= 0x80000001u) {
        safe_cpuid(b, 0x80000001u, 0, &e1);
        caps.has1e = (!strcmp(vendor, "AuthenticAMD") || !strcmp(vendor, "HygonGenuine")) && maxe >= 0x8000001Eu && ((e1.c >> 22) & 1);
    }
    if (caps.has1e) {
        safe_cpuid(b, 0x8000001Eu, 0, &r);
        put(o, ",\"amd_leaf8000001e_raw\":{\"eax\":\"0x%08X\",\"ebx\":\"0x%08X\",\"ecx\":\"0x%08X\",\"edx\":\"0x%08X\"}", r.a, r.b, r.c, r.d);
    }
}

int nm_collect(const nm_backend *b, nm_out *o, uint32_t budget_ms) {
    nm_regs r0, r1, r, e0;
    nm_caps caps = {0, 0, 0, 0};
    char vendor[13];
    uint64_t start = b->now_ms(b->ctx);

    if (o->cap < 8192) return -1;          /* the fixed header needs room; the helper always passes NM_OUT_CAP */
    o->len = 0; o->truncated = 0; o->buf[0] = 0;
    put(o, "{\"sample_scope\":\"header is an unpinned helper-thread sample; per-processor records query their own capabilities\",\"schema\":\"nm-cpuinfo/1\",\"operation\":\"fixed read-only CPUID allow-list\",");

    safe_cpuid(b, 0x0, 0, &r0);
    vendor_of(&r0, vendor);
    uint32_t maxb = r0.a;
    put(o, "\"basic\":{\"max_leaf\":\"0x%X\",\"vendor\":\"%s\"},", maxb, vendor);

    /* leaf 1 */
    uint32_t xsave = 0, osxsave = 0, avx = 0;
    if (maxb >= 1) {
        safe_cpuid(b, 0x1, 0, &r1);
        uint32_t fam = (r1.a >> 8) & 0xF, model = (r1.a >> 4) & 0xF, step = r1.a & 0xF;
        uint32_t xfam = (r1.a >> 20) & 0xFF, xmodel = (r1.a >> 16) & 0xF;
        uint32_t dfam = fam == 0xF ? fam + xfam : fam;
        uint32_t dmodel = (fam == 0x6 || fam == 0xF) ? model + (xmodel << 4) : model;
        xsave = (r1.c >> 26) & 1; osxsave = (r1.c >> 27) & 1; avx = (r1.c >> 28) & 1;
        put(o, "\"leaf1\":{\"signature\":\"0x%08X\",\"family\":%u,\"model\":%u,\"stepping\":%u,\"ecx\":\"0x%08X\",\"edx\":\"0x%08X\","
               "\"hypervisor_bit\":%u,\"hypervisor_meaning\":\"CPUID reports a hypervisor present; an observation, not proof the hardware is virtual\"},",
            r1.a, dfam, dmodel, step, r1.c, r1.d, (r1.c >> 31) & 1);
    } else {
        put(o, "\"leaf1\":{\"status\":\"unavailable\",\"error\":\"max basic leaf below 1\"},");
    }

    /* leaf 7 */
    uint32_t avx512f = 0;
    if (maxb >= 7) {
        safe_cpuid(b, 0x7, 0, &r);
        uint32_t maxsub = r.a;
        avx512f = (r.b >> 16) & 1;
        put(o, "\"leaf7\":{\"max_subleaf\":%u,\"subleaves\":[", maxsub);
        for (uint32_t s = 0; s <= maxsub && s <= NM_MAX_LEAF7_SUBLEAF; s++) {
            safe_cpuid(b, 0x7, s, &r);
            put(o, "%s{\"subleaf\":%u,\"eax\":\"0x%08X\",\"ebx\":\"0x%08X\",\"ecx\":\"0x%08X\",\"edx\":\"0x%08X\"}", s ? "," : "", s, r.a, r.b, r.c, r.d);
        }
        put(o, "]%s},", maxsub > NM_MAX_LEAF7_SUBLEAF ? ",\"note\":\"subleaves above 2 not read\"" : "");
    } else {
        put(o, "\"leaf7\":{\"status\":\"unavailable\",\"error\":\"max basic leaf below 7\"},");
    }

    /* XGETBV: only when the CPU has XSAVE and the OS set OSXSAVE */
    if (xsave && osxsave) {
        uint64_t xcr0 = 0;
        if (b->xgetbv(b->ctx, 0, &xcr0) == 0) {
            put(o, "\"xcr0\":{\"value\":\"0x%llX\",\"os_enabled_avx\":%s,\"os_enabled_avx512\":%s,\"cpu_reports_avx\":%u,\"cpu_reports_avx512f\":%u},",
                (unsigned long long)xcr0, (avx && (xcr0 & 0x6) == 0x6) ? "true" : "false",
                (avx512f && (xcr0 & 0xE6) == 0xE6) ? "true" : "false", avx, avx512f);
        } else {
            put(o, "\"xcr0\":{\"status\":\"unavailable\",\"error\":\"XGETBV failed\"},");
        }
    } else {
        put(o, "\"xcr0\":{\"status\":\"unavailable\",\"error\":\"not executed: %s\"},", !xsave ? "CPU reports no XSAVE" : "OSXSAVE clear");
    }

    /* topology leaves: 1FH preferred, then 0BH; each exists only if subleaf 0 EBX != 0 */
    if (maxb >= 0x1F) { safe_cpuid(b, 0x1F, 0, &r); caps.use1f = r.b != 0; }
    if (!caps.use1f && maxb >= 0xB) { safe_cpuid(b, 0xB, 0, &r); caps.use0b = r.b != 0; }
    if (maxb >= 0x1A) { safe_cpuid(b, 0x1A, 0, &r); caps.has1a = r.a != 0; }
    put(o, "\"topology\":{");
    if (caps.use1f || caps.use0b) topo_walk(b, o, caps.use1f ? 0x1F : 0xB);
    else put(o, "\"status\":\"unavailable\",\"error\":\"neither leaf 1FH nor 0BH present\"");
    put(o, "},");

    /* extended leaves */
    safe_cpuid(b, 0x80000000u, 0, &e0);
    uint32_t maxe = e0.a >= 0x80000000u ? e0.a : 0;
    put(o, "\"extended\":{\"max_leaf\":\"0x%X\"", maxe);
    if (maxe >= 0x80000001u) {
        safe_cpuid(b, 0x80000001u, 0, &r);
        put(o, ",\"e1_ecx\":\"0x%08X\",\"e1_edx\":\"0x%08X\"", r.c, r.d);
        int amd = !strcmp(vendor, "AuthenticAMD") || !strcmp(vendor, "HygonGenuine");
        caps.has1e = amd && maxe >= 0x8000001Eu && ((r.c >> 22) & 1);
    }
    if (maxe >= 0x80000008u) {
        safe_cpuid(b, 0x80000008u, 0, &r);
        put(o, ",\"e8_eax\":\"0x%08X\",\"e8_ecx\":\"0x%08X\"", r.a, r.c);
    }
    put(o, ",\"amd_8000001E\":\"%s\"},", caps.has1e ? "read per logical processor" : "not read (not AMD/Hygon, absent, or TopologyExtensions clear)");

    /* per logical processor, on this (owned helper) thread */
    nm_affinity prior;
    nm_group groups[NM_MAX_GROUPS];
    put(o, "\"per_logical_processor\":{");
    int ng = b->groups(b->ctx, groups, NM_MAX_GROUPS);
    int group_capped = ng > NM_MAX_GROUPS;
    if (group_capped) ng = NM_MAX_GROUPS;
    if (ng < 0) {
        put(o, "\"status\":\"unavailable\",\"error\":\"processor groups not readable\"}");
    } else if (b->get_affinity(b->ctx, &prior) != 0) {
        put(o, "\"status\":\"unavailable\",\"error\":\"current affinity not readable; no processor was visited\"}");
    } else {
        int visited = 0, failed = 0, location_failed = 0, stopped = 0;
        const char *why = group_capped ? "processor-group cap reached" : "complete";
        put(o, "\"groups\":[");
        for (int g = 0; g < ng; g++)
            put(o, "%s{\"group\":%u,\"active\":%u,\"mask\":\"0x%llX\"}", g ? "," : "", groups[g].group, groups[g].active,
                (unsigned long long)groups[g].mask);
        put(o, "],\"processors\":[");
        for (int g = 0; g < ng && !stopped; g++) {
            for (int bit = 0; bit < 64 && !stopped; bit++) {
                if (!((groups[g].mask >> bit) & 1)) continue;
                if (visited + failed + location_failed >= NM_MAX_LP) { stopped = 1; why = "logical-processor cap reached"; break; }
                if (b->now_ms(b->ctx) - start >= budget_ms) { stopped = 1; why = "time cap reached"; break; }
                nm_affinity a = { groups[g].group, 1ull << bit };
                char rb[4096];                     /* one record is built whole, then appended whole or not at all */
                nm_out rec = { rb, sizeof rb, 0, 0 };
                put(&rec, "%s{\"group\":%u,\"bit\":%d,", (visited + failed + location_failed) ? "," : "", groups[g].group, bit);
                int ok = b->set_affinity(b->ctx, &a) == 0;
                int pinned = ok;
                nm_affinity location;
                int located = ok && b->current_processor && b->current_processor(b->ctx, &location) == 0 && location.group == a.group && location.mask == a.mask;
                if (ok && !located) {
                    put(&rec, "\"status\":\"location unavailable\"}");
                    ok = 0;
                } else if (ok) { put(&rec, "\"status\":\"measured\","); per_lp(b, &rec); put(&rec, "}"); }
                else put(&rec, "\"status\":\"affinity refused\"}");
                if (rec.truncated || o->len + rec.len + NM_TAIL_RESERVE + 160 >= o->cap) {
                    o->truncated = 1; stopped = 1; why = "output cap reached"; break;
                }
                memcpy(o->buf + o->len, rb, rec.len); o->len += rec.len; o->buf[o->len] = 0;
                if (ok) visited++; else if (pinned) location_failed++; else failed++;
            }
        }
        int restored = b->set_affinity(b->ctx, &prior) == 0;
        nm_affinity after;
        int verified = restored && b->get_affinity(b->ctx, &after) == 0 && after.group == prior.group && after.mask == prior.mask;
        put_tail(o, "],");
        char tail[256];
        snprintf(tail, sizeof tail, "\"visited\":%d,\"affinity_refused\":%d,\"location_unavailable\":%d,\"stopped\":\"%s\",\"affinity_restored\":%s}",
                 visited, failed, location_failed, why, verified ? "true" : "false");
        put_tail(o, tail);
    }
    put_tail(o, o->truncated ? ",\"truncated\":true}" : ",\"truncated\":false}");
    return 0;
}
