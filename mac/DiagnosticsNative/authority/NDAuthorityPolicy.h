#import <Foundation/Foundation.h>
@interface NDAuthorityPolicy : NSObject
@property(readonly) NSDictionary *receipt;
@property(readonly) NSString *appRequirement;
@property(readonly) NSString *helperRequirement;
+ (instancetype)parse:(NSData *)data error:(NSString **)error;
+ (instancetype)loadInstalled:(NSString **)error;
- (BOOL)verifyAppAndHelperFiles:(NSString **)error;
@end
BOOL NDAdministratorFormIsGranted(NSData *form);
BOOL NDTraceSigningFlagsAllow(uint32_t flags,NSDictionary *entitlements);
