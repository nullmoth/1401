#include "NDTracePolicy.h"
#include <stdio.h>
const char *NDTraceRefusal(const NDRequirements *f) {
    if(!f || !f->authenticated_client) return "local_client_not_authenticated";
    if(!f->explicit_session_consent) return "explicit_session_consent_required";
    if(!f->authorization_granted || !f->administrator) return "administrator_authorization_required";
    if(!f->csr_known) return "csr_permission_unknown";
    if(!f->csr_check_allowed || !f->csr_active_bit) return "csr_dtrace_permission_required";
    if(!f->tool_valid) return "system_dtrace_unavailable";
    if(!f->target_known || !f->target_identity_matches) return "target_unavailable_or_changed";
    if(!f->target_owned_by_client) return "target_owner_mismatch";
    if(f->target_system || (f->target_cs_flags&(ND_CS_RESTRICT|ND_CS_PLATFORM_BINARY))) return "protected_target_refused";
    if(!f->profile_probe || !f->timer_probe || !f->lifecycle_probes) return "required_probe_unavailable";
    if(!f->duration_seconds || f->duration_seconds>ND_TRACE_MAX_SECONDS) return "duration_out_of_range";
    if(!f->logical_cpus || f->logical_cpus>ND_TRACE_MAX_CPUS) return "cpu_count_out_of_range";
    return NULL;
}
int NDTraceScript(char *out,size_t capacity,int pid,unsigned owner,unsigned seconds) {
    if(pid<=1 || !seconds || seconds>ND_TRACE_MAX_SECONDS || !out) return -1;
    int n=snprintf(out,capacity,
        "#pragma D option quiet\n#pragma D option bufsize=16k\n#pragma D option aggsize=16k\n"
        "#pragma D option dynvarsize=16k\n#pragma D option switchrate=2hz\n"
        "dtrace:::BEGIN { started = timestamp; printf(\"ND_START\\n\"); }\n"
        "profile:::profile-10 /pid == %d && uid == %u/ { @samples = count(); }\n"
        "profile:::tick-1sec /timestamp - started >= %lluULL/ { exit(0); }\n"
        "dtrace:::ERROR { @errors = count(); }\n"
        "dtrace:::END { printa(\"ND_SAMPLES %%@d\\n\", @samples); "
        "printa(\"ND_ERRORS %%@d\\n\", @errors); printf(\"ND_END\\n\"); }\n",pid,owner,(unsigned long long)seconds*1000000000ULL);
    return n<0 || (size_t)n>=capacity ? -1 : n;
}
