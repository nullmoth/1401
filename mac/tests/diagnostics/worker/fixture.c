#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    if (strstr(argv[0], "slow")) {
        char name[4096]; if (snprintf(name, sizeof name, "%s.pid", argv[0]) >= (int)sizeof name) return 2;
        FILE *f = fopen(name, "w"); if (!f) return 2; fprintf(f, "%d", getpid()); fclose(f);
        sleep(20); return 0;
    }
    if (strstr(argv[0], "oversized")) { for (unsigned i = 0; i < 40000; i++) putchar('x'); return 0; }
    if (strstr(argv[0], "invalid")) { puts("{bad}"); return 0; }
    if (strstr(argv[0], "failure")) return 5;
    printf("{\"schema\":\"nullmoth-optional-diagnostics/1\",\"status\":\"blocked\",\"captureAvailable\":%s,\"productionBridgeQualified\":false}", strstr(argv[0], "forged") ? "true" : "false");
    return 0;
}
