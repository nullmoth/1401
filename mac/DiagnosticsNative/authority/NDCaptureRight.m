#import "NDCaptureRight.h"
#import <Security/AuthorizationDB.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
NSString *const NDCaptureRightName=@"com.nullmoth.1401.diagnostics.capture";
NSDictionary *NDCaptureRightDefinition(void){return @{@"class":@"user",@"group":@"admin",@"authenticate-user":@YES,@"shared":@NO,@"allow-root":@NO,@"session-owner":@NO,@"timeout":@45,@"tries":@1,@"comment":@"Authorize one bounded local count-only diagnostics session"};}
NSDictionary *NDCaptureRightRead(NSString **error){if(error)*error=nil;CFDictionaryRef definition=NULL;OSStatus status=AuthorizationRightGet(NDCaptureRightName.UTF8String,&definition);if(status==errAuthorizationDenied)return nil;if(status){if(error)*error=@"dedicated_authorization_policy_unavailable";return nil;}return CFBridgingRelease(definition);}
BOOL NDCaptureRightConfigured(void){
    NSString *path=@"/Library/Application Support/NullMoth/Diagnostics/right-policy.json";struct stat s;if(lstat(path.fileSystemRepresentation,&s)||!S_ISREG(s.st_mode)||s.st_uid!=0||(s.st_mode&0022)||s.st_size<=0||s.st_size>65536)return NO;
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return NO;NSMutableData *data=[NSMutableData dataWithLength:(NSUInteger)s.st_size];ssize_t n=read(fd,data.mutableBytes,data.length);close(fd);if(n!=(ssize_t)data.length)return NO;
    NSDictionary *receipt=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];NSDictionary *installed=receipt[@"installedDefinition"];
    if(![receipt[@"scope"]isEqual:@"nullmoth-diagnostics-right-v1"]||![receipt[@"rightName"]isEqual:NDCaptureRightName]||![installed isKindOfClass:NSDictionary.class])return NO;
    NSDictionary *required=NDCaptureRightDefinition();for(NSString *key in required)if(![installed[key]isEqual:required[key]])return NO;
    return [NDCaptureRightRead(nil)isEqual:installed];
}
