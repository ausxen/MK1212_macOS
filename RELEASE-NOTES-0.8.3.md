# MK1212 Mac Launcher 0.8.3

- Adds a separate **Clear Cache** button to free disk space without immediately rebuilding. Submod selections and load order are preserved.
- **Rebuild Cache** now clears the entire existing cache before recreating compatibility files, including output from interrupted builds.
- Opens the submod selector before checking cached files, so missing or damaged cache files no longer block access to the cache controls.
- Automatically rebuilds incomplete or damaged cached profiles when continuing to launch or saving the submod selection.
- Fixes rebuilding a missing cache when saved launcher records still mark setup as prepared.
- Refuses cache clearing or rebuilding while ATTILA or a launcher activation is active, and rejects unexpected or symlinked cache locations.

Clearing or rebuilding deletes the entire launcher cache, including saved recovery files. Original Steam Workshop downloads are preserved.

Supports Apple Silicon Feral ATTILA 1.6.1 build 480285.103778 on macOS 12 or newer.

Validation: 62 automated tests pass; the macOS launcher builds successfully. Cache clearing and rebuilding were confirmed working in user testing.
