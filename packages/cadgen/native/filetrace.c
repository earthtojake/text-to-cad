/*
 * filetrace: the files a cadgen build opens, as the C library sees them.
 *
 * A model reads its data any way it likes: open(), numpy, build123d's
 * importers, an OCCT reader in C++, a font FreeType loads. Each of those ends
 * in the C library's open (kernel32's CreateFile on Windows). Installed once
 * in a process, this library points every loaded image's imported reference
 * to those functions, and those of every image loaded later, at a wrapper that
 * calls the real function. While a capture is open, each file a call opened
 * is appended to a log:
 *
 *     kind TAB size TAB mtime-ns TAB absolute-path NUL
 *
 * kind is 'r' for a regular file opened to read; 'u' for one opened to read
 * and write that keeps what it holds (r+, a+, a database); 'w' for a path
 * written (opened write-only or truncated, or renamed onto). size and mtime
 * are the open file's, so the reader can tell a file that changed after the
 * build opened it; a 'w' record carries -1 for both. 'x' is a file opened
 * whose path could not be written down. cadgen._internal.filetrace reads the
 * log back. Nothing is classified, hashed or allocated here.
 *
 * The rewiring is per image, not per process: calls made inside the operating
 * system's own libraries (the macOS shared cache, kernelbase) are not seen.
 * Every library a Python build loads is outside them.
 *
 * Built for each platform by zig (scripts/bundle/cadgen-runtime.sh) into
 * cadgen/_runtime/native.
 */

#define FILETRACE_VERSION 2

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define _GNU_SOURCE
#define EXPORT __attribute__((visibility("default")))
#endif

#include <stdio.h>
#include <string.h>

static volatile int capturing;
static _Thread_local int paused;  /* this thread is doing cadgen's own reading */

/* "kind\tsize\tmtime\t" then the absolute path, into rec; the record length
   including its NUL, or 0 when it does not fit. */
static int record(char *rec, int cap, char kind, long long size, long long mtime,
                  const char *dir, const char *path) {
    int n = snprintf(rec, (size_t)cap, "%c\t%lld\t%lld\t", kind, size, mtime);
    int m = dir ? snprintf(rec + n, (size_t)(cap - n), "%s/%s", dir, path)
                : snprintf(rec + n, (size_t)(cap - n), "%s", path);
    if (n <= 0 || m < 0 || n + m + 1 > cap) return 0;
    return n + m + 1;
}

#ifndef _WIN32 /* ------------------------------------------------------- POSIX */

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

static int log_fd = -1;

/* The folder a relative path is anchored on: the working directory, or dirfd's. */
static int anchor(int dirfd, char dir[PATH_MAX]) {
    if (dirfd == AT_FDCWD) return getcwd(dir, PATH_MAX) != NULL;
#ifdef __APPLE__
    return fcntl(dirfd, F_GETPATH, dir) != -1;
#else
    char link[64];
    snprintf(link, sizeof link, "/proc/self/fd/%d", dirfd);
    ssize_t len = readlink(link, dir, PATH_MAX - 1);
    if (len < 0) return 0;
    dir[len] = '\0';
    return 1;
#endif
}

/* A file this call opened (fd for a read); dirfd anchors a relative path. */
static void note(char kind, int fd, int dirfd, const char *path) {
    if (!capturing || paused || fd < 0 || !path) return;
    int saved = errno;
    long long size = -1, mtime = -1;
    if (kind != 'w') {
        struct stat st;
        if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode)) goto done;  /* a folder, a pipe, a device */
        size = (long long)st.st_size;
#ifdef __APPLE__
        mtime = (long long)st.st_mtimespec.tv_sec * 1000000000LL + st.st_mtimespec.tv_nsec;
#else
        mtime = (long long)st.st_mtim.tv_sec * 1000000000LL + st.st_mtim.tv_nsec;
#endif
    }
    char dir[PATH_MAX], rec[2 * PATH_MAX + 64];
    int n = 0;
    if (path[0] == '/') n = record(rec, sizeof rec, kind, size, mtime, NULL, path);
    else if (anchor(dirfd, dir)) n = record(rec, sizeof rec, kind, size, mtime, dir, path);
    if (!n) n = record(rec, sizeof rec, 'x', -1, -1, NULL, "");  /* opened, but not nameable */
    (void)!write(log_fd, rec, (size_t)n);
done:
    errno = saved;
}

/* fopen's mode: "w" and "a" only write, "r+" and "a+" read what is there too. */
static char mode_kind(const char *mode) {
    if (!mode) return 'r';
    if (mode[0] == 'w') return 'w';
    if (strchr(mode, '+')) return 'u';
    return mode[0] == 'a' ? 'w' : 'r';
}

/* open's flags: truncating or write-only writes; read-write (or creating)
   may read what is there. */
static char flags_kind(int flags) {
    if ((flags & O_TRUNC) || (flags & O_ACCMODE) == O_WRONLY) return 'w';
    if ((flags & O_ACCMODE) == O_RDWR || (flags & O_CREAT)) return 'u';
    return 'r';
}

static int flags_need_mode(int flags) {
#ifdef O_TMPFILE
    if ((flags & O_TMPFILE) == O_TMPFILE) return 1;
#endif
    return (flags & O_CREAT) != 0;
}

#define MODE_ARG(flags, last)                                   \
    mode_t mode = 0;                                            \
    if (flags_need_mode(flags)) {                               \
        va_list ap;                                             \
        va_start(ap, last);                                     \
        mode = (mode_t)va_arg(ap, int);                         \
        va_end(ap);                                             \
    }

typedef int (*open_fn)(const char *, int, ...);
typedef int (*openat_fn)(int, const char *, int, ...);
typedef int (*open2_fn)(const char *, int);
typedef int (*openat2_fn)(int, const char *, int);
typedef FILE *(*fopen_fn)(const char *, const char *);
typedef FILE *(*freopen_fn)(const char *, const char *, FILE *);
typedef int (*rename_fn)(const char *, const char *);
typedef int (*renameat_fn)(int, const char *, int, const char *);

/* One wrapper per real function: each knows its own original. */
#define OPEN_HOOK(name)                                                     \
    static open_fn real_##name;                                             \
    static int hook_##name(const char *path, int flags, ...) {              \
        MODE_ARG(flags, flags)                                              \
        int fd = real_##name(path, flags, mode);                            \
        note(flags_kind(flags), fd, AT_FDCWD, path);           \
        return fd;                                                          \
    }
#define OPENAT_HOOK(name)                                                   \
    static openat_fn real_##name;                                           \
    static int hook_##name(int dirfd, const char *path, int flags, ...) {   \
        MODE_ARG(flags, flags)                                              \
        int fd = real_##name(dirfd, path, flags, mode);                     \
        note(flags_kind(flags), fd, dirfd, path);              \
        return fd;                                                          \
    }
#define OPEN2_HOOK(name)                                                    \
    static open2_fn real_##name;                                            \
    static int hook_##name(const char *path, int flags) {                   \
        int fd = real_##name(path, flags);                                  \
        note(flags_kind(flags), fd, AT_FDCWD, path);           \
        return fd;                                                          \
    }
#define OPENAT2_HOOK(name)                                                  \
    static openat2_fn real_##name;                                          \
    static int hook_##name(int dirfd, const char *path, int flags) {        \
        int fd = real_##name(dirfd, path, flags);                           \
        note(flags_kind(flags), fd, dirfd, path);              \
        return fd;                                                          \
    }
#define FOPEN_HOOK(name)                                                    \
    static fopen_fn real_##name;                                            \
    static FILE *hook_##name(const char *path, const char *mode) {          \
        FILE *f = real_##name(path, mode);                                  \
        if (f) note(mode_kind(mode), fileno(f), AT_FDCWD, path); \
        return f;                                                           \
    }
#define FREOPEN_HOOK(name)                                                  \
    static freopen_fn real_##name;                                          \
    static FILE *hook_##name(const char *path, const char *mode, FILE *s) { \
        FILE *f = real_##name(path, mode, s);                               \
        if (f) note(mode_kind(mode), fileno(f), AT_FDCWD, path); \
        return f;                                                           \
    }

static rename_fn real_rename;
static int hook_rename(const char *from, const char *to) {
    int result = real_rename(from, to);
    if (result == 0) note('w', 0, AT_FDCWD, to);
    return result;
}

static renameat_fn real_renameat;
static int hook_renameat(int fromfd, const char *from, int tofd, const char *to) {
    int result = real_renameat(fromfd, from, tofd, to);
    if (result == 0) note('w', 0, tofd, to);
    return result;
}

OPEN_HOOK(open)
OPENAT_HOOK(openat)
FOPEN_HOOK(fopen)
FREOPEN_HOOK(freopen)

struct hook {
    const char *name;   /* the symbol as the image imports it */
    void *wrapper;
    void **real;
};

#ifdef __APPLE__ /* --------------------------------------------------- macOS */

#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach-o/nlist.h>
#include <mach/mach.h>

#ifndef MH_DYLIB_IN_CACHE
#define MH_DYLIB_IN_CACHE 0x80000000
#endif

FOPEN_HOOK(fopen_extsn)

#define HOOK(sym, fn) {"_" sym, (void *)hook_##fn, (void **)&real_##fn}
static struct hook hooks[] = {
    HOOK("open", open),
    HOOK("openat", openat),
    HOOK("fopen", fopen),
    HOOK("fopen$DARWIN_EXTSN", fopen_extsn),
    HOOK("freopen", freopen),
    HOOK("rename", rename),
    HOOK("renameat", renameat),
};

#else /* -------------------------------------------------------------- Linux */

#include <elf.h>
#include <link.h>
#include <sys/auxv.h>

OPEN_HOOK(open64)
OPENAT_HOOK(openat64)
OPEN2_HOOK(__open_2)
OPEN2_HOOK(__open64_2)
OPENAT2_HOOK(__openat_2)
OPENAT2_HOOK(__openat64_2)
FOPEN_HOOK(fopen64)
FREOPEN_HOOK(freopen64)

typedef int (*renameat2_fn)(int, const char *, int, const char *, unsigned int);
static renameat2_fn real_renameat2;
static int hook_renameat2(int fromfd, const char *from, int tofd, const char *to, unsigned int flags) {
    int result = real_renameat2(fromfd, from, tofd, to, flags);
    if (result == 0) note('w', 0, tofd, to);
    return result;
}

/* A library loaded later is rewired as it arrives: Python loads an extension
   module by its path. glibc resolves a bare name against its CALLER's search
   path, so that load is handed over by a tail call, leaving the caller in
   place; what it brought in is rewired at the next load or capture. */
static void rewire_all(void);
typedef void *(*dlopen_fn)(const char *, int);
static dlopen_fn real_dlopen;
static void *hook_dlopen(const char *file, int flags) {
    if (file && strchr(file, '/') && !strchr(file, '$')) {
        void *handle = real_dlopen(file, flags);
        if (handle) rewire_all();
        return handle;
    }
    __attribute__((musttail)) return real_dlopen(file, flags);
}

#define HOOK(sym, fn) {sym, (void *)hook_##fn, (void **)&real_##fn}
static struct hook hooks[] = {
    HOOK("open", open), HOOK("open64", open64),
    HOOK("openat", openat), HOOK("openat64", openat64),
    HOOK("__open_2", __open_2), HOOK("__open64_2", __open64_2),
    HOOK("__openat_2", __openat_2), HOOK("__openat64_2", __openat64_2),
    HOOK("fopen", fopen), HOOK("fopen64", fopen64),
    HOOK("freopen", freopen), HOOK("freopen64", freopen64),
    HOOK("rename", rename), HOOK("renameat", renameat), HOOK("renameat2", renameat2),
    HOOK("dlopen", dlopen),
};

#endif

#define HOOK_COUNT (sizeof hooks / sizeof hooks[0])

static void *wrapper_for(const char *name) {
    for (size_t i = 0; i < HOOK_COUNT; i++)
        if (*hooks[i].real && strcmp(hooks[i].name, name) == 0) return hooks[i].wrapper;
    return NULL;
}

/* Point one imported reference at its wrapper. The page is made writable for
   the write and given back as it was: read-only once relocated, or not. */
static void rewire(void **slot, void *wrapper, int read_only) {
    if (*slot == wrapper) return;
    uintptr_t page = (uintptr_t)slot & ~((uintptr_t)getpagesize() - 1);
    if (mprotect((void *)page, (size_t)getpagesize(), PROT_READ | PROT_WRITE) != 0) return;
    *slot = wrapper;
    if (read_only) mprotect((void *)page, (size_t)getpagesize(), PROT_READ);
}

static uintptr_t own_base;

#ifdef __APPLE__

static void rewire_image(const struct mach_header *header, intptr_t slide) {
    if ((uintptr_t)header == own_base || (header->flags & MH_DYLIB_IN_CACHE)) return;
    if (header->magic != MH_MAGIC_64) return;
    const struct mach_header_64 *mh = (const void *)header;
    const struct segment_command_64 *linkedit = NULL;
    const struct symtab_command *symtab = NULL;
    const struct dysymtab_command *dysymtab = NULL;
    const struct load_command *cmd = (const void *)(mh + 1);
    for (uint32_t i = 0; i < mh->ncmds; i++, cmd = (const void *)((const char *)cmd + cmd->cmdsize)) {
        if (cmd->cmd == LC_SEGMENT_64 && !strcmp(((const struct segment_command_64 *)cmd)->segname, SEG_LINKEDIT))
            linkedit = (const void *)cmd;
        else if (cmd->cmd == LC_SYMTAB) symtab = (const void *)cmd;
        else if (cmd->cmd == LC_DYSYMTAB) dysymtab = (const void *)cmd;
    }
    if (!linkedit || !symtab || !dysymtab || !dysymtab->nindirectsyms) return;
    uintptr_t base = (uintptr_t)slide + linkedit->vmaddr - linkedit->fileoff;
    const struct nlist_64 *syms = (const void *)(base + symtab->symoff);
    const char *strings = (const char *)(base + symtab->stroff);
    const uint32_t *indirect = (const uint32_t *)(base + dysymtab->indirectsymoff);
    cmd = (const void *)(mh + 1);
    for (uint32_t i = 0; i < mh->ncmds; i++, cmd = (const void *)((const char *)cmd + cmd->cmdsize)) {
        if (cmd->cmd != LC_SEGMENT_64) continue;
        const struct segment_command_64 *seg = (const void *)cmd;
        const struct section_64 *sect = (const void *)(seg + 1);
        int read_only = !(seg->initprot & VM_PROT_WRITE) || !strcmp(seg->segname, "__DATA_CONST")
                        || !strcmp(seg->segname, "__AUTH_CONST");
        for (uint32_t j = 0; j < seg->nsects; j++) {
            uint32_t type = sect[j].flags & SECTION_TYPE;
            if (type != S_LAZY_SYMBOL_POINTERS && type != S_NON_LAZY_SYMBOL_POINTERS) continue;
            void **slots = (void **)((uintptr_t)slide + sect[j].addr);
            const uint32_t *index = indirect + sect[j].reserved1;
            for (uint64_t k = 0; k < sect[j].size / sizeof(void *); k++) {
                uint32_t sym = index[k];
                if (sym & (INDIRECT_SYMBOL_ABS | INDIRECT_SYMBOL_LOCAL)) continue;
                void *wrapper = wrapper_for(strings + syms[sym].n_un.n_strx);
                if (wrapper) rewire(&slots[k], wrapper, read_only);
            }
        }
    }
}

static int install_images(void) {
    _dyld_register_func_for_add_image(rewire_image);  /* every image loaded so far, then each new one */
    return 1;
}

#else

#if defined(__x86_64__)
#define JUMP_SLOT R_X86_64_JUMP_SLOT
#define GLOB_DAT R_X86_64_GLOB_DAT
#elif defined(__aarch64__)
#define JUMP_SLOT R_AARCH64_JUMP_SLOT
#define GLOB_DAT R_AARCH64_GLOB_DAT
#else
#error "filetrace: unsupported Linux architecture"
#endif

static pthread_mutex_t rewiring = PTHREAD_MUTEX_INITIALIZER;

static void rewire_relocations(uintptr_t base, const ElfW(Rela) *rel, size_t size, const ElfW(Sym) *syms,
                               const char *strings, uintptr_t relro, uintptr_t relro_end) {
    if (!rel || !syms || !strings) return;
    for (size_t i = 0; i < size / sizeof *rel; i++) {
        unsigned long type = ELF64_R_TYPE(rel[i].r_info);
        if (type != JUMP_SLOT && type != GLOB_DAT) continue;
        void *wrapper = wrapper_for(strings + syms[ELF64_R_SYM(rel[i].r_info)].st_name);
        if (!wrapper) continue;
        uintptr_t slot = base + rel[i].r_offset;
        rewire((void **)slot, wrapper, slot >= relro && slot < relro_end);
    }
}

/* .dynamic holds addresses, already relocated by glibc and not by every loader. */
#define DYN_PTR(info, value) ((uintptr_t)(value) < (info)->dlpi_addr ? (info)->dlpi_addr + (uintptr_t)(value) : (uintptr_t)(value))

static int rewire_object(struct dl_phdr_info *info, size_t size, void *unused) {
    (void)size; (void)unused;
    if (info->dlpi_addr == own_base || info->dlpi_addr == getauxval(AT_BASE)
        || info->dlpi_addr == getauxval(AT_SYSINFO_EHDR))
        return 0;  /* this library, the dynamic loader, the vDSO */
    const ElfW(Dyn) *dyn = NULL;
    uintptr_t relro = 0, relro_end = 0;
    for (int i = 0; i < info->dlpi_phnum; i++) {
        const ElfW(Phdr) *ph = &info->dlpi_phdr[i];
        if (ph->p_type == PT_DYNAMIC) dyn = (const void *)(info->dlpi_addr + ph->p_vaddr);
        else if (ph->p_type == PT_GNU_RELRO) {
            /* The pages the loader made read-only, rounded as it rounds them: a
               partial last page is still writable, and must stay so. */
            uintptr_t page = ~((uintptr_t)getpagesize() - 1);
            relro = (info->dlpi_addr + ph->p_vaddr) & page;
            relro_end = (info->dlpi_addr + ph->p_vaddr + ph->p_memsz) & page;
        }
    }
    if (!dyn) return 0;
    const ElfW(Sym) *syms = NULL;
    const char *strings = NULL;
    const ElfW(Rela) *plt = NULL, *rela = NULL;
    size_t plt_size = 0, rela_size = 0;
    for (; dyn->d_tag != DT_NULL; dyn++) {
        switch (dyn->d_tag) {
        case DT_SYMTAB: syms = (const void *)DYN_PTR(info, dyn->d_un.d_ptr); break;
        case DT_STRTAB: strings = (const void *)DYN_PTR(info, dyn->d_un.d_ptr); break;
        case DT_JMPREL: plt = (const void *)DYN_PTR(info, dyn->d_un.d_ptr); break;
        case DT_PLTRELSZ: plt_size = dyn->d_un.d_val; break;
        case DT_RELA: rela = (const void *)DYN_PTR(info, dyn->d_un.d_ptr); break;
        case DT_RELASZ: rela_size = dyn->d_un.d_val; break;
        }
    }
    rewire_relocations(info->dlpi_addr, plt, plt_size, syms, strings, relro, relro_end);
    rewire_relocations(info->dlpi_addr, rela, rela_size, syms, strings, relro, relro_end);
    return 0;
}

static void rewire_all(void) {
    pthread_mutex_lock(&rewiring);
    dl_iterate_phdr(rewire_object, NULL);
    pthread_mutex_unlock(&rewiring);
}

static void rewiring_after_fork(void) { pthread_mutex_init(&rewiring, NULL); }

static int install_images(void) {
    pthread_atfork(NULL, NULL, rewiring_after_fork);
    rewire_all();
    return 1;
}

#endif

EXPORT int cadgen_filetrace_install(void) {
    static int installed;
    if (installed) return FILETRACE_VERSION;
    Dl_info self;
    if (!dladdr((void *)cadgen_filetrace_install, &self)) return 0;
    own_base = (uintptr_t)self.dli_fbase;
    for (size_t i = 0; i < HOOK_COUNT; i++) {
#ifdef __APPLE__
        *hooks[i].real = dlsym(RTLD_DEFAULT, hooks[i].name + 1);  /* the C name drops Mach-O's underscore */
#else
        *hooks[i].real = dlsym(RTLD_DEFAULT, hooks[i].name);
#endif
    }
    if (!real_open || !real_fopen) return 0;
    installed = install_images();
    return installed ? FILETRACE_VERSION : 0;
}

EXPORT int cadgen_filetrace_begin(const char *log_path) {
#ifndef __APPLE__
    rewire_all();  /* what a load by bare name brought in since the last load by path */
#endif
    int fd = open(log_path, O_WRONLY | O_APPEND | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    if (log_fd < 0) {
        log_fd = fd;  /* the log's descriptor number, held for the life of the process */
    } else {
        dup2(fd, log_fd);
        close(fd);
        fcntl(log_fd, F_SETFD, FD_CLOEXEC);
    }
    capturing = 1;
    return 0;
}

EXPORT void cadgen_filetrace_end(void) {
    capturing = 0;
    /* A wrapper already past its check may still write: it lands in /dev/null,
       never in whatever file would otherwise reuse a closed descriptor. */
    int null = open("/dev/null", O_WRONLY | O_CLOEXEC);
    if (null < 0 || log_fd < 0) return;
    dup2(null, log_fd);
    close(null);
    fcntl(log_fd, F_SETFD, FD_CLOEXEC);
}

#else /* ------------------------------------------------------------ Windows */

#include <windows.h>
#include <tlhelp32.h>

#define PATH_CHARS 4096

static HANDLE log_handle = INVALID_HANDLE_VALUE;
static SRWLOCK log_lock = SRWLOCK_INIT;

/* What os.stat reports as st_mtime_ns: FILETIME counts 100 ns from 1601. */
static long long unix_ns(FILETIME ft) {
    ULARGE_INTEGER t;
    t.LowPart = ft.dwLowDateTime;
    t.HighPart = ft.dwHighDateTime;
    return ((long long)t.QuadPart - 116444736000000000LL) * 100;
}

static void note(char kind, HANDLE handle, const wchar_t *path) {
    if (!capturing || paused || !path) return;
    DWORD saved = GetLastError();
    long long size = -1, mtime = -1;
    if (kind != 'w') {
        BY_HANDLE_FILE_INFORMATION info;
        if (GetFileType(handle) != FILE_TYPE_DISK || !GetFileInformationByHandle(handle, &info)
            || (info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY))
            goto done;
        size = ((long long)info.nFileSizeHigh << 32) | info.nFileSizeLow;
        mtime = unix_ns(info.ftLastWriteTime);
    }
    wchar_t full[PATH_CHARS];
    char rec[3 * PATH_CHARS + 64];
    int n = record(rec, sizeof rec, kind, size, mtime, NULL, "");
    DWORD len = GetFullPathNameW(path, PATH_CHARS, full, NULL);
    int m = len && len < PATH_CHARS
                ? WideCharToMultiByte(CP_UTF8, 0, full, -1, rec + n - 1, (int)sizeof rec - n + 1, NULL, NULL) : 0;
    if (m) n += m - 1;
    else n = record(rec, sizeof rec, 'x', -1, -1, NULL, "");  /* opened, but not nameable */
    AcquireSRWLockShared(&log_lock);
    DWORD written;
    if (capturing && log_handle != INVALID_HANDLE_VALUE) WriteFile(log_handle, rec, (DWORD)n, &written, NULL);
    ReleaseSRWLockShared(&log_lock);
done:
    SetLastError(saved);
}

#define WRITE_ACCESS (GENERIC_WRITE | GENERIC_ALL | FILE_WRITE_DATA | FILE_APPEND_DATA)
#define READ_ACCESS (GENERIC_READ | GENERIC_ALL | GENERIC_EXECUTE | FILE_READ_DATA | FILE_EXECUTE)

static void note_open(HANDLE handle, const wchar_t *path, DWORD access, DWORD disposition) {
    if (handle == INVALID_HANDLE_VALUE) return;
    if (disposition == CREATE_ALWAYS || disposition == CREATE_NEW || disposition == TRUNCATE_EXISTING)
        note('w', handle, path);
    else if (access & WRITE_ACCESS)
        note(access & READ_ACCESS ? 'u' : 'w', handle, path);
    else if (access & READ_ACCESS)
        note('r', handle, path);  /* metadata-only opens (what os.stat does) read nothing */
}

typedef HANDLE(WINAPI *CreateFileW_fn)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HANDLE(WINAPI *CreateFileA_fn)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HANDLE(WINAPI *CreateFile2_fn)(LPCWSTR, DWORD, DWORD, DWORD, void *);
typedef BOOL(WINAPI *MoveFileExW_fn)(LPCWSTR, LPCWSTR, DWORD);
typedef BOOL(WINAPI *MoveFileW_fn)(LPCWSTR, LPCWSTR);
typedef HMODULE(WINAPI *LoadLibraryExW_fn)(LPCWSTR, HANDLE, DWORD);
typedef HMODULE(WINAPI *LoadLibraryExA_fn)(LPCSTR, HANDLE, DWORD);
typedef HMODULE(WINAPI *LoadLibraryW_fn)(LPCWSTR);
typedef HMODULE(WINAPI *LoadLibraryA_fn)(LPCSTR);

static CreateFileW_fn real_CreateFileW;
static CreateFileA_fn real_CreateFileA;
static CreateFile2_fn real_CreateFile2;
static MoveFileExW_fn real_MoveFileExW;
static MoveFileW_fn real_MoveFileW;
static LoadLibraryExW_fn real_LoadLibraryExW;
static LoadLibraryExA_fn real_LoadLibraryExA;
static LoadLibraryW_fn real_LoadLibraryW;
static LoadLibraryA_fn real_LoadLibraryA;

static HANDLE WINAPI hook_CreateFileW(LPCWSTR path, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES security,
                                      DWORD disposition, DWORD flags, HANDLE template_file) {
    HANDLE handle = real_CreateFileW(path, access, share, security, disposition, flags, template_file);
    note_open(handle, path, access, disposition);
    return handle;
}

static HANDLE WINAPI hook_CreateFileA(LPCSTR path, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES security,
                                      DWORD disposition, DWORD flags, HANDLE template_file) {
    HANDLE handle = real_CreateFileA(path, access, share, security, disposition, flags, template_file);
    wchar_t wide[PATH_CHARS];
    if (handle != INVALID_HANDLE_VALUE && capturing && path) {
        if (!MultiByteToWideChar(CP_ACP, 0, path, -1, wide, PATH_CHARS)) wide[0] = L'\0';
        note_open(handle, wide, access, disposition);
    }
    return handle;
}

static HANDLE WINAPI hook_CreateFile2(LPCWSTR path, DWORD access, DWORD share, DWORD disposition, void *params) {
    HANDLE handle = real_CreateFile2(path, access, share, disposition, params);
    note_open(handle, path, access, disposition);
    return handle;
}

static BOOL WINAPI hook_MoveFileExW(LPCWSTR from, LPCWSTR to, DWORD flags) {
    BOOL moved = real_MoveFileExW(from, to, flags);
    if (moved) note('w', INVALID_HANDLE_VALUE, to);
    return moved;
}

static BOOL WINAPI hook_MoveFileW(LPCWSTR from, LPCWSTR to) {
    BOOL moved = real_MoveFileW(from, to);
    if (moved) note('w', INVALID_HANDLE_VALUE, to);
    return moved;
}

/* A module loaded later is rewired as it arrives, with what it brought in. */
static void rewire_all(void);

static HMODULE WINAPI hook_LoadLibraryExW(LPCWSTR name, HANDLE file, DWORD flags) {
    HMODULE module = real_LoadLibraryExW(name, file, flags);
    if (module) rewire_all();
    return module;
}

static HMODULE WINAPI hook_LoadLibraryExA(LPCSTR name, HANDLE file, DWORD flags) {
    HMODULE module = real_LoadLibraryExA(name, file, flags);
    if (module) rewire_all();
    return module;
}

static HMODULE WINAPI hook_LoadLibraryW(LPCWSTR name) {
    HMODULE module = real_LoadLibraryW(name);
    if (module) rewire_all();
    return module;
}

static HMODULE WINAPI hook_LoadLibraryA(LPCSTR name) {
    HMODULE module = real_LoadLibraryA(name);
    if (module) rewire_all();
    return module;
}

struct hook {
    const char *name;
    void *wrapper;
    void **real;
};

#define HOOK(fn) {#fn, (void *)hook_##fn, (void **)&real_##fn}
static struct hook hooks[] = {
    HOOK(CreateFileW), HOOK(CreateFileA), HOOK(CreateFile2),
    HOOK(MoveFileExW), HOOK(MoveFileW),
    HOOK(LoadLibraryExW), HOOK(LoadLibraryExA), HOOK(LoadLibraryW), HOOK(LoadLibraryA),
};
#define HOOK_COUNT (sizeof hooks / sizeof hooks[0])

static HMODULE own_module, kernel32, kernelbase, ntdll;
static SRWLOCK rewiring = SRWLOCK_INIT;

static void rewire_module(HMODULE module) {
    if (module == own_module || module == kernel32 || module == kernelbase || module == ntdll) return;
    BYTE *base = (BYTE *)module;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return;
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return;
    for (IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); imp->Name; imp++) {
        if (!imp->OriginalFirstThunk) continue;  /* no name table: nothing to match by name */
        IMAGE_THUNK_DATA *names = (IMAGE_THUNK_DATA *)(base + imp->OriginalFirstThunk);
        IMAGE_THUNK_DATA *slots = (IMAGE_THUNK_DATA *)(base + imp->FirstThunk);
        for (; names->u1.AddressOfData; names++, slots++) {
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
            const char *name = (const char *)((IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData))->Name;
            for (size_t i = 0; i < HOOK_COUNT; i++) {
                if (!*hooks[i].real || strcmp(hooks[i].name, name) != 0) continue;
                if ((void *)slots->u1.Function == hooks[i].wrapper) break;
                DWORD old;
                if (VirtualProtect(&slots->u1.Function, sizeof(void *), PAGE_READWRITE, &old)) {
                    slots->u1.Function = (ULONG_PTR)hooks[i].wrapper;
                    VirtualProtect(&slots->u1.Function, sizeof(void *), old, &old);
                }
                break;
            }
        }
    }
}

/* The modules are listed before the lock is taken: listing takes the loader's
   own lock, which a library's DllMain may hold while it loads another. The lock
   keeps two threads from unprotecting and re-protecting one page at once. */
static void rewire_all(void) {
    HMODULE modules[2048];
    int count = 0;
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return;
    MODULEENTRY32W entry;
    entry.dwSize = sizeof entry;
    for (BOOL more = Module32FirstW(snapshot, &entry); more && count < 2048; more = Module32NextW(snapshot, &entry))
        modules[count++] = entry.hModule;
    CloseHandle(snapshot);
    AcquireSRWLockExclusive(&rewiring);
    for (int i = 0; i < count; i++) rewire_module(modules[i]);
    ReleaseSRWLockExclusive(&rewiring);
}

EXPORT int cadgen_filetrace_install(void) {
    static int installed;
    if (installed) return FILETRACE_VERSION;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCWSTR)(void *)cadgen_filetrace_install, &own_module))
        return 0;
    kernel32 = GetModuleHandleW(L"kernel32.dll");
    kernelbase = GetModuleHandleW(L"kernelbase.dll");
    ntdll = GetModuleHandleW(L"ntdll.dll");
    for (size_t i = 0; i < HOOK_COUNT; i++) {
        FARPROC real = kernelbase ? GetProcAddress(kernelbase, hooks[i].name) : NULL;
        if (!real && kernel32) real = GetProcAddress(kernel32, hooks[i].name);
        *hooks[i].real = (void *)real;
    }
    if (!real_CreateFileW) return 0;
    rewire_all();
    installed = 1;
    return FILETRACE_VERSION;
}

EXPORT int cadgen_filetrace_begin(const char *log_path) {
    rewire_all();  /* a module loaded where no rewired LoadLibrary saw it */
    wchar_t path[32768];
    if (!MultiByteToWideChar(CP_UTF8, 0, log_path, -1, path, 32768)) return -1;
    HANDLE handle = real_CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                     NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle == INVALID_HANDLE_VALUE) return -1;
    AcquireSRWLockExclusive(&log_lock);
    log_handle = handle;
    capturing = 1;
    ReleaseSRWLockExclusive(&log_lock);
    return 0;
}

EXPORT void cadgen_filetrace_end(void) {
    AcquireSRWLockExclusive(&log_lock);  /* no wrapper is mid-write once this is held */
    capturing = 0;
    if (log_handle != INVALID_HANDLE_VALUE) CloseHandle(log_handle);
    log_handle = INVALID_HANDLE_VALUE;
    ReleaseSRWLockExclusive(&log_lock);
}

#endif

/* cadgen's own reading on this thread (the gate hashing a child's files) is
   not the build's: a child is an input by its result. Nests. */
EXPORT void cadgen_filetrace_pause(int on) {
    paused += on ? 1 : -1;
}
