# 0.8.0 release notes

Version 0.8.0 replaces the 0.7.0 ten-slot implementation that could cause
delayed clicks and render-surface scaling after several minutes of play.

## Changes

- Uses the tested heap-only settlement-slot patch. It changes the matching
  in-memory object field from 6 to 10 without writing to ATTILA's executable
  code pages.
- Corrects generated movie-pack precedence so a high-priority submod wins file
  collisions. This restores submods such as Tycherious' 4TPY.
- Replaces the numeric priority prompt with a native, foreground submod window.
  Check submods and drag them into order; the top row has highest priority.
- Adds a `? Help` window with launch instructions, including the requirement to
  leave every mod disabled in Feral's subsequent launcher.
- Adds `Rebuild Cache`, which safely recreates generated compatibility packs
  from the installed Workshop sources.
- Adds foreground progress windows for initial preparation, cache rebuilds, and
  first-time preparation of new submod combinations.
- Removes nonessential macOS notification banners. Detailed progress remains
  available in the launcher log.
- Adds a standard macOS installer package. It installs a custom-icon
  `MK1212 Mac Launcher` folder in Applications, replacing the old drag-and-drop
  and preparation-helper workflow.
- Replaces the old shell uninstaller with a native macOS uninstaller that safely
  removes the generated cache before requesting authorization to remove its
  exact Installer-owned Applications folder.

## Validation completed

The release candidate has been exercised through many campaign turns and
battles with multiple ten-building-slot settlements. The tested optional set
included Tycherious' 1212 Tweaks, Realistic Smoke, and Tycherious' 4TPY.

Version 0.8.0 remains limited to the Apple Silicon Feral ATTILA 1.6.1 build
`480285.103778`. Other executable hashes are refused.

Thanks to:

@paulkremer for describing the method by which this launcher was developed.

@raweon for testing.

Robonios for the independent audit and troubleshooting work that
helped narrow the 0.7.0 failure.

...and the entire MK1212 Dev Team for making an amazing mod.
