#import "NDSecurityState.h"
#import "NDAuthorityPolicy.h"
#import "../module/NDBoundedProcess.h"
#include <dlfcn.h>
#include <sys/sysctl.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>

NSDictionary *NDEvaluateSecurityState(NSDictionary *facts){
    NSMutableArray *reasons=[NSMutableArray new];
    if(![facts[@"csrKnown"] boolValue]) [reasons addObject:@"sip_state_unknown"];
    else{
        if(([facts[@"csrConfig"] unsignedIntValue]&0x1cu)||[facts[@"debugCSREffectivelyAllowed"] boolValue]) [reasons addObject:@"security_policy_incompatible_with_authenticated_capture"];
        if(![facts[@"dtraceEffectivelyAllowed"] boolValue]||!([facts[@"csrConfig"] unsignedIntValue]&0x20u)) [reasons addObject:@"unrestricted_dtrace_permission_missing"];
    }
    if(![facts[@"bootPolicyKnown"] boolValue])[reasons addObject:@"boot_security_policy_unknown"];
    else if([facts[@"unsafeBootPolicy"] boolValue])[reasons addObject:@"boot_security_policy_incompatible"];
    if(![facts[@"libraryPolicyKnown"] boolValue])[reasons addObject:@"library_validation_policy_unknown"];
    else if([facts[@"libraryValidationDisabled"] boolValue])[reasons addObject:@"system_library_validation_disabled"];
    if(![facts[@"selfRuntimeKnown"] boolValue]||![facts[@"selfRuntimeEnforced"] boolValue])[reasons addObject:@"hardened_runtime_unavailable"];
    return @{@"schemaVersion":@1,@"status":reasons.count?@"blocked":@"compatible",@"allowed":@(reasons.count==0),@"reasons":reasons,@"facts":facts,@"kernelIntegrityAttestation":@"not_available",@"ordinaryLogsAvailable":@YES};
}
NSDictionary *NDCurrentSecurityState(void){
    int(*check)(uint32_t)=dlsym(RTLD_DEFAULT,"csr_check");int(*active)(uint32_t*)=dlsym(RTLD_DEFAULT,"csr_get_active_config");uint32_t config=0;
    BOOL csrKnown=check&&active&&active(&config)==0,other=NO;
    if(csrKnown)for(unsigned bit=2;bit<=4;bit++)if(check(1u<<bit)==0)other=YES;
    char arguments[4096]={0};size_t length=sizeof arguments;BOOL bootKnown=sysctlbyname("kern.bootargs",arguments,&length,NULL,0)==0&&length>0&&length<=sizeof arguments;
    NSMutableArray *overrides=[NSMutableArray new];BOOL unsafe=NO;if(bootKnown){NSString *text=[[NSString alloc]initWithBytes:arguments length:strnlen(arguments,sizeof arguments) encoding:NSUTF8StringEncoding];bootKnown=text!=nil;
        for(NSString *token in [text componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceCharacterSet]){NSString *key=[[[token componentsSeparatedByString:@"="] firstObject]lowercaseString];
            NSArray *parts=[token componentsSeparatedByString:@"="];NSString *value=parts.count==2?parts[1]:@"";NSScanner *scanner=[NSScanner scannerWithString:value];unsigned long long number=0;BOOL numeric=value.length&&[scanner scanUnsignedLongLong:&number]&&scanner.isAtEnd;
            if([value.lowercaseString hasPrefix:@"0x"]){scanner=[NSScanner scannerWithString:[value substringFromIndex:2]];numeric=[scanner scanHexLongLong:&number]&&scanner.isAtEnd;}
            BOOL codeOverride=[@[@"amfi_get_out_of_my_way",@"amfi_allow_any_signature",@"amfi_unrestrict_task_for_pid",@"cs_enforcement_disable",@"amfi_disable_library_validation"] containsObject:key];
            if((codeOverride&&(!numeric||number!=0))||([key isEqual:@"amfi"]&&(!numeric||number!=0))||([key isEqual:@"ipc_control_port_options"]&&(!numeric||number==0))||[key hasPrefix:@"-amfipass"]||([key isEqual:@"dyld_flags"]&&(!numeric||number!=0))){unsafe=YES;[overrides addObject:key];}}}
    BOOL libraryKnown=YES,disabled=NO;const char *path="/Library/Preferences/com.apple.security.libraryvalidation.plist";struct stat s;
    if(lstat(path,&s)==0){libraryKnown=S_ISREG(s.st_mode)&&s.st_uid==0&&!(s.st_mode&0022)&&s.st_size>0&&s.st_size<=65536;
        if(libraryKnown){int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);NSMutableData *data=[NSMutableData dataWithLength:(NSUInteger)s.st_size];ssize_t n=fd<0?-1:read(fd,data.mutableBytes,data.length);if(fd>=0)close(fd);id plist=n==(ssize_t)data.length?[NSPropertyListSerialization propertyListWithData:data options:0 format:NULL error:nil]:nil;
            libraryKnown=[plist isKindOfClass:NSDictionary.class];if(libraryKnown){id value=plist[@"DisableLibraryValidation"];libraryKnown=!value||[value isKindOfClass:NSNumber.class];disabled=[value boolValue];}}}
    else libraryKnown=errno==ENOENT;
    int(*readFlags)(pid_t,unsigned,void*,size_t)=dlsym(RTLD_DEFAULT,"csops");uint32_t flags=0;BOOL runtimeKnown=readFlags&&readFlags(getpid(),0,&flags,sizeof flags)==0;
    return NDEvaluateSecurityState(@{@"csrKnown":@(csrKnown),@"csrConfig":@(config),@"dtraceEffectivelyAllowed":@(csrKnown&&check(0x20)==0),@"debugCSREffectivelyAllowed":@(other),@"bootPolicyKnown":@(bootKnown),@"unsafeBootPolicy":@(unsafe),@"observedUnsafePolicyKeys":overrides,@"libraryPolicyKnown":@(libraryKnown),@"libraryValidationDisabled":@(disabled),@"selfRuntimeKnown":@(runtimeKnown),@"selfRuntimeEnforced":@(runtimeKnown&&(flags&1u)&&NDTraceSigningFlagsAllow(flags,nil))});
}
NSDictionary *NDLibraryValidationEvidence(NSString *bundle){
    /* Caller first verifies the complete root-owned pinned bundle. These two
       harmless fixed images test effective policy, never a requested payload. */
    NSString *directory=[bundle stringByAppendingPathComponent:@"Contents/Resources"];
    NSDictionary *baseline=NDExecuteBounded([directory stringByAppendingPathComponent:@"nd-lv-baseline"],@[],1,1024,nil,nil);
    if(![baseline[@"status"] isEqual:@"completed"]||![baseline[@"childReaped"] boolValue])return @{@"allowed":@NO,@"reason":@"library_validation_control_unavailable"};
    void *library=dlopen([directory stringByAppendingPathComponent:@"nd-untrusted-probe.dylib"].fileSystemRepresentation,RTLD_NOW|RTLD_LOCAL);
    if(library){dlclose(library);return @{@"allowed":@NO,@"reason":@"library_validation_not_enforced"};}
    return @{@"allowed":@YES,@"reason":@"control_loads_hardened_process_refuses",@"scope":@"fixed_inert_library_probe",@"kernelIntegrityAttestation":@"not_available"};
}
