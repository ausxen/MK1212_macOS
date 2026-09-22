# BUG NOTICE 2026-09-22

There is currently a bug affecting version 0.7.0

I am working on fixing it; in the meantime download version 0.6.1 from `dist/old/`


# ausxen's MK1212 macOS Launcher

[_Reading is for geeks, just give me the launcher._](https://github.com/ausxen/MK1212_macOS/raw/refs/heads/main/dist/MK1212_macOS-0.7.0.dmg)

## Table of Contents

1. [Why Tho](#why-tho)
2. [The Boring Technical Part](#the-boring-technical-part)
   1. [Test Status and Limitations](#test-status-and-limitations)
   2. [What It Does](#what-it-does)
   3. [Requirements](#requirements)
   4. [Install From Release](#install-from-release)
   5. [Verify](#verify)
   6. [Uninstall](#uninstall)
   7. [Data Locations](#data-locations)
   8. [Safety First](#safety-first)
3. [Build From Source](#build-from-source)
4. [Give Me DMG](#give-me-dmg)
5. [Bug Reporting](#bug-reporting)

## Why Tho

If you're a contemptible, sub-human macOS gamer like me and recently started playing the Feral Interactive release of Attila, you may have been disappointed to find that the Medieval Kingdoms 1212 AD mod is not macOS-compatible.

I was not satisfied to let that status quo sit unchallenged. So I put on my equally-contemptible AI fanboy vibe-coder hat and threw together this launcher.

It keeps Steam Workshop packs byte-for-byte unchanged, does not edit or
re-sign Feral's application, and does not use any sort of Windows emulation. It makes a reversible compatibility cache beside ATTILA's data directory and activates only the selected profile while the independent `.app` supervises the genuine Feral executable.

**As of right now I cannot guarantee it will work 100% of the time or with 100% of the submods for MK1212.** Therefore, if you are using this launcher, you are effectively a beta tester. Or alpha tester, I guess, if you're sensitive about your masculinity. Either way you're a guinea pig, so find a way to cope.

Anyway now for all the boring stuff.

## The Boring Technical Part

_You should actually probably read at least the first part of this._

### Test Status and Limitations

I tested it as follows:

- Apple Silicon / ARM64
- macOS with Feral ATTILA 1.6.1, build `480285.103778`
- MK1212 Scripts, Cities, Base, Models 1–9, and Music
- Tycherious' 1212 Tweaks, Realistic Smoke, and Tycherious' 4TPY

Your mileage may vary. If it does, let me know, because I want us all to get as much mileage as possible. Gas is expensive these days.

Ten-slot settlements are enabled automatically on the supported Feral build.
The obsolete Windows-only “Increase Slots” button and executable prompt are
hidden because the macOS runtime fix is already active before campaign Lua runs.

### What It Does

_Boring list of how this thing functions._

- Discovers Steam libraries, ATTILA, and Workshop item directories.
- Prepares ordered local type-4/movie representations in a hidden cache.
- Uses APFS clone-on-write copies, so source Workshop packs are not edited.
- Extracts the final load-order winner for each Lua path.
- Shows a checkbox and editable priority for every optional submod before each launch, so unrelated mods can be disabled and MK1212 submods can be ordered.
- Applies a narrowly guarded, memory-only ARM64 patch that changes ATTILA's two
  six-slot limits to ten for the lifetime of the launched process.
- Verifies the exact Feral executable hash, Mach-O UUID, instruction context,
  library signature, and runtime success report before treating the launch as supported.
- Hard-links the selected cached representation into the live data tree only for the supervised ATTILA session.
- Adds exact path-and-size records to Feral's filesystem manifest only while that session is active, then removes them surgically.
- Detects smaller or incomplete same-path DDS overrides.
- Applies only defined DDS transformations and refuses unknown unsafe formats.
- Keeps hash ledgers and backs up the current manifest before preparation, activation, deactivation, or uninstallation.
- Uses an isolated Feral preference home and a controlled working directory.
- Writes one diagnostic JSON record per launch.
- Rebuilds changed Workshop-source caches with progress notifications and can
  resume from a completed cache if the launcher was interrupted before saving its ledger.
- Recovers an interrupted activation the next time any launcher command runs.
- Leaves normal Steam launches vanilla while the custom launcher is inactive.

### Requirements

_I mean at least, this is what I have._

- macOS 12 or newer
- A native Feral Total War: ATTILA Steam installation
- Python 3.9 or newer
- Steam Workshop subscriptions for the MK1212 core and any optional packs you
  want to test
- Enough free space for generated packs; APFS is strongly recommended

The launcher checks `/usr/bin/python3`, Apple Silicon Homebrew, then Intel Homebrew. If none provides Python 3.9+, install Python before continuing. 

### Install From Release

_"I WANT IT AND I WANT IT NOW!"_

1. Download `MK1212_macOS-0.7.0.dmg`.
2. Drag the `MK1212 Mac Launcher` folder onto the Applications shortcut.
3. Open `/Applications/MK1212 Mac Launcher/` and run `Prepare MK1212 Mac Launcher.command`.
   This removes only the downloaded-app quarantine metadata from the launcher
   folder. Verify the DMG checksum first; the same command is documented in
   the DMG-root `Read_Me_First.txt`.
4. Open `MK1212 Mac Launcher.app` from `/Applications/MK1212 Mac Launcher/`.
5. Quit ATTILA completely before preparing a profile.
6. Inspect the discovered MK1212 core and currently enabled optional packs if
   using the command-line tools:

   ```sh
   ./bin/mk1212-mac-inspect
   ```

7. Prepare the compatibility cache:

   ```sh
   ./bin/mk1212-mac-install
   ```

8. Add the launcher app to Steam as a non-Steam game if desired. Use each checkbox to enable or disable an optional mod, and set its priority number to control submod order (1 loads first).

The launcher discovers installed Workshop packs automatically. Before each
launch, check or uncheck optional packs and set their priority numbers in the
selector; no submod-specific load-order file is required.

**Do not enable the same Workshop packs in Feral's Mod Manager when launching the game with this launcher. This launcher uses an isolated copy of Feral's preferences with mod toggles disabled.**

### Verify

_This is how the thing works and makes sure it can keep working._

Quick verification runs automatically before every launch:

```sh
./bin/mk1212-mac-verify --quick
```

Full verification recomputes Workshop source hashes:

```sh
./bin/mk1212-mac-verify
```

If Steam updates an indexed Workshop pack, the launcher offers to rebuild the
compatibility cache from the current files. Progress is written to
`rebuild-progress.log` and shown through notifications. A new combination of
already indexed submods is cached on first use; the launcher shows a notice
because this can take a few minutes.

### Uninstall

_For when you decide you should probably get off your computer and do something valuable with your life._

Quit ATTILA, then open `Uninstall MK1212 Mac Launcher.app` from the installed folder, or run:

```sh
./bin/mk1212-mac-uninstall
```

The tool first recovers any stale transient activation, backs up the then-current Feral manifest, and removes only its exact hidden cache. It never restores an old manifest wholesale over a newer installation.

### Data Locations

_This is where all the files and sh!t go._

Generated state, manifest backups, activation history, and diagnostic logs:

```text
~/Library/Application Support/MK1212 Mac Launcher
```

App error log:

```text
~/Library/Logs/MK1212 Mac Launcher/last-launch-error.log
```

Workshop-rebuild progress:

```text
~/Library/Logs/MK1212 Mac Launcher/rebuild-progress.log
```

Do not make unredacted `state.json` or diagnostic logs public. I don't want to hack you and I don't want anyone else to either.

### Safety First

_Use protection! lol jk you play TW you don't get b!tches... or dudes… idk, whatever you're into you don't get any, and I know that for a fact, on god fr fr no cap._

The tool refuses compatibility writes while ATTILA is already running. It never
writes inside the Feral `.app` or a Workshop item directory. The ten-slot change
exists only in the launched process's private memory and disappears when ATTILA
exits; the executable on disk and its Feral signature remain unchanged.

The runtime patch is intentionally fail-closed. Release 0.7.0 supports only the
ARM64 Feral 1.6.1 build `480285.103778`, whose executable SHA-256 is
`13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e`.
Any different build is refused until its offsets and instruction guards are
independently audited.

Cached files live under `TotalWarAttilaData/.mk1212-cache`; selected generated packs, loose Lua, `used_mods.txt`, and manifest entries exist in the live tree only for a custom launcher session.

Ordinary exits and handled termination signals clean up in a `finally` path.

A hard power loss or forced `SIGKILL` can leave a stale activation until the next launcher command recovers it; run `mk1212-mac-verify --quick` before a normal launch after such an interruption.

### Build From Source

_In case you want to, which I know you don't._

```sh
python3 -m unittest discover -s tests -v
./scripts/build-runtime-patch
./scripts/build-release
./scripts/build-dmg
```

Building from source also requires Apple's Xcode Command Line Tools for the
ARM64 runtime library. The build creates an ad-hoc-signed app and release
artifacts under `dist/`.
Ad-hoc signing proves bundle integrity; it is not Apple Developer ID signing or
notarization. Because this community build has no Apple Developer ID
certificate, a browser download may receive a quarantine flag and show
“Apple could not verify … free of malware.” After confirming the DMG checksum,
remove that user-download flag once and launch the app:

```sh
xattr -dr com.apple.quarantine "/Applications/MK1212 Mac Launcher"
open "/Applications/MK1212 Mac Launcher/MK1212 Mac Launcher.app"
```

Alternatively, use macOS Privacy & Security’s **Open Anyway** control after a
user-initiated launch attempt. Do not use this for an unverified copy; verify
the release checksum first.

Maintainers with a Developer ID Application certificate can set
`CODESIGN_IDENTITY="Developer ID Application: …"` while building. Eliminating
the warning for general downloads additionally requires Apple notarization and
stapling, which cannot be performed without that account and certificate.

## Give Me DMG

_In case you don't know how to download a file from a GitHub repo — which is fine, we're not all insufferable nerdcels who spend our lives in front of computers... though you're a Total War gamer which I'm not sure is much better._

[**DOWNLOAD THE LAUNCHER!!!!** (yes this is a real link, there are no lonely milfs near you, and i don't even know what an extended warranty is)](https://github.com/ausxen/MK1212_macOS/raw/refs/heads/main/dist/MK1212_macOS-0.7.0.dmg)

[Download the SHA-256 checksum](https://github.com/ausxen/MK1212_macOS/raw/refs/heads/main/dist/MK1212_macOS-0.7.0.dmg.sha256)

## Bug Reporting

_The lanternflies! They're f&cking everywhere!_

DM me on Discord `@austenballard`

I will try to keep this updated through at least mid-2027.
