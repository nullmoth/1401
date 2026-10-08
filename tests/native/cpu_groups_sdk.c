/* Real Windows SDK parser fixtures, compiled in the same translation unit as the production parser. */
#define main original_helper_main
#include "../../native/cpu/nm_cpuinfo_win.c"
#undef main
#include <stdio.h>
int main(void) {
    BYTE buffer[4096]; nm_group groups[NM_MAX_GROUPS];
    memset(buffer, 0, sizeof buffer);
    PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX e = (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)buffer;
    size_t minimum = offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX, Group.GroupInfo);
    e->Relationship = RelationGroup; e->Size = (DWORD)(minimum + 2 * sizeof(PROCESSOR_GROUP_INFO));
    e->Group.MaximumGroupCount = 2; e->Group.ActiveGroupCount = 2;
    e->Group.GroupInfo[0].MaximumProcessorCount = 64; e->Group.GroupInfo[0].ActiveProcessorCount = 64; e->Group.GroupInfo[0].ActiveProcessorMask = ~(KAFFINITY)0;
    e->Group.GroupInfo[1].MaximumProcessorCount = 64; e->Group.GroupInfo[1].ActiveProcessorCount = 8; e->Group.GroupInfo[1].ActiveProcessorMask = 0xff;
    if (parse_group_buffer(buffer, e->Size, groups, NM_MAX_GROUPS) != 2 || groups[1].group != 1 || groups[1].mask != 0xff) return 1;
    if (parse_group_buffer(buffer, e->Size, groups, 1) != 2) return 2; /* cap preserves total count */
    DWORD size = e->Size;
    e->Group.ActiveGroupCount = 100; if (parse_group_buffer(buffer,size,groups,NM_MAX_GROUPS) >= 0) return 3;
    e->Group.ActiveGroupCount = 2; e->Size = 8; if (parse_group_buffer(buffer,8,groups,NM_MAX_GROUPS) >= 0) return 4;
    e->Size = size; e->Group.GroupInfo[1].ActiveProcessorCount = 9; if (parse_group_buffer(buffer,size,groups,NM_MAX_GROUPS) >= 0) return 5;
    e->Group.GroupInfo[1].ActiveProcessorCount = 8; if (parse_group_buffer(buffer,size-1,groups,NM_MAX_GROUPS) >= 0) return 6;
    e->Size = 0; if (parse_group_buffer(buffer,size,groups,NM_MAX_GROUPS) >= 0) return 7;
    puts("{\"group_record_bounds\":true,\"mask_validation\":true,\"group_cap_status\":true}"); return 0;
}
