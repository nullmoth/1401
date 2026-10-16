#import "NDBoundedProcess.h"
#include <spawn.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
static double nd_now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
NSDictionary *NDExecuteBounded(NSString *exe,NSArray<NSString*> *args,NSTimeInterval seconds,NSUInteger limit,NDCancelCheck cancel,NDIdentityCheck identity){
    if(!exe.isAbsolutePath || seconds<=0 || seconds>18 || !limit || limit>65536 || args.count>16)return @{@"status":@"invalid_process_request"};
    if(cancel&&cancel())return @{@"status":@"cancelled",@"childLaunched":@NO,@"childReaped":@YES};
    if(identity&&!identity())return @{@"status":@"target_changed",@"childLaunched":@NO,@"childReaped":@YES};
    int fd[2];if(pipe(fd))return @{@"status":@"pipe_failure"};fcntl(fd[0],F_SETFL,O_NONBLOCK);fcntl(fd[0],F_SETFD,FD_CLOEXEC);fcntl(fd[1],F_SETFD,FD_CLOEXEC);
    posix_spawn_file_actions_t actions;posix_spawn_file_actions_init(&actions);posix_spawn_file_actions_addopen(&actions,STDIN_FILENO,"/dev/null",O_RDONLY,0);posix_spawn_file_actions_adddup2(&actions,fd[1],STDOUT_FILENO);posix_spawn_file_actions_adddup2(&actions,fd[1],STDERR_FILENO);posix_spawn_file_actions_addclose(&actions,fd[0]);posix_spawn_file_actions_addclose(&actions,fd[1]);
    posix_spawnattr_t attr;posix_spawnattr_init(&attr);sigset_t defaults,mask;sigemptyset(&defaults);sigaddset(&defaults,SIGINT);sigaddset(&defaults,SIGTERM);sigaddset(&defaults,SIGPIPE);sigemptyset(&mask);posix_spawnattr_setsigdefault(&attr,&defaults);posix_spawnattr_setsigmask(&attr,&mask);posix_spawnattr_setflags(&attr,POSIX_SPAWN_SETPGROUP|POSIX_SPAWN_CLOEXEC_DEFAULT|POSIX_SPAWN_SETSIGDEF|POSIX_SPAWN_SETSIGMASK);posix_spawnattr_setpgroup(&attr,0);
    char **argv=calloc(args.count+2,sizeof(char*));argv[0]=(char*)exe.fileSystemRepresentation;for(NSUInteger i=0;i<args.count;i++)argv[i+1]=(char*)args[i].UTF8String;
    char *environment[]={"PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=C","LC_ALL=C",NULL};
    pid_t child=0;int spawn=posix_spawn(&child,exe.fileSystemRepresentation,&actions,&attr,argv,environment);
    free(argv);posix_spawnattr_destroy(&attr);posix_spawn_file_actions_destroy(&actions);close(fd[1]);
    if(spawn){close(fd[0]);return @{@"status":@"launch_failure",@"launchErrno":@(spawn)};}
    NSMutableData *bytes=[NSMutableData new];NSString *reason=nil;BOOL reaped=NO,verifiedReaped=NO,eof=NO;int status=0;double deadline=nd_now()+seconds,stopped=0;
    while(!reaped || !eof){
        if(!reason){if(cancel&&cancel())reason=@"cancelled";else if(identity&&!identity())reason=@"target_changed";else if(nd_now()>=deadline)reason=@"timeout";}
        if(reason&&!stopped){stopped=nd_now();if(!reaped){if(getpgid(child)==child)kill(-child,SIGINT);else kill(child,SIGINT);}}
        if(reason&&!reaped&&nd_now()-stopped>=0.5){if(getpgid(child)==child)kill(-child,SIGKILL);else kill(child,SIGKILL);}
        uint8_t chunk[4096];ssize_t n=0;unsigned drained=0;
        while(drained++<16&&(n=read(fd[0],chunk,sizeof chunk))>0){NSUInteger remaining=limit-bytes.length;[bytes appendBytes:chunk length:MIN((NSUInteger)n,remaining)];if((NSUInteger)n>remaining&&!reason)reason=@"output_limit";}
        if(n==0)eof=YES;else if(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR){reason=reason?:@"read_failure";eof=YES;}
        if(!reaped){pid_t done=waitpid(child,&status,WNOHANG);if(done==child){reaped=YES;verifiedReaped=YES;}else if(done<0&&errno!=EINTR){reason=reason?:@"wait_failure";reaped=YES;}}
        if(reaped&&(!eof)&&nd_now()>=deadline+1){reason=reason?:@"pipe_cleanup_timeout";break;}
        if(!reaped || !eof){struct pollfd p={fd[0],POLLIN,0};poll(&p,1,25);}
    }
    close(fd[0]);if(!reaped){kill(child,SIGKILL);pid_t done;do{done=waitpid(child,&status,0);}while(done<0&&errno==EINTR);verifiedReaped=done==child;}
    return @{@"status":reason?:((WIFEXITED(status)&&WEXITSTATUS(status)==0)?@"completed":@"process_failed"),@"exitCode":@(WIFEXITED(status)?WEXITSTATUS(status):-1),@"signal":@(WIFSIGNALED(status)?WTERMSIG(status):0),@"capturedBytes":@(bytes.length),@"output":bytes,@"childLaunched":@YES,@"childReaped":@(verifiedReaped)};
}
NSDictionary *NDParseTrace(NSDictionary *process){
    NSString *text=[[NSString alloc]initWithData:process[@"output"] encoding:NSUTF8StringEncoding];BOOL start=NO,end=NO,dataLoss=NO;uint64_t samples=0,errors=0;BOOL valid=text!=nil;
    for(NSString *line in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]){
        if([line isEqual:@"ND_START"]){if(start)valid=NO;start=YES;}else if([line isEqual:@"ND_END"]){if(end)valid=NO;end=YES;}
        else if([line hasPrefix:@"ND_SAMPLES "]||[line hasPrefix:@"ND_ERRORS "]){NSString *value=[line componentsSeparatedByString:@" "].lastObject;NSScanner *scanner=[NSScanner scannerWithString:value];unsigned long long number=0;if(!value.length||[value rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789"] invertedSet]].location!=NSNotFound||![scanner scanUnsignedLongLong:&number]||!scanner.isAtEnd||number>100000)valid=NO;else if([line hasPrefix:@"ND_SAMPLES "])samples=number;else errors=number;}
        if([line.lowercaseString hasPrefix:@"dtrace:"]&&([line.lowercaseString containsString:@"drop"]||[line.lowercaseString containsString:@"error"]||[line.lowercaseString containsString:@"failed"]||[line.lowercaseString containsString:@"denied"]))dataLoss=YES;
    }
    NSString *status=process[@"status"]?:@"unknown";BOOL complete=[status isEqual:@"completed"]&&valid&&start&&end&&!errors&&!dataLoss;
    return @{@"status":complete?(samples?@"captured":@"inconclusive_no_samples"):@"trace_incomplete",@"complete":@(complete),@"samples":@(samples),@"errors":@(errors),@"dataLossOrToolFailure":@(dataLoss),@"started":@(start),@"ended":@(end),@"transportStatus":status,@"exitCode":process[@"exitCode"]?:@-1,@"capturedBytes":process[@"capturedBytes"]?:@0,@"childReaped":process[@"childReaped"]?:@NO};
}
