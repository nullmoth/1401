#import <Foundation/Foundation.h>
#import "NDBoundedProcess.h"
/* Both blocks belong to the authenticated local helper implementation.
   They are not booleans or executable callbacks accepted from an app request. */
typedef BOOL (^NDConsumeLocalConsent)(NSDictionary *currentReceipt);
NSDictionary *NDParseProviderInventory(NSDictionary *process);
NSDictionary *NDPrerequisites(pid_t target,uid_t localClient,NSTimeInterval providerBudget);
NSDictionary *NDRunApprovedSession(pid_t target,uid_t authenticatedLocalClient,unsigned seconds,
    NDConsumeLocalConsent consumeFreshConsent,NDCancelCheck cancelled);
