/* Windows x64 backend and entry point for nm_cpuinfo. Build (CI, MSVC, static CRT):
 *     cl /nologo /O2 /MT /W4 /WX /DWIN32_LEAN_AND_MEAN /D_WIN32_WINNT=0x0602 nm_cpuinfo_core.c nm_cpuinfo_win.c
 *        /Fe:nm_cpuinfo.exe /link /SUBSYSTEM:CONSOLE kernel32.lib
 * Only documented kernel32 calls and the compiler's __cpuidex / _xgetbv. The collection runs on one helper thread the
 * process owns; its affinity is changed one logical processor at a time and its previous affinity is restored. The
 * process affinity, priority and every system setting are left alone. The main thread waits a bounded time and writes
 * whatever the helper had completed. */
#include <windows.h>
#include <intrin.h>
#include <immintrin.h>
#include <stdlib.h>
#include <string.h>
#include "nm_cpuinfo.h"

typedef struct { HANDLE thread; } win_ctx;

static void w_cpuid(void *ctx, uint32_t leaf, uint32_t sub, nm_regs *r) {
    int v[4];
    (void)ctx;
    __cpuidex(v, (int)leaf, (int)sub);
    r->a = (uint32_t)v[0]; r->b = (uint32_t)v[1]; r->c = (uint32_t)v[2]; r->d = (uint32_t)v[3];
}

static int w_xgetbv(void *ctx, uint32_t index, uint64_t *out) {   /* the core calls this only after XSAVE+OSXSAVE */
    (void)ctx;
    *out = _xgetbv(index);
    return 0;
}

static int parse_group_buffer(const BYTE *buf, DWORD used, nm_group *out, int max) {
DWORD off = 0; int seen = 0;
int result;
    result = 0;
    while (off < used) {
        if (used - off < 2 * sizeof(DWORD)) { result = -1; break; }
        const SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *e = (const SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *)(buf + off);
        if (e->Size < 2 * sizeof(DWORD) || e->Size > used - off) { result = -1; break; }
        size_t minimum = offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX, Group.GroupInfo);
        if (e->Relationship != RelationGroup || seen++ || e->Size < minimum) { result = -1; break; }
        WORD count = e->Group.ActiveGroupCount;
        if (!count || count > e->Group.MaximumGroupCount || count > (e->Size - minimum) / sizeof(PROCESSOR_GROUP_INFO)) { result = -1; break; }
        for (WORD g = 0; g < count; g++) {
            const PROCESSOR_GROUP_INFO *info = &e->Group.GroupInfo[g];
            if (!info->ActiveProcessorCount || info->ActiveProcessorCount > info->MaximumProcessorCount || info->MaximumProcessorCount > 64) { result = -1; break; }
            uint64_t mask = (uint64_t)info->ActiveProcessorMask;
            unsigned bits = 0;
            for (uint64_t value = mask; value; value >>= 1) bits += (unsigned)(value & 1);
            if (bits != info->ActiveProcessorCount || (info->MaximumProcessorCount < 64 && (mask >> info->MaximumProcessorCount))) { result = -1; break; }
            if (g < max) { out[g].group = g; out[g].active = info->ActiveProcessorCount; out[g].mask = mask; }
        }
        if (result < 0) break;
        result = count; /* return total count so the core labels its smaller bounded sample partial */
        off += e->Size;
    }
    if (!seen || off != used) result = -1;
    return result;
}

static int w_groups(void *ctx, nm_group *out, int max) {
    DWORD capacity = 0;
    BYTE *buf = NULL;
    int result = -1;
    (void)ctx;
    if (max <= 0) return -1;
    if (GetLogicalProcessorInformationEx(RelationGroup, NULL, &capacity) || GetLastError() != ERROR_INSUFFICIENT_BUFFER) return -1;
    for (unsigned attempt = 0; attempt < 3; attempt++) {
        if (!capacity || capacity > (1u << 20)) return -1;
        buf = (BYTE *)malloc(capacity);
        if (!buf) return -1;
        DWORD used = capacity;
        BOOL ok = GetLogicalProcessorInformationEx(RelationGroup, (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)buf, &used);
        if (!ok) {
            DWORD error = GetLastError(); free(buf); buf = NULL;
            if (error == ERROR_INSUFFICIENT_BUFFER && used > capacity) { capacity = used; continue; }
            return -1;
        }
        if (used > capacity) break;
        result = parse_group_buffer(buf, used, out, max);
        break;
    }
    free(buf);
    return result;
}

static int w_get_aff(void *ctx, nm_affinity *out) {
    GROUP_AFFINITY ga;
    memset(&ga, 0, sizeof ga);
    if (!GetThreadGroupAffinity(((win_ctx *)ctx)->thread, &ga)) return -1;
    out->group = ga.Group; out->mask = (uint64_t)ga.Mask;
    return 0;
}

static int w_set_aff(void *ctx, const nm_affinity *a) {
    GROUP_AFFINITY ga;
    memset(&ga, 0, sizeof ga);                       /* Reserved members must be zero */
    ga.Group = a->group; ga.Mask = (KAFFINITY)a->mask;
    if (!SetThreadGroupAffinity(((win_ctx *)ctx)->thread, &ga, NULL)) return -1;
    SwitchToThread();                                /* give the scheduler the chance to move this thread now */
    return 0;
}

static int w_where(void *ctx, nm_affinity *out) {
    PROCESSOR_NUMBER current;
    (void)ctx;
    memset(&current, 0, sizeof current);
    GetCurrentProcessorNumberEx(&current);
    if (current.Number >= 64) return -1;
    out->group = current.Group; out->mask = 1ull << current.Number;
    return 0;
}

static uint64_t w_now(void *ctx) { (void)ctx; return GetTickCount64(); }

typedef struct { nm_out out; int rc; volatile LONG done; } job;
static job g_job;
static char g_buf[NM_OUT_CAP];

static DWORD WINAPI worker(LPVOID p) {
    win_ctx ctx;
    nm_backend b;
    (void)p;
    ctx.thread = GetCurrentThread();                 /* pseudo-handle: this helper thread only */
    b.ctx = &ctx; b.cpuid = w_cpuid; b.xgetbv = w_xgetbv; b.groups = w_groups;
    b.get_affinity = w_get_aff; b.set_affinity = w_set_aff; b.now_ms = w_now; b.current_processor = w_where;
    g_job.rc = nm_collect(&b, &g_job.out, NM_DEFAULT_BUDGET_MS);
    InterlockedExchange(&g_job.done, 1);
    return 0;
}

static void write_out(const char *s, size_t n) {
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD w = 0;
    while (n && h && h != INVALID_HANDLE_VALUE && WriteFile(h, s, (DWORD)n, &w, NULL) && w) { s += w; n -= w; }
}

int main(int argc, char **argv) {
    static const char bad_args[] = "{\"schema\":\"nm-cpuinfo/1\",\"error\":\"arguments are not accepted\"}\n";
    static const char late[] = "{\"schema\":\"nm-cpuinfo/1\",\"error\":\"collection did not finish within its time cap\"}\n";
    HANDLE t;
    (void)argv;
    if (!nm_args_ok(argc)) { write_out(bad_args, sizeof bad_args - 1); return 2; }
    g_job.out.buf = g_buf; g_job.out.cap = sizeof g_buf;
    t = CreateThread(NULL, 64 * 1024, worker, NULL, 0, NULL);
    if (!t) { write_out(late, sizeof late - 1); return 3; }
    /* the helper stops itself at NM_DEFAULT_BUDGET_MS; this wait is the backstop for a thread that never returns */
    if (WaitForSingleObject(t, NM_DEFAULT_BUDGET_MS + 2000) != WAIT_OBJECT_0 || !g_job.done || g_job.rc != 0) {
        CloseHandle(t);
        write_out(late, sizeof late - 1);
        return 4;                                    /* process exit ends the helper; its affinity was its own */
    }
    CloseHandle(t);
    write_out(g_job.out.buf, g_job.out.len);
    write_out("\n", 1);
    return 0;
}
