#include <fcntl.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Feral ATTILA 1.6.1, build 480285.103778, arm64. */
static const uint8_t supported_uuid[16] = {
    0x39, 0x2d, 0x6f, 0x66, 0x91, 0x83, 0x32, 0x9e,
    0x8a, 0x98, 0x8c, 0x90, 0xfc, 0x82, 0x83, 0x26,
};

/* Store settlement-capital flag; mov w8, #6; store maximum slot count. */
static const uint8_t before_context[12] = {
    0x08, 0xc0, 0x01, 0x39,
    0xc8, 0x00, 0x80, 0x52,
    0x08, 0x74, 0x00, 0xb9,
};

static const uint8_t replacement_instruction[4] = {
    0x48, 0x01, 0x80, 0x52, /* mov w8, #10 */
};

static const uintptr_t patch_offsets[2] = {
    0x03457244,
    0x034577f4,
};

static int image_uuid(const struct mach_header_64 *header, uint8_t result[16]) {
    const uint8_t *cursor = (const uint8_t *)(header + 1);
    for (uint32_t index = 0; index < header->ncmds; ++index) {
        const struct load_command *command = (const struct load_command *)cursor;
        if (command->cmdsize < sizeof(*command)) {
            return 0;
        }
        if (command->cmd == LC_UUID && command->cmdsize >= sizeof(struct uuid_command)) {
            const struct uuid_command *uuid = (const struct uuid_command *)command;
            memcpy(result, uuid->uuid, 16);
            return 1;
        }
        cursor += command->cmdsize;
    }
    return 0;
}

static const struct mach_header_64 *main_executable(void) {
    uint32_t count = _dyld_image_count();
    for (uint32_t index = 0; index < count; ++index) {
        const struct mach_header *candidate = _dyld_get_image_header(index);
        if (candidate != NULL && candidate->magic == MH_MAGIC_64 &&
                candidate->filetype == MH_EXECUTE) {
            return (const struct mach_header_64 *)candidate;
        }
    }
    return NULL;
}

static void log_result(int descriptor, const char *status, kern_return_t code) {
    if (descriptor >= 0) {
        dprintf(descriptor, "runtime_patch status=%s kern_return=%d\n", status, code);
    }
}

__attribute__((constructor))
static void mk1212_runtime_patch(void) {
    const char *log_path = getenv("MK1212_MAC_SLOT_PATCH_LOG");
    int descriptor = -1;
    if (log_path != NULL && log_path[0] != '\0') {
        descriptor = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0600);
    }

    const struct mach_header_64 *header = main_executable();
    if (header == NULL) {
        log_result(descriptor, "no-main-executable", KERN_INVALID_ADDRESS);
        if (descriptor >= 0) close(descriptor);
        return;
    }

    uint8_t uuid[16] = {0};
    if (!image_uuid(header, uuid) || memcmp(uuid, supported_uuid, sizeof(uuid)) != 0) {
        log_result(descriptor, "unsupported-uuid", KERN_INVALID_ARGUMENT);
        if (descriptor >= 0) close(descriptor);
        return;
    }

    uint8_t *sites[2];
    for (size_t index = 0; index < 2; ++index) {
        sites[index] = (uint8_t *)header + patch_offsets[index];
        if (memcmp(sites[index] - 4, before_context, sizeof(before_context)) != 0) {
            log_result(descriptor, "preimage-mismatch", KERN_INVALID_ARGUMENT);
            if (descriptor >= 0) close(descriptor);
            return;
        }
    }

    vm_size_t page_size = (vm_size_t)getpagesize();
    mach_vm_address_t first_page = (mach_vm_address_t)sites[0] & ~((mach_vm_address_t)page_size - 1);
    mach_vm_address_t last_page = (mach_vm_address_t)sites[1] & ~((mach_vm_address_t)page_size - 1);
    mach_vm_size_t span = (last_page - first_page) + page_size;

    kern_return_t result = mach_vm_protect(
        mach_task_self(), first_page, span, FALSE,
        VM_PROT_READ | VM_PROT_WRITE | VM_PROT_COPY
    );
    if (result != KERN_SUCCESS) {
        log_result(descriptor, "make-writable-failed", result);
        if (descriptor >= 0) close(descriptor);
        return;
    }

    for (size_t index = 0; index < 2; ++index) {
        memcpy(sites[index], replacement_instruction, sizeof(replacement_instruction));
    }
    __builtin___clear_cache((char *)first_page, (char *)(first_page + span));

    result = mach_vm_protect(
        mach_task_self(), first_page, span, FALSE,
        VM_PROT_READ | VM_PROT_EXECUTE
    );
    if (result != KERN_SUCCESS) {
        log_result(descriptor, "restore-execute-failed", result);
        if (descriptor >= 0) close(descriptor);
        return;
    }

    for (size_t index = 0; index < 2; ++index) {
        if (memcmp(sites[index], replacement_instruction, sizeof(replacement_instruction)) != 0) {
            log_result(descriptor, "postimage-mismatch", KERN_FAILURE);
            if (descriptor >= 0) close(descriptor);
            return;
        }
    }

    log_result(descriptor, "patched-6-to-10", KERN_SUCCESS);
    if (descriptor >= 0) close(descriptor);
}
