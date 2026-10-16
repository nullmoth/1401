#import "NDNativeDiagnostics.h"
#import "NDTracePolicy.h"
#import <CommonCrypto/CommonDigest.h>
#import <IOKit/IOKitLib.h>
#import <Security/Security.h>
#include <libproc.h>
#include <sys/proc_info.h>
#include <sys/sysctl.h>
#include <sys/stat.h>
#include <sys/mount.h>
#include <dlfcn.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
static NSString *nd_hash_file(NSString *path){
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return nil;
    struct stat st;if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size>1024LL*1024*1024){close(fd);return nil;}
    CC_SHA256_CTX ctx;CC_SHA256_Init(&ctx);uint8_t data[65536];ssize_t n;while((n=read(fd,data,sizeof data))>0)CC_SHA256_Update(&ctx,data,(CC_LONG)n);close(fd);if(n<0)return nil;
    uint8_t digest[32];CC_SHA256_Final(digest,&ctx);NSMutableString *result=[NSMutableString new];for(unsigned i=0;i<32;i++)[result appendFormat:@"%02x",digest[i]];return result;
}
static OSStatus nd_apple_tool_signature(NSString *path){
    SecStaticCodeRef code=NULL;SecRequirementRef requirement=NULL;
    OSStatus status=SecStaticCodeCreateWithPath((__bridge CFURLRef)[NSURL fileURLWithPath:path],kSecCSDefaultFlags,&code);
    if(status==errSecSuccess)status=SecRequirementCreateWithString(CFSTR("anchor apple and identifier com.apple.dtrace"),kSecCSDefaultFlags,&requirement);
    if(status==errSecSuccess)status=SecStaticCodeCheckValidity(code,kSecCSCheckAllArchitectures|kSecCSStrictValidate|kSecCSNoNetworkAccess,requirement);
    if(requirement)CFRelease(requirement);if(code)CFRelease(code);return status;
}
static NSString *nd_system_value(const char *name){char value[256];size_t size=sizeof value;if(sysctlbyname(name,value,&size,NULL,0)||!size||size>sizeof value)return @"unavailable";value[sizeof value-1]=0;return @(value);}
static NSDictionary *nd_target(pid_t pid,uid_t owner,BOOL includeHash){
    struct proc_bsdinfo info;char path[PROC_PIDPATHINFO_MAXSIZE];
    int(*csops_read)(pid_t,unsigned,void*,size_t)=dlsym(RTLD_DEFAULT,"csops");uint32_t flags=0;
    if(pid<=1||proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&info,sizeof info)!=sizeof info||proc_pidpath(pid,path,sizeof path)<=0||!csops_read||csops_read(pid,0,&flags,sizeof flags))return @{@"known":@NO};
    struct stat st;if(stat(path,&st))return @{@"known":@NO};NSString *hash=includeHash?nd_hash_file(@(path)):@"not_requested";
    if(!hash)return @{@"known":@NO};
    return @{@"known":@YES,@"pid":@(pid),@"ownedByClient":@((BOOL)(info.pbi_uid==owner&&info.pbi_ruid==owner)),@"systemProcess":@((BOOL)((info.pbi_flags&PROC_FLAG_SYSTEM)!=0)),
        @"startSeconds":@(info.pbi_start_tvsec),@"startMicroseconds":@(info.pbi_start_tvusec),@"codeStatus":@(flags),@"executableSHA256":hash,
        @"fileDevice":@(st.st_dev),@"fileInode":@(st.st_ino),@"fileBytes":@(st.st_size),@"fileModifiedSeconds":@(st.st_mtimespec.tv_sec),@"fileModifiedNanoseconds":@(st.st_mtimespec.tv_nsec)};
}
static NSArray *nd_devices(void){
    io_iterator_t iterator=0;NSMutableArray *result=[NSMutableArray new];
    if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("IOPCIDevice"),&iterator))return result;
    io_service_t service;while((service=IOIteratorNext(iterator))){
        CFMutableDictionaryRef props=NULL;uint64_t registry=0;
        if(result.count<64&&IORegistryEntryCreateCFProperties(service,&props,kCFAllocatorDefault,0)==KERN_SUCCESS){
            NSDictionary *p=CFBridgingRelease(props);NSMutableDictionary *r=[NSMutableDictionary new];
            for(NSString *key in @[@"vendor-id",@"device-id",@"subsystem-vendor-id",@"subsystem-id",@"class-code",@"revision-id"]){NSData *v=p[key];if([v isKindOfClass:[NSData class]]&&v.length>=4){uint32_t number;memcpy(&number,v.bytes,4);r[key]=@(number);}}
            if(!IORegistryEntryGetRegistryEntryID(service,&registry))r[@"registryEntryID"]=@(registry);if(r.count)[result addObject:r];
        }
        IOObjectRelease(service);
    }IOObjectRelease(iterator);return result;
}
NSDictionary *NDParseProviderInventory(NSDictionary *process){
    NSMutableDictionary *providers=[NSMutableDictionary new];
    NSString *text=[[NSString alloc]initWithData:process[@"output"] encoding:NSUTF8StringEncoding];
    for(NSString *probe in @[@"profile-10",@"tick-1sec",@"BEGIN",@"END",@"ERROR"]){
        BOOL found=NO;for(NSString *line in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]){
            NSArray *fields=[[line componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceCharacterSet] filteredArrayUsingPredicate:[NSPredicate predicateWithFormat:@"length > 0"]];
            if(fields.count<3)continue;NSScanner *idScanner=[NSScanner scannerWithString:fields[0]];unsigned long long probeID=0;
            if(![idScanner scanUnsignedLongLong:&probeID]||!idScanner.isAtEnd)continue;
            if([fields.lastObject isEqual:probe]&&[fields[1] isEqual:([probe hasPrefix:@"profile-"]||[probe hasPrefix:@"tick-"])?@"profile":@"dtrace"])found=YES;
        }providers[probe]=@((BOOL)(found&&[process[@"status"] isEqual:@"completed"]));
    }return providers;
}
NSDictionary *NDPrerequisites(pid_t target,uid_t owner,NSTimeInterval budget){
    int(*check)(uint32_t)=dlsym(RTLD_DEFAULT,"csr_check");int(*active)(uint32_t*)=dlsym(RTLD_DEFAULT,"csr_get_active_config");uint32_t config=0;
    BOOL known=check&&active&&active(&config)==0,allowed=known&&check(ND_CSR_DTRACE)==0;
    NSString *toolHash=nd_hash_file(@"/usr/sbin/dtrace");OSStatus toolStatus=nd_apple_tool_signature(@"/usr/sbin/dtrace");BOOL toolValid=toolHash&&toolStatus==errSecSuccess;NSDictionary *targetState=nd_target(target,owner,YES);
    int cpus=0;size_t size=sizeof cpus;sysctlbyname("hw.logicalcpu",&cpus,&size,NULL,0);
    NSMutableDictionary *providers=[NSMutableDictionary new];NSString *inventoryStatus=@"not_checked_missing_prerequisites";
    /* Provider listing never enables probes. Do not invoke even listing until the
       checked privileged session environment is available. */
    if(geteuid()==0&&known&&allowed&&(config&ND_CSR_DTRACE)&&toolValid&&budget>0&&budget<=3){
        NSDictionary *p=NDExecuteBounded(@"/usr/sbin/dtrace",@[@"-l",@"-n",@"profile:::profile-10",@"-n",@"profile:::tick-1sec",@"-n",@"dtrace:::BEGIN",@"-n",@"dtrace:::END",@"-n",@"dtrace:::ERROR"],budget,16384,nil,nil);
        inventoryStatus=p[@"status"];[providers addEntriesFromDictionary:NDParseProviderInventory(p)];
    }
    NSMutableArray *components=[NSMutableArray new];
    Dl_info ownImage;NSString *helperHash=nil;
    if(dladdr((const void*)&NDPrerequisites,&ownImage)&&ownImage.dli_fname)helperHash=nd_hash_file(@(ownImage.dli_fname));
    [components addObject:@{@"component":@"local_diagnostics_helper",@"present":@(helperHash!=nil),@"SHA256":helperHash?:@"unavailable"}];
    NSDictionary *locations=@{
        @"gpu_plugin":@"/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver",
        @"translator_bundle_sibling":@"/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/libnvmtl_translate.dylib",
        @"translator_runtime_fallback":@"/Library/GPUBundles/nvmtl/libnvmtl_translate.dylib",
        @"vulkan_loader":@"/Library/GPUBundles/nvmtl/libvulkan.dylib",
        @"vulkan_backend":@"/Library/GPUBundles/nvmtl/libvulkan_nouveau.dylib",
        @"NVRM":@"/Library/Extensions/NVRM.kext/Contents/MacOS/NVRM",
        @"NVAccel":@"/Library/Extensions/NVAccel.kext/Contents/MacOS/NVAccel",
        @"NVRMFB":@"/Library/Extensions/NVRMFB.kext/Contents/MacOS/NVRMFB",
        @"NVRMAGDC":@"/Library/Extensions/NVRMAGDC.kext/Contents/MacOS/NVRMAGDC"};
    for(NSString *component in [[locations allKeys] sortedArrayUsingSelector:@selector(compare:)]){NSString *hash=nd_hash_file(locations[component]);[components addObject:@{@"component":component,@"present":@(hash!=nil),@"SHA256":hash?:@"unavailable",@"loadedState":@"not_observed"}];}
    struct statfs volume;NSArray *fsid=@[];
    if(!statfs("/",&volume))fsid=@[@(volume.f_fsid.val[0]),@(volume.f_fsid.val[1])];
    NSString *bootUUID=nd_system_value("kern.bootsessionuuid");if(![[NSUUID alloc]initWithUUIDString:bootUUID])bootUUID=@"unavailable";
    return @{@"schemaVersion":@1,@"tool":@{@"path":@"/usr/sbin/dtrace",@"available":@(toolValid),@"signatureStatus":@(toolStatus),@"AppleSignatureVerified":@((BOOL)(toolStatus==errSecSuccess)),@"signatureNetworkAccess":@NO,@"SHA256":toolHash?:@"unavailable"},
        @"csr":@{@"known":@(known),@"activeConfig":@(config),@"requiredFlag":@(ND_CSR_DTRACE),@"activeBitSet":@((BOOL)((config&ND_CSR_DTRACE)!=0)),@"effectivePermissionAllowed":@(allowed)},
        @"administrator":@((BOOL)(geteuid()==0)),@"target":targetState,@"providers":providers,@"providerInventoryStatus":inventoryStatus,
        @"system":@{@"osVersion":nd_system_value("kern.osproductversion"),@"osBuild":nd_system_value("kern.osversion"),@"kernelRelease":nd_system_value("kern.osrelease"),@"modelReportedByOS":nd_system_value("hw.model"),@"logicalCPUs":@(cpus),@"startupVolumeFSID":fsid,@"bootSessionUUID":bootUUID},@"PCIdevices":nd_devices(),@"components":components,
        @"limitations":@[@"CPU scheduling counts only; no GPU commands, kernel function bodies, stack addresses, memory or document contents are collected.",@"Some processes deny tracing independently of SIP; zero samples are inconclusive."]};
}
NSDictionary *NDRunApprovedSession(pid_t pid,uid_t owner,unsigned seconds,NDConsumeLocalConsent consent,NDCancelCheck cancel){
    if(cancel&&cancel())return @{@"status":@"blocked",@"reason":@"cancelled",@"traceEnabled":@NO};
    NSDictionary *preview=NDPrerequisites(pid,owner,0);
    if(!consent || !consent(preview))return @{@"status":@"blocked",@"reason":@"explicit_local_session_authorization_required",@"receipt":preview,@"traceEnabled":@NO};
    NSDictionary *receipt=NDPrerequisites(pid,owner,3),*csr=receipt[@"csr"],*target=receipt[@"target"],*probes=receipt[@"providers"];
    NDRequirements facts={0};facts.authenticated_client=1;facts.explicit_session_consent=1;facts.authorization_granted=1;
    facts.administrator=[receipt[@"administrator"] boolValue];facts.csr_known=[csr[@"known"] boolValue];facts.csr_check_allowed=[csr[@"effectivePermissionAllowed"] boolValue];facts.csr_active_bit=[csr[@"activeBitSet"] boolValue];facts.tool_valid=[receipt[@"tool"][@"available"] boolValue];
    facts.target_known=[target[@"known"] boolValue];facts.target_identity_matches=[target isEqual:preview[@"target"]];facts.target_owned_by_client=[target[@"ownedByClient"] boolValue];facts.target_system=[target[@"systemProcess"] boolValue];facts.target_cs_flags=[target[@"codeStatus"] unsignedIntValue];
    facts.profile_probe=[probes[@"profile-10"] boolValue];facts.timer_probe=[probes[@"tick-1sec"] boolValue];facts.lifecycle_probes=[probes[@"BEGIN"] boolValue]&&[probes[@"END"] boolValue]&&[probes[@"ERROR"] boolValue];facts.duration_seconds=seconds;facts.logical_cpus=[receipt[@"system"][@"logicalCPUs"] unsignedIntValue];
    const char *refusal=NDTraceRefusal(&facts);if(refusal)return @{@"status":@"blocked",@"reason":@(refusal),@"receipt":receipt,@"traceEnabled":@NO};
    char script[2048];if(NDTraceScript(script,sizeof script,pid,owner,seconds)<0)return @{@"status":@"blocked",@"reason":@"script_generation_failed",@"traceEnabled":@NO};
    /* No shell, target launch, attach/stop option, wildcard provider or input D code. */
    NSMutableDictionary *expected=[target mutableCopy];expected[@"executableSHA256"]=@"not_requested";
    NSDictionary *transport=NDExecuteBounded(@"/usr/sbin/dtrace",@[@"-q",@"-n",@(script)],seconds+2,ND_TRACE_MAX_BYTES,cancel,^BOOL{NSDictionary *now=nd_target(pid,owner,NO);return [now isEqual:expected];});
    NSDictionary *trace=NDParseTrace(transport);
    return @{@"status":@"session_finished",@"receipt":receipt,@"trace":trace,@"traceAttempted":@YES,@"traceEnabled":trace[@"started"],@"securitySettingsChanged":@NO};
}
