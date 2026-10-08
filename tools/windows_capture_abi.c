/* Compare the native Windows SDK layout with the Python capture bindings. No device access. */
#define _WIN32_WINNT 0x0A00
#include <windows.h>
#include <wintrust.h>
#include <stdio.h>
#include <stddef.h>
int main(void) {
    printf("{\"trust_size\":%zu,\"trust_file\":%zu,\"trust_state\":%zu,\"file_size\":%zu,\"file_handle\":%zu,"
           "\"group_size\":%zu,\"processor_groups\":%zu,\"processor_mask\":%zu,\"cache_mask\":%zu,\"numa_mask\":%zu}\n",
           sizeof(WINTRUST_DATA), offsetof(WINTRUST_DATA,pFile), offsetof(WINTRUST_DATA,hWVTStateData),
           sizeof(WINTRUST_FILE_INFO), offsetof(WINTRUST_FILE_INFO,hFile), sizeof(GROUP_AFFINITY),
           offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX,Processor.GroupCount),
           offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX,Processor.GroupMask),
           offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX,Cache.GroupMask),
           offsetof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX,NumaNode.GroupMask));
    return sizeof(void *) == 8 ? 0 : 1;
}
