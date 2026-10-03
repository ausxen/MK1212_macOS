#include <atomic>
#include <cstdarg>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <pthread.h>
#include <sched.h>
#include <time.h>
#include <unistd.h>

/* Heap-only ten-slot proof for Feral ATTILA 1.6.1 build 480285.103778. */

static const uint8_t kUuid[16] = {
    0x39, 0x2d, 0x6f, 0x66, 0x91, 0x83, 0x32, 0x9e,
    0x8a, 0x98, 0x8c, 0x90, 0xfc, 0x82, 0x83, 0x26,
};
static const uint8_t kContext[12] = {
    0x08, 0xc0, 0x01, 0x39, 0xc8, 0x00, 0x80, 0x52,
    0x08, 0x74, 0x00, 0xb9,
};
static constexpr uintptr_t kSite1 = 0x03457244;
static constexpr uintptr_t kSite2 = 0x034577f4;
static constexpr uintptr_t kCallbackNewReturn = 0x034aaca4;
static constexpr uintptr_t kPrimaryVptr = 0x04c99c08;
static constexpr uintptr_t kSecondaryVptr = 0x04c99df8;
static constexpr size_t kAllocationSize = 160;
static constexpr size_t kSecondaryOffset = 0x48;
static constexpr size_t kCountOffset = 0x74;
static constexpr size_t kMaxCandidates = 64;

static const struct mach_header_64 *gHeader = nullptr;
static uintptr_t gPrimary = 0;
static uintptr_t gSecondary = 0;
static uintptr_t gPage = 0;
static size_t gPageSize = 0;
static uint64_t gPageHash = 0;
static int gLog = -1;
static std::atomic<uintptr_t> gCandidates[kMaxCandidates];
static std::atomic<uintptr_t> gHazards[kMaxCandidates];
static std::atomic<uint64_t> gMatchedAllocations{0};
static std::atomic<uint64_t> gDroppedAllocations{0};
static std::atomic<uint64_t> gPatchedCallbacks{0};

extern "C" void *_Znwm(size_t);
extern "C" void _ZdlPv(void *);
extern "C" void _ZdlPvm(void *, size_t);

#define INTERPOSE_NAMED(name, replacement, replacee)                            \
    __attribute__((used)) static struct {                                       \
        const void *replacement;                                                \
        const void *replacee;                                                   \
    } name __attribute__((section("__DATA,__interpose"))) = {                  \
        reinterpret_cast<const void *>(reinterpret_cast<uintptr_t>(&replacement)), \
        reinterpret_cast<const void *>(reinterpret_cast<uintptr_t>(&replacee))     \
    }

static void log_line(const char *format, ...) {
    if (gLog < 0) return;
    struct timespec now{};
    clock_gettime(CLOCK_REALTIME, &now);
    dprintf(gLog, "%lld.%09ld ", static_cast<long long>(now.tv_sec), now.tv_nsec);
    va_list arguments;
    va_start(arguments, format);
    vdprintf(gLog, format, arguments);
    va_end(arguments);
    fsync(gLog);
}

static uint64_t hash_page(const uint8_t *bytes, size_t length) {
    uint64_t value = 1469598103934665603ULL;
    for (size_t index = 0; index < length; ++index) {
        value ^= bytes[index];
        value *= 1099511628211ULL;
    }
    return value;
}

static const struct mach_header_64 *main_executable() {
    for (uint32_t index = 0; index < _dyld_image_count(); ++index) {
        const struct mach_header *candidate = _dyld_get_image_header(index);
        if (candidate && candidate->magic == MH_MAGIC_64 && candidate->filetype == MH_EXECUTE)
            return reinterpret_cast<const struct mach_header_64 *>(candidate);
    }
    return nullptr;
}

static bool uuid_matches(const struct mach_header_64 *header) {
    const uint8_t *cursor = reinterpret_cast<const uint8_t *>(header + 1);
    for (uint32_t index = 0; index < header->ncmds; ++index) {
        const auto *command = reinterpret_cast<const struct load_command *>(cursor);
        if (command->cmdsize < sizeof(*command)) return false;
        if (command->cmd == LC_UUID && command->cmdsize >= sizeof(struct uuid_command)) {
            const auto *uuid = reinterpret_cast<const struct uuid_command *>(command);
            return memcmp(uuid->uuid, kUuid, sizeof(kUuid)) == 0;
        }
        cursor += command->cmdsize;
    }
    return false;
}

static void *tracked_new(size_t size) {
    void *pointer = malloc(size);
    if (!pointer) abort();
    if (size == kAllocationSize && gHeader) {
        uintptr_t returned_to = reinterpret_cast<uintptr_t>(__builtin_return_address(0));
        if (returned_to == reinterpret_cast<uintptr_t>(gHeader) + kCallbackNewReturn) {
            bool inserted = false;
            for (size_t index = 0; index < kMaxCandidates; ++index) {
                uintptr_t empty = 0;
                if (gCandidates[index].compare_exchange_strong(
                        empty, reinterpret_cast<uintptr_t>(pointer), std::memory_order_acq_rel)) {
                    gMatchedAllocations.fetch_add(1, std::memory_order_relaxed);
                    inserted = true;
                    break;
                }
            }
            if (!inserted) gDroppedAllocations.fetch_add(1, std::memory_order_relaxed);
        }
    }
    return pointer;
}

static void retire_candidate(void *pointer) {
    uintptr_t target = reinterpret_cast<uintptr_t>(pointer);
    for (size_t index = 0; index < kMaxCandidates; ++index) {
        uintptr_t value = target;
        if (gCandidates[index].compare_exchange_strong(value, 0, std::memory_order_acq_rel)) {
            while (gHazards[index].load(std::memory_order_acquire) == target) sched_yield();
            break;
        }
    }
}

static void tracked_delete(void *pointer) {
    if (pointer) retire_candidate(pointer);
    free(pointer);
}

static void tracked_sized_delete(void *pointer, size_t size) {
    (void)size;
    tracked_delete(pointer);
}

INTERPOSE_NAMED(gNewInterpose, tracked_new, _Znwm);
INTERPOSE_NAMED(gDeleteInterpose, tracked_delete, _ZdlPv);
INTERPOSE_NAMED(gSizedDeleteInterpose, tracked_sized_delete, _ZdlPvm);

static void *monitor(void *) {
    uint64_t last_matches = 0;
    uint64_t last_drops = 0;
    uint64_t last_patches = 0;
    uintptr_t last_pointer[kMaxCandidates] = {};
    uintptr_t last_primary[kMaxCandidates];
    uintptr_t last_secondary[kMaxCandidates];
    uint32_t last_count[kMaxCandidates];
    for (size_t index = 0; index < kMaxCandidates; ++index) {
        last_primary[index] = UINTPTR_MAX;
        last_secondary[index] = UINTPTR_MAX;
        last_count[index] = UINT32_MAX;
    }
    for (;;) {
        bool any = false;
        for (size_t index = 0; index < kMaxCandidates; ++index) {
            uintptr_t pointer = gCandidates[index].load(std::memory_order_acquire);
            if (!pointer) {
                last_pointer[index] = 0;
                last_primary[index] = UINTPTR_MAX;
                last_secondary[index] = UINTPTR_MAX;
                last_count[index] = UINT32_MAX;
                continue;
            }
            any = true;
            gHazards[index].store(pointer, std::memory_order_release);
            if (gCandidates[index].load(std::memory_order_acquire) != pointer) {
                gHazards[index].store(0, std::memory_order_release);
                continue;
            }
            uintptr_t primary = __atomic_load_n(reinterpret_cast<uintptr_t *>(pointer), __ATOMIC_ACQUIRE);
            uintptr_t secondary = __atomic_load_n(
                reinterpret_cast<uintptr_t *>(pointer + kSecondaryOffset), __ATOMIC_ACQUIRE);
            uint32_t count = __atomic_load_n(
                reinterpret_cast<uint32_t *>(pointer + kCountOffset), __ATOMIC_ACQUIRE);
            if (pointer != last_pointer[index] || primary != last_primary[index] ||
                secondary != last_secondary[index] || count != last_count[index]) {
                log_line("heap_slot event=candidate-state slot=%zu address=0x%llx "
                         "primary_offset=0x%llx secondary_offset=0x%llx count=%u\n",
                         index, static_cast<unsigned long long>(pointer),
                         static_cast<unsigned long long>(primary - reinterpret_cast<uintptr_t>(gHeader)),
                         static_cast<unsigned long long>(secondary - reinterpret_cast<uintptr_t>(gHeader)),
                         count);
                last_pointer[index] = pointer;
                last_primary[index] = primary;
                last_secondary[index] = secondary;
                last_count[index] = count;
            }
            if (primary == gPrimary && secondary == gSecondary) {
                auto *field = reinterpret_cast<uint32_t *>(pointer + kCountOffset);
                uint32_t expected = 6;
                if (__atomic_compare_exchange_n(field, &expected, 10, false,
                                                __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
                    gPatchedCallbacks.fetch_add(1, std::memory_order_relaxed);
                    log_line("heap_slot event=patched address=0x%llx old=6 new=10 "
                             "page_hash=0x%016llx\n",
                             static_cast<unsigned long long>(pointer),
                             static_cast<unsigned long long>(hash_page(
                                 reinterpret_cast<const uint8_t *>(gPage), gPageSize)));
                }
            }
            gHazards[index].store(0, std::memory_order_release);
        }
        if (!any) usleep(100);

        uint64_t matches = gMatchedAllocations.load(std::memory_order_relaxed);
        uint64_t drops = gDroppedAllocations.load(std::memory_order_relaxed);
        uint64_t patches = gPatchedCallbacks.load(std::memory_order_relaxed);
        if (matches != last_matches || drops != last_drops || patches != last_patches) {
            log_line("heap_slot event=counters matched_allocations=%llu "
                     "dropped_allocations=%llu patched_callbacks=%llu\n",
                     static_cast<unsigned long long>(matches),
                     static_cast<unsigned long long>(drops),
                     static_cast<unsigned long long>(patches));
            last_matches = matches;
            last_drops = drops;
            last_patches = patches;
        }
        if (hash_page(reinterpret_cast<const uint8_t *>(gPage), gPageSize) != gPageHash) {
            log_line("heap_slot status=fatal-code-page-change\n");
            _exit(106);
        }
    }
    return nullptr;
}

__attribute__((constructor))
static void initialize() {
    const char *path = getenv("MK1212_MAC_SLOT_PATCH_LOG");
    if (path && *path) gLog = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (gLog < 0) _exit(100);
    gHeader = main_executable();
    if (!gHeader || !uuid_matches(gHeader)) _exit(101);
    const uint8_t *base = reinterpret_cast<const uint8_t *>(gHeader);
    if (memcmp(base + kSite1 - 4, kContext, sizeof(kContext)) != 0 ||
        memcmp(base + kSite2 - 4, kContext, sizeof(kContext)) != 0) _exit(102);
    gPageSize = static_cast<size_t>(getpagesize());
    gPage = (reinterpret_cast<uintptr_t>(base + kSite1)) & ~(gPageSize - 1);
    gPageHash = hash_page(reinterpret_cast<const uint8_t *>(gPage), gPageSize);
    gPrimary = reinterpret_cast<uintptr_t>(gHeader) + kPrimaryVptr;
    gSecondary = reinterpret_cast<uintptr_t>(gHeader) + kSecondaryVptr;
    pthread_t thread{};
    if (pthread_create(&thread, nullptr, monitor, nullptr) != 0) _exit(103);
    pthread_detach(thread);
    log_line("heap_slot status=observer-ready mode=heap-field-6-to-10 revision=v3 "
             "executable_page_writes=false page_hash=0x%016llx\n",
             static_cast<unsigned long long>(gPageHash));
}

