#ifndef ND_TRACE_POLICY_H
#define ND_TRACE_POLICY_H
#include <stdint.h>
#include <stddef.h>
#define ND_CSR_DTRACE 0x20u
#define ND_CS_RESTRICT 0x800u
#define ND_CS_PLATFORM_BINARY 0x04000000u
#define ND_TRACE_MAX_SECONDS 15u
#define ND_TRACE_MAX_BYTES 65536u
#define ND_TRACE_MAX_CPUS 256u
/* These facts must be obtained by the privileged local helper, never from app JSON. */
typedef struct {
    int authenticated_client, explicit_session_consent, authorization_granted;
    int csr_known, csr_check_allowed, csr_active_bit, administrator, tool_valid;
    int target_known, target_owned_by_client, target_system, target_identity_matches;
    uint32_t target_cs_flags;
    int profile_probe, timer_probe, lifecycle_probes;
    unsigned duration_seconds, logical_cpus;
} NDRequirements;
/* Returns a stable refusal code or NULL. No operation changes policy or enables probes. */
const char *NDTraceRefusal(const NDRequirements *facts);
int NDTraceScript(char *output, size_t capacity, int pid, unsigned owner, unsigned seconds);
#endif
