#import <AppKit/AppKit.h>
#import <Security/Security.h>
#include <unistd.h>

static NSString *const InstalledContainer = @"/Applications/MK1212 Mac Launcher";

static NSString *LogPath(void) {
    NSString *root = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/MK1212 Mac Launcher"];
    [[NSFileManager defaultManager] createDirectoryAtPath:root
                              withIntermediateDirectories:YES attributes:nil error:nil];
    return [root stringByAppendingPathComponent:@"last-uninstall-error.log"];
}

static void WriteLog(NSString *message) {
    NSString *line = [NSString stringWithFormat:@"%@\n", message ?: @""];
    [line writeToFile:LogPath() atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

static void ShowAlert(NSString *message, NSAlertStyle style) {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"MK1212 Mac Launcher";
    alert.informativeText = message;
    alert.alertStyle = style;
    [alert addButtonWithTitle:@"OK"];
    [NSApp activateIgnoringOtherApps:YES];
    [alert runModal];
}

static int RunTask(NSString *path, NSArray<NSString *> *arguments, NSString **output) {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:path];
    task.arguments = arguments;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        if (output) *output = error.localizedDescription;
        return -1;
    }
    [task waitUntilExit];
    NSData *data = [[pipe fileHandleForReading] readDataToEndOfFile];
    if (output) {
        *output = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
    }
    return task.terminationStatus;
}

static NSString *FindPython(void) {
    NSArray<NSString *> *candidates = @[@"/usr/bin/python3", @"/opt/homebrew/bin/python3",
                                        @"/usr/local/bin/python3"];
    for (NSString *candidate in candidates) {
        if (![[NSFileManager defaultManager] isExecutableFileAtPath:candidate]) continue;
        if (RunTask(candidate, @[@"-c", @"import sys; raise SystemExit(sys.version_info < (3, 9))"], nil) == 0) {
            return candidate;
        }
    }
    return nil;
}

static BOOL ConfirmUninstall(void) {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Uninstall MK1212 Mac Launcher?";
    alert.informativeText = @"This removes the launcher and its compatibility cache. Workshop packs, Total War: ATTILA, and saved campaigns will be left untouched.";
    alert.alertStyle = NSAlertStyleWarning;
    [alert addButtonWithTitle:@"Uninstall"];
    [alert addButtonWithTitle:@"Cancel"];
    [NSApp activateIgnoringOtherApps:YES];
    return [alert runModal] == NSAlertFirstButtonReturn;
}

static BOOL RemoveInstalledContainer(NSString *container, NSString **failure) {
    AuthorizationRef authorization = NULL;
    OSStatus status = AuthorizationCreate(NULL, kAuthorizationEmptyEnvironment,
                                           kAuthorizationFlagDefaults, &authorization);
    if (status != errAuthorizationSuccess) {
        if (failure) *failure = [NSString stringWithFormat:@"AuthorizationCreate failed (%d).", (int)status];
        return NO;
    }

    AuthorizationItem item = {kAuthorizationRightExecute, 0, NULL, 0};
    AuthorizationRights rights = {1, &item};
    AuthorizationFlags flags = kAuthorizationFlagInteractionAllowed |
                               kAuthorizationFlagPreAuthorize |
                               kAuthorizationFlagExtendRights;
    status = AuthorizationCopyRights(authorization, &rights, kAuthorizationEmptyEnvironment,
                                     flags, NULL);
    if (status != errAuthorizationSuccess) {
        AuthorizationFree(authorization, kAuthorizationFlagDefaults);
        if (failure) *failure = status == errAuthorizationCanceled
            ? @"Administrator authorization was cancelled."
            : [NSString stringWithFormat:@"Administrator authorization failed (%d).", (int)status];
        return NO;
    }

    char *arguments[] = {"-rf", "--", (char *)container.fileSystemRepresentation, NULL};
    FILE *communications = NULL;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    status = AuthorizationExecuteWithPrivileges(authorization, "/bin/rm",
                                                 kAuthorizationFlagDefaults,
                                                 arguments, &communications);
#pragma clang diagnostic pop
    if (communications) {
        char buffer[256];
        while (fread(buffer, 1, sizeof(buffer), communications) > 0) {}
        fclose(communications);
    }
    AuthorizationFree(authorization, kAuthorizationFlagDestroyRights);

    if (status != errAuthorizationSuccess) {
        if (failure) *failure = [NSString stringWithFormat:@"The authorized removal failed (%d).", (int)status];
        return NO;
    }
    for (int attempt = 0; attempt < 50; ++attempt) {
        if (![[NSFileManager defaultManager] fileExistsAtPath:container]) return YES;
        usleep(100000);
    }
    if (failure) *failure = @"macOS reported success, but the installed launcher folder is still present.";
    return NO;
}

int main(void) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        [NSApp activateIgnoringOtherApps:YES];

        NSFileManager *files = [NSFileManager defaultManager];
        if (![files fileExistsAtPath:InstalledContainer]) {
            ShowAlert(@"The launcher is not installed in /Applications/MK1212 Mac Launcher/.",
                      NSAlertStyleInformational);
            return 0;
        }
        if (!ConfirmUninstall()) return 0;

        if (RunTask(@"/usr/bin/pgrep",
                    @[@"-f", @"Total War ATTILA.app/Contents/MacOS/Total War ATTILA"], nil) == 0) {
            ShowAlert(@"ATTILA is still running. Close it, then run the uninstaller again.",
                      NSAlertStyleCritical);
            return 1;
        }

        NSString *tool = [InstalledContainer stringByAppendingPathComponent:
                          @"MK1212 Mac Launcher.app/Contents/Resources/mk1212_mac_tool.py"];
        NSString *python = FindPython();
        if (!python || ![files fileExistsAtPath:tool]) {
            NSString *message = !python ? @"Python 3.9 or newer was not found. Nothing was removed."
                                        : @"The bundled cleanup tool is missing. Nothing was removed.";
            WriteLog(message);
            ShowAlert(message, NSAlertStyleCritical);
            return 1;
        }

        NSString *cleanupOutput = nil;
        int cleanupStatus = RunTask(python, @[tool, @"uninstall"], &cleanupOutput);
        if (cleanupStatus != 0) {
            NSString *message = cleanupOutput.length ? cleanupOutput
                                                     : @"The compatibility-cache cleanup failed.";
            WriteLog(message);
            ShowAlert(message, NSAlertStyleCritical);
            return cleanupStatus;
        }

        NSString *failure = nil;
        if (!RemoveInstalledContainer(InstalledContainer, &failure)) {
            WriteLog(failure);
            ShowAlert(failure, NSAlertStyleCritical);
            return 1;
        }
        WriteLog(@"Uninstall completed successfully.");
        return 0;
    }
}
