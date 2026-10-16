#import "authority/NDSecurityState.h"
#import "authority/NDAuthorityPolicy.h"
#import "authority/NDCaptureRight.h"
#import "module/NDNativeDiagnostics.h"
#include <unistd.h>
#include <limits.h>
#include <stdlib.h>

/* Read-only entry: provider budget zero prevents listing or enabling probes.
   An installed receipt never qualifies this release's installer bridge. */
int main(int argc, const char **argv) { @autoreleasepool {
    if (argc != 2 || geteuid() == 0) return 2;
    char *end = NULL; long pid = strtol(argv[1], &end, 10);
    if (!end || *end || pid <= 1 || pid > INT_MAX) return 2;
    NSDictionary *preview = NDPrerequisites((pid_t)pid, getuid(), 0);
    NSString *error = nil;
    NDAuthorityPolicy *policy = [NDAuthorityPolicy loadInstalled:&error];
    BOOL pins = policy && [policy verifyAppAndHelperFiles:&error];
    NSDictionary *result = @{
        @"schema": @"nullmoth-optional-diagnostics/1", @"status": @"blocked",
        @"captureAvailable": @NO, @"productionBridgeQualified": @NO,
        @"authorityReason": @"verified_privileged_installer_bridge_unqualified",
        @"installedPinsVerified": @(pins), @"installedCaptureRightVerified": @(pins && NDCaptureRightConfigured()),
        @"security": NDCurrentSecurityState(), @"tool": preview[@"tool"], @"csr": preview[@"csr"],
        @"providerInventoryStatus": preview[@"providerInventoryStatus"], @"ordinaryLogsAvailable": @YES
    };
    NSData *json = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:nil];
    if (!json || json.length > 32768) return 3;
    fwrite(json.bytes, 1, json.length, stdout); fputc('\n', stdout);
    return 0;
} }
