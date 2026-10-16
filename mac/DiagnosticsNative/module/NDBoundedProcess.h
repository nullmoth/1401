#import <Foundation/Foundation.h>
/* Internal transport primitive. Production callers supply only /usr/sbin/dtrace
   and the built-in script; the app must never expose executable/argument input. */
typedef BOOL (^NDCancelCheck)(void);
typedef BOOL (^NDIdentityCheck)(void);
NSDictionary *NDExecuteBounded(NSString *executable,NSArray<NSString*> *arguments,
    NSTimeInterval seconds,NSUInteger byteLimit,NDCancelCheck cancelled,NDIdentityCheck identity);
NSDictionary *NDParseTrace(NSDictionary *process);
