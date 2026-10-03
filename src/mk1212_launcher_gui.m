#import <Cocoa/Cocoa.h>

static NSPasteboardType const MKSubmodRowType = @"local.mk1212.launcher.submod-row";

@interface MKLauncherController : NSObject <NSApplicationDelegate, NSTableViewDataSource,
    NSTableViewDelegate, NSWindowDelegate>
@property(nonatomic) NSMutableArray<NSMutableDictionary *> *items;
@property(nonatomic) NSString *actionLabel;
@property(nonatomic) NSString *helpText;
@property(nonatomic, nullable) NSString *status;
@property(nonatomic) NSString *mode;
@property(nonatomic, nullable) NSString *progressPath;
@property(nonatomic, nullable) NSString *donePath;
@property(nonatomic, nullable) NSString *progressTitle;
@property(nonatomic, nullable) NSString *progressDetail;
@property(nonatomic, nullable) NSString *errorTitle;
@property(nonatomic, nullable) NSString *errorMessage;
@property(nonatomic, nullable) NSString *errorDetail;
@property(nonatomic, nullable) NSString *resultPath;
@property(nonatomic) NSWindow *window;
@property(nonatomic, nullable) NSWindow *helpWindow;
@property(nonatomic) NSTableView *tableView;
@property(nonatomic, nullable) NSTextField *progressLabel;
@property(nonatomic, nullable) NSProgressIndicator *progressIndicator;
@property(nonatomic, nullable) NSTimer *progressTimer;
@property(nonatomic) BOOL emittedResult;
- (instancetype)initWithConfig:(NSDictionary *)config;
- (void)buildWindow;
- (void)buildErrorWindow;
@end

static MKLauncherController *MKController = nil;

@implementation MKLauncherController

- (instancetype)initWithConfig:(NSDictionary *)config {
    self = [super init];
    if (self) {
        _items = [NSMutableArray array];
        for (NSDictionary *item in config[@"items"]) {
            [_items addObject:[@{
                @"name": item[@"name"] ?: @"",
                @"selected": item[@"selected"] ?: @NO,
            } mutableCopy]];
        }
        _actionLabel = config[@"actionLabel"] ?: @"Launch";
        _helpText = config[@"helpText"] ?: @"";
        id status = config[@"status"];
        _status = [status isKindOfClass:NSString.class] ? status : nil;
        id mode = config[@"mode"];
        _mode = [mode isKindOfClass:NSString.class] ? mode : @"picker";
        id progressPath = config[@"progressPath"];
        _progressPath = [progressPath isKindOfClass:NSString.class] ? progressPath : nil;
        id donePath = config[@"donePath"];
        _donePath = [donePath isKindOfClass:NSString.class] ? donePath : nil;
        id progressTitle = config[@"progressTitle"];
        _progressTitle = [progressTitle isKindOfClass:NSString.class] ? progressTitle : nil;
        id progressDetail = config[@"progressDetail"];
        _progressDetail = [progressDetail isKindOfClass:NSString.class] ? progressDetail : nil;
        id errorTitle = config[@"errorTitle"];
        _errorTitle = [errorTitle isKindOfClass:NSString.class] ? errorTitle : nil;
        id errorMessage = config[@"errorMessage"];
        _errorMessage = [errorMessage isKindOfClass:NSString.class] ? errorMessage : nil;
        id errorDetail = config[@"errorDetail"];
        _errorDetail = [errorDetail isKindOfClass:NSString.class] ? errorDetail : nil;
    }
    return self;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    if (self.window == nil) [self buildWindow];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    (void)sender;
    return YES;
}

- (BOOL)windowShouldClose:(NSWindow *)sender {
    if ([self.mode isEqualToString:@"progress"] && sender == self.window) return NO;
    if ([self.mode isEqualToString:@"error"] && sender == self.window) return YES;
    if (sender == self.window && !self.emittedResult) {
        [self emitAction:@"cancel"];
        return NO;
    }
    return YES;
}

- (void)buildWindow {
    if ([self.mode isEqualToString:@"progress"]) {
        [self buildProgressWindow];
        return;
    }
    if ([self.mode isEqualToString:@"error"]) {
        [self buildErrorWindow];
        return;
    }
    NSWindow *window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0, 0, 720, 560)
                  styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                            NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
                    backing:NSBackingStoreBuffered
                      defer:NO];
    window.title = @"ausxen's MK1212 macOS Launcher";
    window.minSize = NSMakeSize(620, 430);
    window.level = NSFloatingWindowLevel;
    window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                NSWindowCollectionBehaviorFullScreenAuxiliary;
    window.releasedWhenClosed = NO;
    window.delegate = self;

    NSView *content = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 720, 560)];
    window.contentView = content;

    NSTextField *title = [NSTextField labelWithString:@"Choose and order submods"];
    title.font = [NSFont systemFontOfSize:22 weight:NSFontWeightSemibold];

    NSTextField *explanation = [NSTextField wrappingLabelWithString:
        @"Check the submods to use, then drag rows into priority order. "
         "The top row has highest priority. Core MK1212 packs are always enabled."];
    explanation.textColor = NSColor.secondaryLabelColor;

    NSTableView *table = [[NSTableView alloc] init];
    table.delegate = self;
    table.dataSource = self;
    table.rowHeight = 30;
    table.usesAlternatingRowBackgroundColors = YES;
    table.allowsEmptySelection = YES;
    table.allowsMultipleSelection = NO;
    [table registerForDraggedTypes:@[MKSubmodRowType]];
    [table setDraggingSourceOperationMask:NSDragOperationMove forLocal:YES];

    NSTableColumn *enabledColumn = [[NSTableColumn alloc] initWithIdentifier:@"enabled"];
    enabledColumn.title = @"Enabled";
    enabledColumn.width = 76;
    enabledColumn.minWidth = 76;
    enabledColumn.maxWidth = 76;
    [table addTableColumn:enabledColumn];

    NSTableColumn *nameColumn = [[NSTableColumn alloc] initWithIdentifier:@"name"];
    nameColumn.title = @"Submod (drag to reorder)";
    nameColumn.minWidth = 400;
    [table addTableColumn:nameColumn];

    NSScrollView *scroll = [[NSScrollView alloc] init];
    scroll.borderType = NSBezelBorder;
    scroll.hasVerticalScroller = YES;
    scroll.autohidesScrollers = YES;
    scroll.documentView = table;

    NSString *emptyMessage = self.items.count == 0
        ? @"No optional submods were found. Core MK1212 packs will be used." : @"";
    NSTextField *emptyLabel = [NSTextField labelWithString:emptyMessage];
    emptyLabel.alignment = NSTextAlignmentCenter;
    emptyLabel.textColor = NSColor.secondaryLabelColor;
    emptyLabel.hidden = self.items.count != 0;

    NSTextField *statusLabel = [NSTextField wrappingLabelWithString:self.status ?: @""];
    statusLabel.textColor = NSColor.systemGreenColor;
    statusLabel.font = [NSFont systemFontOfSize:12 weight:NSFontWeightMedium];
    statusLabel.hidden = self.status.length == 0;

    NSButton *helpButton = [NSButton buttonWithTitle:@"?  Help"
                                             target:self action:@selector(showHelp:)];
    helpButton.bezelStyle = NSBezelStyleRounded;
    NSButton *rebuildButton = [NSButton buttonWithTitle:@"Rebuild Cache"
                                                target:self action:@selector(rebuildCache:)];
    rebuildButton.bezelStyle = NSBezelStyleRounded;
    rebuildButton.toolTip = @"Discard and recreate all generated compatibility packs.";
    NSButton *cancelButton = [NSButton buttonWithTitle:@"Cancel"
                                               target:self action:@selector(cancel:)];
    cancelButton.bezelStyle = NSBezelStyleRounded;
    cancelButton.keyEquivalent = @"\e";
    NSButton *confirmButton = [NSButton buttonWithTitle:self.actionLabel
                                                target:self action:@selector(confirm:)];
    confirmButton.bezelStyle = NSBezelStyleRounded;
    confirmButton.keyEquivalent = @"\r";

    NSView *spacer = [[NSView alloc] init];
    [spacer setContentHuggingPriority:NSLayoutPriorityDefaultLow
                       forOrientation:NSLayoutConstraintOrientationHorizontal];
    NSStackView *buttonRow = [NSStackView stackViewWithViews:
        @[helpButton, rebuildButton, spacer, cancelButton, confirmButton]];
    buttonRow.orientation = NSUserInterfaceLayoutOrientationHorizontal;
    buttonRow.spacing = 10;
    buttonRow.alignment = NSLayoutAttributeCenterY;

    NSArray<NSView *> *views = @[title, explanation, scroll, emptyLabel, statusLabel, buttonRow];
    for (NSView *view in views) {
        view.translatesAutoresizingMaskIntoConstraints = NO;
        [content addSubview:view];
    }

    [NSLayoutConstraint activateConstraints:@[
        [title.topAnchor constraintEqualToAnchor:content.topAnchor constant:22],
        [title.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:24],
        [title.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-24],
        [explanation.topAnchor constraintEqualToAnchor:title.bottomAnchor constant:8],
        [explanation.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [explanation.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [scroll.topAnchor constraintEqualToAnchor:explanation.bottomAnchor constant:16],
        [scroll.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [scroll.bottomAnchor constraintEqualToAnchor:statusLabel.topAnchor constant:-12],
        [emptyLabel.centerXAnchor constraintEqualToAnchor:scroll.centerXAnchor],
        [emptyLabel.centerYAnchor constraintEqualToAnchor:scroll.centerYAnchor],
        [emptyLabel.leadingAnchor constraintGreaterThanOrEqualToAnchor:scroll.leadingAnchor constant:20],
        [emptyLabel.trailingAnchor constraintLessThanOrEqualToAnchor:scroll.trailingAnchor constant:-20],
        [statusLabel.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [statusLabel.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [statusLabel.bottomAnchor constraintEqualToAnchor:buttonRow.topAnchor constant:-12],
        [statusLabel.heightAnchor constraintGreaterThanOrEqualToConstant:16],
        [buttonRow.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [buttonRow.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [buttonRow.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-20],
        [buttonRow.heightAnchor constraintEqualToConstant:32],
    ]];

    self.window = window;
    self.tableView = table;
    [window center];
    [window makeKeyAndOrderFront:nil];
    [window orderFrontRegardless];
    [NSApp activateIgnoringOtherApps:YES];
}

- (NSInteger)numberOfRowsInTableView:(NSTableView *)tableView {
    (void)tableView;
    return self.items.count;
}

- (NSView *)tableView:(NSTableView *)tableView
   viewForTableColumn:(NSTableColumn *)tableColumn
                  row:(NSInteger)row {
    (void)tableView;
    if (row < 0 || row >= (NSInteger)self.items.count) return nil;
    NSDictionary *item = self.items[(NSUInteger)row];
    if ([tableColumn.identifier isEqualToString:@"enabled"]) {
        NSButton *checkbox = [NSButton checkboxWithTitle:@""
                                                  target:self action:@selector(toggleSubmod:)];
        checkbox.state = [item[@"selected"] boolValue] ? NSControlStateValueOn : NSControlStateValueOff;
        checkbox.tag = row;
        return checkbox;
    }
    NSTextField *label = [NSTextField labelWithString:item[@"name"]];
    label.lineBreakMode = NSLineBreakByTruncatingMiddle;
    label.toolTip = item[@"name"];
    return label;
}

- (id<NSPasteboardWriting>)tableView:(NSTableView *)tableView
            pasteboardWriterForRow:(NSInteger)row {
    (void)tableView;
    NSPasteboardItem *item = [[NSPasteboardItem alloc] init];
    [item setString:[NSString stringWithFormat:@"%ld", (long)row] forType:MKSubmodRowType];
    return item;
}

- (NSDragOperation)tableView:(NSTableView *)tableView
                validateDrop:(id<NSDraggingInfo>)info
                 proposedRow:(NSInteger)row
       proposedDropOperation:(NSTableViewDropOperation)dropOperation {
    (void)dropOperation;
    [tableView setDropRow:row dropOperation:NSTableViewDropAbove];
    return info.draggingSource == tableView ? NSDragOperationMove : NSDragOperationNone;
}

- (BOOL)tableView:(NSTableView *)tableView
        acceptDrop:(id<NSDraggingInfo>)info
               row:(NSInteger)row
     dropOperation:(NSTableViewDropOperation)dropOperation {
    (void)dropOperation;
    NSString *value = [info.draggingPasteboard stringForType:MKSubmodRowType];
    NSInteger source = value.integerValue;
    if (value == nil || source < 0 || source >= (NSInteger)self.items.count) return NO;
    NSInteger destination = MAX(0, MIN(row, (NSInteger)self.items.count));
    NSMutableDictionary *moved = self.items[(NSUInteger)source];
    [self.items removeObjectAtIndex:(NSUInteger)source];
    if (source < destination) destination -= 1;
    [self.items insertObject:moved atIndex:(NSUInteger)destination];
    [tableView reloadData];
    [tableView selectRowIndexes:[NSIndexSet indexSetWithIndex:(NSUInteger)destination]
           byExtendingSelection:NO];
    return YES;
}

- (void)toggleSubmod:(NSButton *)sender {
    if (sender.tag < 0 || sender.tag >= (NSInteger)self.items.count) return;
    self.items[(NSUInteger)sender.tag][@"selected"] = @(sender.state == NSControlStateValueOn);
}

- (void)confirm:(id)sender { (void)sender; [self emitAction:@"confirm"]; }
- (void)cancel:(id)sender { (void)sender; [self emitAction:@"cancel"]; }
- (void)rebuildCache:(id)sender {
    (void)sender;
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"Rebuild the compatibility cache?";
    alert.informativeText =
        @"This can take a few minutes. The launcher will recreate its generated "
         "compatibility packs from your installed Workshop files, then return to "
         "the submod screen. ATTILA will not launch until the rebuild is finished.";
    alert.alertStyle = NSAlertStyleInformational;
    [alert addButtonWithTitle:@"OK"];
    [alert addButtonWithTitle:@"Cancel"];
    [alert beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        if (response == NSAlertFirstButtonReturn) [self emitAction:@"rebuild"];
    }];
}

- (void)buildProgressWindow {
    NSWindow *window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0, 0, 560, 190)
                  styleMask:NSWindowStyleMaskTitled
                    backing:NSBackingStoreBuffered
                      defer:NO];
    window.title = @"ausxen's MK1212 macOS Launcher";
    window.level = NSFloatingWindowLevel;
    window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                NSWindowCollectionBehaviorFullScreenAuxiliary;
    window.releasedWhenClosed = NO;
    window.delegate = self;

    NSView *content = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 560, 190)];
    window.contentView = content;
    NSTextField *title = [NSTextField labelWithString:
        self.progressTitle ?: @"Rebuilding compatibility cache"];
    title.font = [NSFont systemFontOfSize:20 weight:NSFontWeightSemibold];
    NSTextField *detail = [NSTextField wrappingLabelWithString:
        self.progressDetail ?: @"This can take a few minutes. Please leave the launcher open."];
    detail.textColor = NSColor.secondaryLabelColor;
    NSProgressIndicator *indicator = [[NSProgressIndicator alloc] init];
    indicator.style = NSProgressIndicatorStyleBar;
    indicator.indeterminate = YES;
    indicator.controlSize = NSControlSizeRegular;
    [indicator startAnimation:nil];
    NSTextField *status = [NSTextField wrappingLabelWithString:@"Starting cache rebuild…"];
    status.textColor = NSColor.secondaryLabelColor;
    status.lineBreakMode = NSLineBreakByTruncatingMiddle;

    for (NSView *view in @[title, detail, indicator, status]) {
        view.translatesAutoresizingMaskIntoConstraints = NO;
        [content addSubview:view];
    }
    [NSLayoutConstraint activateConstraints:@[
        [title.topAnchor constraintEqualToAnchor:content.topAnchor constant:24],
        [title.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:26],
        [title.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-26],
        [detail.topAnchor constraintEqualToAnchor:title.bottomAnchor constant:8],
        [detail.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [detail.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [indicator.topAnchor constraintEqualToAnchor:detail.bottomAnchor constant:18],
        [indicator.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [indicator.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [status.topAnchor constraintEqualToAnchor:indicator.bottomAnchor constant:12],
        [status.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [status.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [status.bottomAnchor constraintLessThanOrEqualToAnchor:content.bottomAnchor constant:-18],
    ]];

    self.window = window;
    self.progressLabel = status;
    self.progressIndicator = indicator;
    [window center];
    [window makeKeyAndOrderFront:nil];
    [window orderFrontRegardless];
    [NSApp activateIgnoringOtherApps:YES];
    self.progressTimer = [NSTimer scheduledTimerWithTimeInterval:0.2
        target:self selector:@selector(pollProgress:) userInfo:nil repeats:YES];
    [self pollProgress:nil];
}

- (void)buildErrorWindow {
    NSWindow *window = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0, 0, 620, 360)
                  styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                    backing:NSBackingStoreBuffered
                      defer:NO];
    window.title = @"ausxen's MK1212 macOS Launcher";
    window.level = NSFloatingWindowLevel;
    window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                                NSWindowCollectionBehaviorFullScreenAuxiliary;
    window.releasedWhenClosed = NO;
    window.delegate = self;

    NSView *content = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 620, 360)];
    window.contentView = content;

    NSImageView *icon = [[NSImageView alloc] init];
    icon.image = [NSImage imageNamed:NSImageNameCaution];
    icon.imageScaling = NSImageScaleProportionallyUpOrDown;

    NSTextField *title = [NSTextField labelWithString:self.errorTitle ?: @"Launch stopped"];
    title.font = [NSFont systemFontOfSize:22 weight:NSFontWeightSemibold];

    NSTextField *message = [NSTextField wrappingLabelWithString:self.errorMessage ?: @""];
    message.font = [NSFont systemFontOfSize:14];

    NSTextField *detail = [NSTextField wrappingLabelWithString:self.errorDetail ?: @""];
    detail.font = [NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightRegular];
    detail.textColor = NSColor.secondaryLabelColor;
    detail.selectable = YES;
    detail.hidden = self.errorDetail.length == 0;

    NSButton *okButton = [NSButton buttonWithTitle:@"OK"
                                           target:self action:@selector(dismissError:)];
    okButton.bezelStyle = NSBezelStyleRounded;
    okButton.keyEquivalent = @"\r";

    for (NSView *view in @[icon, title, message, detail, okButton]) {
        view.translatesAutoresizingMaskIntoConstraints = NO;
        [content addSubview:view];
    }
    [NSLayoutConstraint activateConstraints:@[
        [icon.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:24],
        [icon.topAnchor constraintEqualToAnchor:content.topAnchor constant:26],
        [icon.widthAnchor constraintEqualToConstant:48],
        [icon.heightAnchor constraintEqualToConstant:48],
        [title.leadingAnchor constraintEqualToAnchor:icon.trailingAnchor constant:16],
        [title.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-26],
        [title.topAnchor constraintEqualToAnchor:content.topAnchor constant:26],
        [message.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [message.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [message.topAnchor constraintEqualToAnchor:title.bottomAnchor constant:14],
        [detail.leadingAnchor constraintEqualToAnchor:title.leadingAnchor],
        [detail.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [detail.topAnchor constraintEqualToAnchor:message.bottomAnchor constant:16],
        [okButton.trailingAnchor constraintEqualToAnchor:title.trailingAnchor],
        [okButton.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-22],
        [okButton.topAnchor constraintGreaterThanOrEqualToAnchor:detail.bottomAnchor constant:18],
    ]];

    self.window = window;
    [window center];
    [window makeKeyAndOrderFront:nil];
    [window orderFrontRegardless];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)dismissError:(id)sender {
    (void)sender;
    [self.window orderOut:nil];
    [NSApp terminate:nil];
}

- (NSDictionary *)dictionaryAtPath:(NSString *)path {
    if (path.length == 0) return nil;
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (data == nil) return nil;
    id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    return [value isKindOfClass:NSDictionary.class] ? value : nil;
}

- (void)pollProgress:(NSTimer *)timer {
    (void)timer;
    NSDictionary *progress = [self dictionaryAtPath:self.progressPath];
    id message = progress[@"message"];
    if ([message isKindOfClass:NSString.class] && [message length] != 0) {
        self.progressLabel.stringValue = message;
    }
    NSDictionary *done = [self dictionaryAtPath:self.donePath];
    id result = done[@"status"];
    if (![result isKindOfClass:NSString.class]) return;
    [self.progressTimer invalidate];
    self.progressTimer = nil;
    [self.progressIndicator stopAnimation:nil];
    self.progressIndicator.indeterminate = NO;
    self.progressIndicator.doubleValue = [result isEqualToString:@"success"] ? 100 : 0;
    id finalMessage = done[@"message"];
    if ([finalMessage isKindOfClass:NSString.class]) {
        self.progressLabel.stringValue = finalMessage;
    }
    [self.window displayIfNeeded];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.35 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; });
}

- (void)showHelp:(id)sender {
    (void)sender;
    if (self.helpWindow != nil) {
        [self.helpWindow makeKeyAndOrderFront:nil];
        [self.helpWindow orderFrontRegardless];
        return;
    }
    NSWindow *panel = [[NSWindow alloc]
        initWithContentRect:NSMakeRect(0, 0, 560, 430)
                  styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                            NSWindowStyleMaskResizable
                    backing:NSBackingStoreBuffered
                      defer:NO];
    panel.title = @"MK1212 Launcher Help";
    panel.level = NSFloatingWindowLevel;
    panel.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                               NSWindowCollectionBehaviorFullScreenAuxiliary;
    panel.releasedWhenClosed = NO;

    NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:panel.contentView.bounds];
    scroll.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    scroll.hasVerticalScroller = YES;
    scroll.borderType = NSNoBorder;
    NSTextView *text = [[NSTextView alloc] initWithFrame:scroll.bounds];
    text.editable = NO;
    text.selectable = YES;
    text.drawsBackground = NO;
    text.textContainerInset = NSMakeSize(18, 18);
    text.font = [NSFont systemFontOfSize:14];
    text.string = self.helpText;
    text.autoresizingMask = NSViewWidthSizable;
    scroll.documentView = text;
    panel.contentView = scroll;
    [panel center];
    self.helpWindow = panel;
    [panel makeKeyAndOrderFront:nil];
    [panel orderFrontRegardless];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)emitAction:(NSString *)action {
    if (self.emittedResult) return;
    self.emittedResult = YES;
    NSMutableArray<NSString *> *selected = [NSMutableArray array];
    NSMutableArray<NSString *> *order = [NSMutableArray array];
    for (NSDictionary *item in self.items) {
        [order addObject:item[@"name"]];
        if ([item[@"selected"] boolValue]) [selected addObject:item[@"name"]];
    }
    NSDictionary *result = @{@"action": action, @"selected": selected, @"order": order};
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:result options:0 error:&error];
    if (data != nil && self.resultPath.length != 0) {
        NSError *writeError = nil;
        if (![data writeToFile:self.resultPath options:NSDataWritingAtomic error:&writeError]) {
            NSString *message = [NSString stringWithFormat:
                @"Could not write launcher result: %@\n", writeError];
            [[NSFileHandle fileHandleWithStandardError]
                writeData:[message dataUsingEncoding:NSUTF8StringEncoding]];
        }
    } else if (data != nil) {
        [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
        [[NSFileHandle fileHandleWithStandardOutput]
            writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
    } else {
        NSString *message = [NSString stringWithFormat:@"Could not encode launcher result: %@\n", error];
        [[NSFileHandle fileHandleWithStandardError]
            writeData:[message dataUsingEncoding:NSUTF8StringEncoding]];
    }
    [self.window orderOut:nil];
    [self.helpWindow orderOut:nil];
    [NSApp terminate:nil];
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSData *input = nil;
        NSString *resultPath = nil;
        if (argc == 2) {
            input = [[[NSString alloc] initWithUTF8String:argv[1]]
                dataUsingEncoding:NSUTF8StringEncoding];
        } else if (argc == 3 && strcmp(argv[1], "--config") == 0) {
            NSString *configPath = [[NSString alloc] initWithUTF8String:argv[2]];
            input = [NSData dataWithContentsOfFile:configPath];
        } else if (argc == 5 && strcmp(argv[1], "--config") == 0 &&
                   strcmp(argv[3], "--result") == 0) {
            NSString *configPath = [[NSString alloc] initWithUTF8String:argv[2]];
            resultPath = [[NSString alloc] initWithUTF8String:argv[4]];
            input = [NSData dataWithContentsOfFile:configPath];
        } else {
            fprintf(stderr, "Usage: mk1212-launcher-gui '<configuration-json>', "
                            "--config PATH, or --config PATH --result PATH\n");
            return 2;
        }
        NSError *error = nil;
        NSDictionary *config = [NSJSONSerialization JSONObjectWithData:input options:0 error:&error];
        if (![config isKindOfClass:NSDictionary.class]) {
            fprintf(stderr, "Invalid launcher configuration: %s\n",
                    error.localizedDescription.UTF8String ?: "unknown error");
            return 2;
        }
        NSApplication *application = NSApplication.sharedApplication;
        MKController = [[MKLauncherController alloc] initWithConfig:config];
        MKController.resultPath = resultPath;
        [application setActivationPolicy:NSApplicationActivationPolicyAccessory];
        application.delegate = MKController;
        [MKController buildWindow];
        [application run];
    }
    return 0;
}
