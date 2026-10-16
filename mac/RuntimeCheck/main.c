/* Inspect the x86_64 userland slice before any system configuration changes. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <mach-o/loader.h>
#include <mach-o/fat.h>

_Static_assert(MH_MAGIC_64==0xfeedfacf && CPU_TYPE_X86_64==0x01000007, "Mach-O x86_64 header format");
_Static_assert(LC_BUILD_VERSION==0x32 && LC_VERSION_MIN_MACOSX==0x24 && PLATFORM_MACOS==1, "macOS version command format");
_Static_assert(FAT_MAGIC==0xcafebabe && FAT_MAGIC_64==0xcafebabf, "universal header format");

static uint32_t word(const unsigned char *p, int big) {
    return big ? ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]
               : ((uint32_t)p[3]<<24)|((uint32_t)p[2]<<16)|((uint32_t)p[1]<<8)|p[0];
}
static uint64_t wide(const unsigned char *p) { return ((uint64_t)word(p,1)<<32)|word(p+4,1); }
static int read_at(FILE *f, uint64_t offset, void *data, size_t size, uint64_t limit) {
    return offset <= limit && size <= limit-offset && offset <= INT64_MAX &&
           fseeko(f, (off_t)offset, SEEK_SET)==0 && fread(data,1,size,f)==size;
}
static int version(const char *text, uint32_t *result) {
    unsigned values[3]={0,0,0}, index=0;
    if (!text || !*text) return 0;
    for (const char *p=text; *p; p++) {
        if (*p=='.') {
            if (p==text || p[-1]=='.' || !p[1] || ++index>=3) return 0;
        } else {
            if (*p<'0'||*p>'9' || values[index]>65535) return 0;
            values[index]=values[index]*10+(unsigned)(*p-'0');
        }
    }
    if (values[0]>65535 || values[1]>255 || values[2]>255) return 0;
    *result=(values[0]<<16)|(values[1]<<8)|values[2]; return 1;
}
static int check(FILE *f, uint64_t size, uint32_t host) {
    unsigned char header[32]; uint64_t base=0, slice=size;
    if (!read_at(f,0,header,4,size)) return 3;
    uint32_t magic=word(header,1);
    if (magic==0xcafebabe || magic==0xcafebabf) {
        if (!read_at(f,0,header,8,size)) return 1;
        uint32_t count=word(header+4,1); unsigned entry=magic==0xcafebabf?32:20;
        if (!count || count>64) return 1;
        int found=0;
        for (uint32_t i=0;i<count;i++) {
            if (!read_at(f,8+(uint64_t)i*entry,header,entry,size)) return 1;
            if (word(header,1)!=0x01000007) continue;
            if (found++) return 1;
            base=entry==32?wide(header+8):word(header+8,1);
            slice=entry==32?wide(header+16):word(header+12,1);
        }
        if (!found || base>size || slice>size-base) return 1;
    } else if (magic==0xbebafeca || magic==0xbfbafeca) return 1;
    else if (magic!=0xcffaedfe && magic!=0xfeedfacf) {
        /* Other Mach-O architectures are not a runnable x86_64 payload. */
        if (magic==0xcefaedfe || magic==0xfeedface) return 1;
        return 3;
    }
    if (!read_at(f,base,header,32,size) || slice<32) return 1;
    int big=word(header,1)==0xfeedfacf;
    if (word(header,big)!=0xfeedfacf || word(header+4,big)!=0x01000007) return 1;
    uint32_t type=word(header+12,big), ncmds=word(header+16,big), bytes=word(header+20,big);
    if (type!=2 && type!=6 && type!=8) return 1;
    if (!ncmds || ncmds>4096 || bytes>16*1024*1024 || bytes>slice-32) return 1;
    uint64_t cursor=base+32, end=cursor+bytes; uint32_t minimum=0; int declared=0;
    for (uint32_t i=0;i<ncmds;i++) {
        if (!read_at(f,cursor,header,8,end)) return 1;
        uint32_t command=word(header,big), length=word(header+4,big);
        if (length<8 || length%8 || length>end-cursor) return 1;
        if (command==0x32 || command==0x24) {
            unsigned needed=command==0x32?24:16;
            if (length<needed || !read_at(f,cursor,header,needed,end)) return 1;
            if (command==0x32 && word(header+8,big)!=1) return 1;
            uint32_t v=word(header+(command==0x32?12:8),big);
            if (!v) return 1;
            if (v>minimum) minimum=v;
            declared=1;
        }
        cursor+=length;
    }
    if (cursor!=end || !declared) return 1;
    if (host<minimum) {
        fprintf(stderr,"STOP runtime payload requires macOS %u.%u.%u; this system is older\n",minimum>>16,(minimum>>8)&255,minimum&255);
        return 1;
    }
    printf("CHECK runtime payload minimum macOS %u.%u.%u\n",minimum>>16,(minimum>>8)&255,minimum&255);
    return 0;
}
int main(int argc, char **argv) {
    uint32_t host=0;
    if (argc!=3 || !version(argv[1],&host)) { fprintf(stderr,"STOP invalid runtime compatibility arguments\n"); return 1; }
    FILE *f=fopen(argv[2],"rb"); struct stat state;
    if (!f || fstat(fileno(f),&state) || !S_ISREG(state.st_mode) || state.st_size<0) {
        if (f) fclose(f); fprintf(stderr,"STOP cannot read runtime payload\n"); return 1;
    }
    int result=check(f,(uint64_t)state.st_size,host); fclose(f);
    if (result==1) fprintf(stderr,"STOP runtime compatibility was not established; no system files may be changed\n");
    return result;
}
