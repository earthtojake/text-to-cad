// wasi_only.cpp: what OCCT's linked code reaches for that WASI has no call for, answered here so the module imports
// WASI alone. None is on the core's path (it reads and writes memory, never files): each answers "not supported".
#include <emscripten/emscripten.h>
#include <emscripten/syscalls.h>

#include <cerrno>
#include <netdb.h>

extern "C" {

// OSD_File, OSD_Directory (file permissions, access checks, directory listing).
int __syscall_faccessat(int, const char*, int, int) { return -ENOSYS; }
int __syscall_chmod(const char*, mode_t) { return -ENOSYS; }
int __syscall_getdents64(int, void*, size_t) { return -ENOSYS; }

// Image_AlienPixMap (a browser's preloaded image) and Standard_StackTrace (a JavaScript call stack).
char* emscripten_get_preloaded_image_data(const char*, int*, int*) { return nullptr; }
int emscripten_get_callstack(int, char*, int) { return 0; }

// OSD_Host (the machine's address, which the STEP writer's header never asks for here).
int getaddrinfo(const char*, const char*, const struct addrinfo*, struct addrinfo**) { return EAI_FAIL; }

}
