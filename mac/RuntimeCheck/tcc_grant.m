// Copyright (c) 2026 NullMoth Systems.
// nullmoth-tcc-grant <app path>: lets one app use the microphone, camera and screen recording.
//
// The driver's boot arguments relax AMFI (amfi_get_out_of_my_way), and with AMFI relaxed macOS never shows the
// "allow microphone" prompt: Discord, games and recorders get silence and never appear under Privacy & Security.
// This asks tccd for the grant the prompt would have recorded, through Apple's own TCC framework
// (TCCAccessSetForBundle), never by editing TCC.db. The method follows tccplus (MIT, Copyright (c) 2020 Jeremy
// Legendre; see NOTICE.md). The private entitlement it needs is honoured only while AMFI is relaxed, which is
// exactly when the prompt is missing. Prints one JSON line: {"ok":bool,"bundle":id,"granted":[...],"failed":[...]}.
#import <Foundation/Foundation.h>
#import <dlfcn.h>

typedef Boolean (*TCCSet)(CFStringRef service, CFBundleRef bundle, Boolean granted);

static void emit(NSDictionary *d)
{
    NSData *j = [NSJSONSerialization dataWithJSONObject:d options:0 error:nil];
    fwrite(j.bytes, 1, j.length, stdout); fputc('\n', stdout);
}

int main(int argc, const char *argv[])
{
    @autoreleasepool {
        if (argc != 2) { emit(@{@"ok": @NO, @"why": @"usage: nullmoth-tcc-grant <app path>"}); return 2; }
        NSURL *url = [NSURL fileURLWithPath:@(argv[1]) isDirectory:YES];
        CFBundleRef b = CFBundleCreate(NULL, (__bridge CFURLRef)url);
        NSString *bid = b ? (__bridge NSString *)CFBundleGetIdentifier(b) : nil;
        if (!b || !bid.length) { if (b) CFRelease(b); emit(@{@"ok": @NO, @"why": @"not an app bundle with an identifier"}); return 1; }
        void *h = dlopen("/System/Library/PrivateFrameworks/TCC.framework/Versions/A/TCC", RTLD_LAZY);
        TCCSet set = h ? (TCCSet)dlsym(h, "TCCAccessSetForBundle") : NULL;
        if (!set) { CFRelease(b); emit(@{@"ok": @NO, @"bundle": bid, @"why": @"TCCAccessSetForBundle not found in this macOS"}); return 1; }
        NSMutableArray *granted = [NSMutableArray array], *failed = [NSMutableArray array];
        for (NSString *s in @[@"kTCCServiceMicrophone", @"kTCCServiceCamera", @"kTCCServiceScreenCapture"]) {
            if (set((__bridge CFStringRef)s, b, true)) [granted addObject:s]; else [failed addObject:s];
        }
        CFRelease(b);
        emit(@{@"ok": @(granted.count > 0), @"bundle": bid, @"granted": granted, @"failed": failed});
        return granted.count > 0 ? 0 : 1;
    }
}
