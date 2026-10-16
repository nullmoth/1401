#import "NDAuthorityPolicy.h"
#import "NDCaptureRight.h"
#import <Security/Security.h>
#import <CommonCrypto/CommonDigest.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
static const char *nd_policy_path="/Library/Application Support/NullMoth/Diagnostics/authority-policy.json";
static NSArray *nd_unsafe_entitlements(void){return @[@"com.apple.security.get-task-allow",@"com.apple.security.cs.disable-library-validation",@"com.apple.security.cs.allow-dyld-environment-variables",@"com.apple.security.cs.allow-unsigned-executable-memory",@"com.apple.security.cs.disable-executable-page-protection",@"com.apple.security.cs.allow-jit"];} 
BOOL NDTraceSigningFlagsAllow(uint32_t flags,NSDictionary *entitlements){
    uint32_t required=kSecCodeSignatureRuntime|kSecCodeSignatureLibraryValidation;
    if((flags&required)!=required||(flags&(0x00000004u|0x10000000u)))return NO;
    if(entitlements&&![entitlements isKindOfClass:[NSDictionary class]])return NO;
    for(NSString *key in nd_unsafe_entitlements())if(entitlements[key])return NO;
    return YES;
}
static BOOL nd_hex(NSString *s,NSUInteger count){return [s isKindOfClass:[NSString class]]&&s.length==count&&[s rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location==NSNotFound;}
static NSString *nd_hash_requirement(id hashes){
    if(![hashes isKindOfClass:[NSArray class]]||![hashes count]||[hashes count]>4)return nil;
    NSMutableArray *parts=[NSMutableArray new];NSMutableSet *seen=[NSMutableSet new];
    for(id hash in hashes){if(!nd_hex(hash,40)||[seen containsObject:hash])return nil;[seen addObject:hash];[parts addObject:[NSString stringWithFormat:@"cdhash H\"%@\"",hash]];}
    return [NSString stringWithFormat:@"(%@)",[parts componentsJoinedByString:@" or "]];
}
static BOOL nd_root_path(NSString *path,BOOL file){
    if(!path.isAbsolutePath || ![path isEqual:path.stringByStandardizingPath])return NO;
    NSString *prefix=@"/";NSArray *parts=path.pathComponents;
    for(NSUInteger i=1;i<parts.count;i++){prefix=[prefix stringByAppendingPathComponent:parts[i]];struct stat s;if(lstat(prefix.fileSystemRepresentation,&s)||s.st_uid!=0||(s.st_mode&0022)||S_ISLNK(s.st_mode))return NO;if(i+1<parts.count&&!S_ISDIR(s.st_mode))return NO;if(i+1==parts.count&&!(file?S_ISREG(s.st_mode):S_ISDIR(s.st_mode)))return NO;}
    return YES;
}
static NSString *nd_sha(NSString *path){
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return nil;struct stat s;
    if(fstat(fd,&s)||!S_ISREG(s.st_mode)||s.st_uid!=0||(s.st_mode&0022)||s.st_size>1024LL*1024*1024){close(fd);return nil;}
    CC_SHA256_CTX c;CC_SHA256_Init(&c);uint8_t buffer[65536];ssize_t n;while((n=read(fd,buffer,sizeof buffer))>0)CC_SHA256_Update(&c,buffer,(CC_LONG)n);close(fd);if(n<0)return nil;
    uint8_t digest[32];CC_SHA256_Final(digest,&c);NSMutableString *out=[NSMutableString new];for(unsigned i=0;i<32;i++)[out appendFormat:@"%02x",digest[i]];return out;
}
@implementation NDAuthorityPolicy
+ (instancetype)parse:(NSData*)data error:(NSString**)error{
    if(error)*error=nil;if(!data || data.length>65536){if(error)*error=@"policy_size_invalid";return nil;}
    NSDictionary *p=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if(![p isKindOfClass:[NSDictionary class]]||![p[@"schemaVersion"] isKindOfClass:[NSNumber class]]||![p[@"schemaVersion"] isEqual:@1]||![p[@"app"] isKindOfClass:[NSDictionary class]]||![p[@"helper"] isKindOfClass:[NSDictionary class]]){if(error)*error=@"policy_schema_invalid";return nil;}
    NSDictionary *app=p[@"app"],*helper=p[@"helper"];NSDictionary *files=app[@"files"];
    NSString *appHashes=nd_hash_requirement(app[@"cdHashes"]),*helperHashes=nd_hash_requirement(helper[@"cdHashes"]);
    if(!nd_hex(p[@"verifiedPackageSHA256"],64)||!appHashes||!nd_hex(app[@"executableSHA256"],64)||!helperHashes||!nd_hex(helper[@"SHA256"],64)||
       ![app[@"bundleIdentifier"] isEqual:@"com.nullmoth.1401.diagnostics"]||![app[@"bundlePath"] isKindOfClass:[NSString class]]||![app[@"bundlePath"] hasPrefix:@"/Library/Application Support/NullMoth/Diagnostics/"]||
       ![app[@"bundlePath"] isEqual:[app[@"bundlePath"] stringByStandardizingPath]]||[[app[@"bundlePath"] pathComponents] containsObject:@".."]||![app[@"executableRelativePath"] isEqual:@"Contents/MacOS/NullMothDiagnostics"]||![helper[@"path"] isEqual:@"/Library/PrivilegedHelperTools/com.nullmoth.1401.trace"]||
       ![files isKindOfClass:[NSDictionary class]]||!files.count||files.count>256||![files[app[@"executableRelativePath"]] isEqual:app[@"executableSHA256"]]){if(error)*error=@"policy_pins_invalid";return nil;}
    for(id relative in files){if(![relative isKindOfClass:[NSString class]]||![relative length]||[relative isAbsolutePath]||![relative isEqual:[relative stringByStandardizingPath]]||[[relative pathComponents] containsObject:@".."]||!nd_hex(files[relative],64)){if(error)*error=@"policy_manifest_invalid";return nil;}}
    NDAuthorityPolicy *policy=[NDAuthorityPolicy new];policy->_receipt=p;
    NSMutableString *suffix=[NSMutableString new];for(NSString *key in nd_unsafe_entitlements())[suffix appendFormat:@" and ! entitlement[\"%@\"] exists",key];
    policy->_appRequirement=[NSString stringWithFormat:@"identifier \"com.nullmoth.1401.diagnostics\" and %@%@",appHashes,suffix];
    policy->_helperRequirement=[helperHashes stringByAppendingString:suffix];return policy;
}
+ (instancetype)loadInstalled:(NSString**)error{
    NSString *path=@(nd_policy_path);if(!nd_root_path(path,YES)){if(error)*error=@"verified_root_pin_policy_required";return nil;}
    int fd=open(nd_policy_path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0){if(error)*error=@"policy_open_failed";return nil;}
    struct stat s;if(fstat(fd,&s)||s.st_uid!=0||(s.st_mode&0022)||!S_ISREG(s.st_mode)||s.st_size<=0||s.st_size>65536){close(fd);if(error)*error=@"policy_file_invalid";return nil;}
    NSMutableData *data=[NSMutableData dataWithLength:(NSUInteger)s.st_size];NSUInteger offset=0;while(offset<data.length){ssize_t n=read(fd,(uint8_t*)data.mutableBytes+offset,data.length-offset);if(n<=0)break;offset+=n;}close(fd);
    if(offset!=data.length){if(error)*error=@"policy_read_failed";return nil;}return [self parse:data error:error];
}
- (BOOL)verifyAppAndHelperFiles:(NSString**)error{
    if(error)*error=nil;NSDictionary *app=_receipt[@"app"],*helper=_receipt[@"helper"];NSString *bundle=app[@"bundlePath"],*helperPath=helper[@"path"];
    if(!nd_root_path(bundle,NO)||!nd_root_path(helperPath,YES)){if(error)*error=@"pinned_files_not_root_controlled";return NO;}
    NSMutableSet *seen=[NSMutableSet new];NSDirectoryEnumerator *enumerator=[[NSFileManager defaultManager] enumeratorAtPath:bundle];
    for(NSString *relative in enumerator){NSString *path=[bundle stringByAppendingPathComponent:relative];struct stat s;
        if(lstat(path.fileSystemRepresentation,&s)||s.st_uid!=0||(s.st_mode&0022)||S_ISLNK(s.st_mode)){if(error)*error=@"app_tree_not_root_controlled";return NO;}
        if(S_ISDIR(s.st_mode))continue;if(!S_ISREG(s.st_mode)||![app[@"files"][relative] isKindOfClass:[NSString class]]||![nd_sha(path) isEqual:app[@"files"][relative]]){if(error)*error=@"app_tree_pin_mismatch";return NO;}[seen addObject:relative];
    }
    if(![seen isEqual:[NSSet setWithArray:[app[@"files"] allKeys]]]||![nd_sha(helperPath) isEqual:helper[@"SHA256"]]){if(error)*error=@"installed_file_pin_mismatch";return NO;}
    for(NSArray *entry in @[@[[bundle stringByAppendingPathComponent:app[@"executableRelativePath"]],_appRequirement],@[helperPath,_helperRequirement]]){
        SecStaticCodeRef code=NULL;SecRequirementRef requirement=NULL;OSStatus status=SecStaticCodeCreateWithPath((__bridge CFURLRef)[NSURL fileURLWithPath:entry[0]],kSecCSDefaultFlags,&code);
        if(!status)status=SecRequirementCreateWithString((__bridge CFStringRef)entry[1],kSecCSDefaultFlags,&requirement);
        if(!status)status=SecStaticCodeCheckValidity(code,kSecCSCheckAllArchitectures|kSecCSStrictValidate|kSecCSNoNetworkAccess,requirement);
        CFDictionaryRef info=NULL;if(!status)status=SecCodeCopySigningInformation(code,kSecCSSigningInformation,&info);
        BOOL hardened=NO;if(!status&&info){NSDictionary *values=(__bridge NSDictionary*)info;hardened=NDTraceSigningFlagsAllow([values[(__bridge NSString*)kSecCodeInfoFlags] unsignedIntValue],values[(__bridge NSString*)kSecCodeInfoEntitlementsDict]);}
        if(info)CFRelease(info);
        if(requirement)CFRelease(requirement);if(code)CFRelease(code);if(status){if(error)*error=@"installed_signature_pin_mismatch";return NO;}
        if(!hardened){if(error)*error=@"hardened_authority_images_required";return NO;}
    }return YES;
}
@end
BOOL NDAdministratorFormIsGranted(NSData *data){
    if(![data isKindOfClass:[NSData class]]||data.length!=kAuthorizationExternalFormLength)return NO;
    AuthorizationExternalForm form;memcpy(&form,data.bytes,sizeof form);AuthorizationRef auth=NULL;
    OSStatus status=AuthorizationCreateFromExternalForm(&form,&auth);for(volatile unsigned char *b=(volatile unsigned char*)&form;b<(volatile unsigned char*)&form+sizeof form;b++)*b=0;if(status||!auth)return NO;
    AuthorizationItem item={NDCaptureRightName.UTF8String,0,NULL,0};AuthorizationRights requested={1,&item};AuthorizationRights *granted=NULL;
    status=AuthorizationCopyRights(auth,&requested,kAuthorizationEmptyEnvironment,kAuthorizationFlagDefaults,&granted);
    BOOL allowed=NO;if(!status&&granted)for(UInt32 i=0;i<granted->count;i++)if(granted->items[i].name&&!strcmp(granted->items[i].name,item.name))allowed=YES;
    if(granted)AuthorizationFreeItemSet(granted);AuthorizationFree(auth,kAuthorizationFlagDefaults);return allowed;
}
