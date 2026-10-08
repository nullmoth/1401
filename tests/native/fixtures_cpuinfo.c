/* Fixture runner: the real nm_cpuinfo_core.c against fake CPUs. Prints one line per scenario:
 *   <name>\t<json>\t{"leaf3_calls":N,"xgetbv_calls":N,"final_group":G,"final_mask":"0x..","prior_mask":"0x..","rc":R}
 * tests/test_cpuinfo.py parses and asserts. Builds anywhere: cc -std=c11 -Wall -Wextra -Werror. */
#include <stdio.h>
#include <string.h>
#include "../../native/cpu/nm_cpuinfo.h"

typedef struct {
    const char *vendor;
    uint32_t maxb, maxe, sig, ecx1, ebx7, e1ecx;
    int ncpu_core, ncpu_atom;       /* lps 0..core-1 type 40H, then atom 20H; 0 + 0 = no leaf 1AH */
    int has1f, has0b;
    uint64_t xcr0;
    int ngroups; nm_group groups[12];
    nm_affinity cur, prior;
    int fail_pin_lp, fail_restore;
    uint64_t clock, clock_step;
    int leaf3_calls, xgetbv_calls;
} fake;

static int hetero = 0, wrong_location = 0, invalid_leaf_calls = 0;

static int lp_index(const fake *f) {
    int idx = 0;
    for (int g = 0; g < f->ngroups; g++)
        for (int b = 0; b < 64; b++)
            if ((f->groups[g].mask >> b) & 1) {
                if (f->groups[g].group == f->cur.group && f->cur.mask == (1ull << b)) return idx;
                idx++;
            }
    return 0;
}

static void f_cpuid(void *ctx, uint32_t leaf, uint32_t sub, nm_regs *r) {
    fake *f = ctx;
    int lp = lp_index(f);
    memset(r, 0, sizeof *r);
    uint32_t maxb = hetero == 2 && lp >= 8 ? 0 : f->maxb;
    const char *vendor = hetero == 1 && lp >= 8 ? "AuthenticAMD" : f->vendor;
    if ((leaf < 0x80000000u && leaf > maxb) || (leaf > 0x80000000u && leaf > f->maxe) || (leaf == 0x8000001Eu && !(hetero == 1 && lp >= 8 ? (lp & 1) == 0 : f->e1ecx & (1u << 22)))) invalid_leaf_calls++;
    switch (leaf) {
    case 0: r->a = maxb; memcpy(&r->b, vendor, 4); memcpy(&r->d, vendor + 4, 4); memcpy(&r->c, vendor + 8, 4); break;
    case 1: r->a = f->sig; r->b = (uint32_t)lp << 24 | 16u << 16; r->c = f->ecx1; r->d = 0x178BFBFF; break;
    case 3: f->leaf3_calls++; r->c = 0x12345678; r->d = 0x9ABCDEF0; break;   /* a serial a correct helper never asks for */
    case 7: if (sub == 0) { r->a = 1; r->b = f->ebx7; } else { r->a = 0; r->b = 0x11; } break;
    case 0xB: case 0x1F:
        if ((leaf == 0x1F && !f->has1f) || (leaf == 0xB && !f->has0b)) break;
        if (sub == 0) { r->a = 1; r->b = 2; r->c = 1u << 8; r->d = (uint32_t)lp; }
        else if (sub == 1) { r->a = 6; r->b = (uint32_t)(f->ncpu_core + f->ncpu_atom ? f->ncpu_core + f->ncpu_atom : 16); r->c = 2u << 8 | 1; r->d = (uint32_t)lp; }
        else { r->c = sub; r->d = (uint32_t)lp; }                           /* domain type 0 ends the walk */
        break;
    case 0x1A:
        if (f->ncpu_core + f->ncpu_atom) r->a = (lp < f->ncpu_core ? 0x40u : 0x20u) << 24 | 0x000001;
        break;
    case 0x80000000u: r->a = f->maxe; break;
    case 0x80000001u: r->c = hetero == 1 && lp >= 8 ? ((lp & 1) ? 0 : 1u << 22) : f->e1ecx; break;
    case 0x80000008u: r->a = 0x3030; r->c = 0x400F; break;
    case 0x8000001Eu: r->a = (uint32_t)lp; r->b = (uint32_t)(lp / 2) | 1u << 8; r->c = 0; break;
    default: break;
    }
}
static int f_xgetbv(void *ctx, uint32_t i, uint64_t *o) { fake *f = ctx; (void)i; f->xgetbv_calls++; *o = f->xcr0; return 0; }
static int f_groups(void *ctx, nm_group *o, int max) {
    fake *f = ctx; int n = f->ngroups < max ? f->ngroups : max;
    memcpy(o, f->groups, sizeof(nm_group) * (size_t)n); return n;
}
static int f_get(void *ctx, nm_affinity *o) { *o = ((fake *)ctx)->cur; return 0; }
static int f_set(void *ctx, const nm_affinity *a) {
    fake *f = ctx;
    f->clock += f->clock_step;
    if (a->group == f->prior.group && a->mask == f->prior.mask) { if (f->fail_restore) return -1; f->cur = *a; return 0; }
    nm_affinity save = f->cur;
    f->cur = *a;
    if (lp_index(f) == f->fail_pin_lp) { f->cur = save; return -1; }
    return 0;
}
static int f_where(void *ctx, nm_affinity *out) { *out = ((fake *)ctx)->cur; if (wrong_location && lp_index(ctx) == 5) out->mask = 1; return 0; }
static uint64_t f_now(void *ctx) { return ((fake *)ctx)->clock; }

static char buf[NM_OUT_CAP];
static void run(const char *name, fake *f, size_t cap) {
    nm_backend b = { f, f_cpuid, f_xgetbv, f_groups, f_get, f_set, f_now, f_where };
    nm_out o = { buf, cap, 0, 0 };
    f->cur = f->prior; invalid_leaf_calls = 0;
    int rc = nm_collect(&b, &o, NM_DEFAULT_BUDGET_MS);
    printf("%s\t%s\t{\"leaf3_calls\":%d,\"xgetbv_calls\":%d,\"final_group\":%u,\"final_mask\":\"0x%llX\",\"prior_mask\":\"0x%llX\",\"rc\":%d,\"invalid_leaf_calls\":%d}\n",
           name, rc == 0 ? o.buf : "null", f->leaf3_calls, f->xgetbv_calls, f->cur.group, (unsigned long long)f->cur.mask,
           (unsigned long long)f->prior.mask, rc, invalid_leaf_calls);
}

#define ECX_XSAVE (1u << 26)
#define ECX_OSXSAVE (1u << 27)
#define ECX_AVX (1u << 28)
#define ECX_HV (1u << 31)

int main(void) {
    fake intel = { "GenuineIntel", 0x20, 0x80000008u, 0x000B0671, ECX_XSAVE | ECX_OSXSAVE | ECX_AVX, 1u << 16, 0,
                   8, 8, 1, 1, 0x7, 1, {{0, 16, 0xFFFF}}, {0, 0}, {0, 0x3}, -1, 0, 0, 1, 0, 0 };
    run("intel_hybrid", &intel, NM_OUT_CAP);
    fake amd = { "AuthenticAMD", 0x10, 0x80000021u, 0x00A20F12, ECX_XSAVE | ECX_OSXSAVE | ECX_AVX | ECX_HV, 0, 1u << 22,
                 0, 0, 0, 1, 0xE7, 1, {{0, 16, 0xFFFF}}, {0, 0}, {0, 0xFFFF}, -1, 0, 0, 1, 0, 0 };
    run("amd_zen", &amd, NM_OUT_CAP);
    fake old = { "GenuineIntel", 5, 0x80000008u, 0x00000F29, 0, 0, 0, 0, 0, 0, 0, 0, 1, {{0, 2, 0x3}}, {0, 0}, {0, 0x3}, -1, 0, 0, 1, 0, 0 };
    run("old_cpu", &old, NM_OUT_CAP);
    fake noos = intel; noos.ecx1 = ECX_XSAVE | ECX_AVX; noos.leaf3_calls = noos.xgetbv_calls = 0;
    run("osxsave_clear", &noos, NM_OUT_CAP);
    fake pin = intel; pin.fail_pin_lp = 5; pin.leaf3_calls = pin.xgetbv_calls = 0;
    run("pin_refused", &pin, NM_OUT_CAP);
    fake norest = intel; norest.fail_restore = 1; norest.leaf3_calls = norest.xgetbv_calls = 0;
    run("restore_refused", &norest, NM_OUT_CAP);
    fake slow = intel; slow.clock_step = 400; slow.clock = 0; slow.leaf3_calls = slow.xgetbv_calls = 0;
    run("time_cap", &slow, NM_OUT_CAP);
    fake twog = intel; twog.ngroups = 2; twog.groups[0] = (nm_group){0, 64, ~0ull}; twog.groups[1] = (nm_group){1, 8, 0xFF};
    twog.ncpu_core = 0; twog.ncpu_atom = 0; twog.leaf3_calls = twog.xgetbv_calls = 0;
    run("two_groups", &twog, NM_OUT_CAP);
    fake many = twog; many.ngroups = 9;
    for (int g = 0; g < 9; g++) many.groups[g] = (nm_group){(uint16_t)g, 64, ~0ull};
    run("lp_cap", &many, NM_OUT_CAP);
    fake small = twog;
    run("output_cap", &small, 9000);
    fake mixed = intel; mixed.maxe = 0x8000001Eu; mixed.leaf3_calls = mixed.xgetbv_calls = 0;
    hetero = 1; run("mixed_vendors", &mixed, NM_OUT_CAP); hetero = 0;
    fake absent = intel; absent.leaf3_calls = absent.xgetbv_calls = 0;
    hetero = 2; run("leaf1_absent_on_some", &absent, NM_OUT_CAP); hetero = 0;
    fake mismatch = intel; mismatch.leaf3_calls = mismatch.xgetbv_calls = 0;
    wrong_location = 1; run("location_mismatch", &mismatch, NM_OUT_CAP); wrong_location = 0;
    fake strange = intel; strange.vendor = "bad\"\\vendor!!"; strange.leaf3_calls = strange.xgetbv_calls = 0;
    run("unknown_vendor", &strange, NM_OUT_CAP);
    nm_out tiny = { buf, 4096, 0, 0 };
    nm_backend b = { &small, f_cpuid, f_xgetbv, f_groups, f_get, f_set, f_now, f_where };
    printf("tiny_cap_rc\t%d\n", nm_collect(&b, &tiny, NM_DEFAULT_BUDGET_MS));
    printf("allow\t{\"leaf3\":%d,\"leaf2\":%d,\"leaf4\":%d,\"leaf1\":%d,\"leaf1F\":%d,\"e1E\":%d}\n", nm_leaf_allowed(3), nm_leaf_allowed(2),
           nm_leaf_allowed(4), nm_leaf_allowed(1), nm_leaf_allowed(0x1F), nm_leaf_allowed(0x8000001Eu));
    printf("args\t{\"none\":%d,\"one\":%d}\n", nm_args_ok(1), nm_args_ok(2));
    return 0;
}
