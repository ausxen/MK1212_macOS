# ausxen's MK1212 macOS Launcher

Experimental native-macOS compatibility launcher for Medieval Kingdoms 1212 AD
on Feral Interactive's current Total War: ATTILA release.

It keeps Steam Workshop packs byte-for-byte unchanged, does not edit or
re-sign Feral's application, and does not use Wine. Instead it creates a
reversible compatibility cache beside ATTILA's data directory and activates
only the selected profile while the independent `.app` supervises the genuine
Feral executable.

## Test status

Version 0.6.1 was tested on:

- Apple Silicon / ARM64
- macOS with Feral ATTILA 1.6.1, build `480285.103778`
- MK1212 Scripts, Cities, Base, Models 1–9, and Music
- Tycherious' 1212 Tweaks with Realistic Smoke; the separate 4TPY utility is
  packaged and ready for community testing

Campaigns and battles loaded in the 13-pack core configuration and the 15-pack
Tycherious configuration. The separate 4TPY pack has been inspected and its
same-path Lua override is preserved by the launcher, but still needs an
in-game community test. A 14-pack core-plus-Realistic-Smoke configuration
also reached MK1212 after disabling Tycherious in the new chooser. Normal
Steam/Feral launches reached vanilla ATTILA before and after launcher use.

Other Macs, game builds, languages, file systems, and submods are experimental.
Back up important saves before testing.

## What it does

- Discovers Steam libraries, ATTILA, and Workshop item directories.
- Prepares ordered local type-4/movie representations in a hidden cache.
- Uses APFS clone-on-write copies, so source Workshop packs are not edited.
- Extracts the final load-order winner for each Lua path.
- Shows ordinary checkboxes for optional submods before every launch.
- Hard-links the selected cached representation into the live data tree only
  for the supervised ATTILA session.
- Adds exact path-and-size records to Feral's filesystem manifest only while
  that session is active, then removes them surgically.
- Detects smaller or incomplete same-path DDS overrides.
- Applies only defined DDS transformations and refuses unknown unsafe formats.
- Keeps hash ledgers and backs up the current manifest before preparation,
  activation, deactivation, or uninstallation.
- Uses an isolated Feral preference home and a controlled working directory.
- Writes one diagnostic JSON record per launch.
- Recovers an interrupted activation the next time any launcher command runs.
- Leaves normal Steam launches vanilla while the custom launcher is inactive.

## Requirements

- macOS 12 or newer
- A native Feral Total War: ATTILA Steam installation
- Python 3.9 or newer
- Steam Workshop subscriptions for every pack in the chosen load-order file
- Enough free space for generated packs; APFS is strongly recommended

The launcher checks `/usr/bin/python3`, Apple Silicon Homebrew, then Intel
Homebrew. If none provides Python 3.9+, install Python before continuing.

## Install from a release

1. Download `ausxen-MK1212-macOS-launcher-0.6.1.dmg`.
2. Drag the `MK1212 Mac Launcher` folder onto the Applications shortcut.
3. Open `MK1212 Mac Launcher.app` from `/Applications/MK1212 Mac Launcher/`.
4. Quit ATTILA completely before preparing a profile.
5. Inspect the intended pack graph if using the command-line tools:

   ```sh
   ./bin/mk1212-mac-inspect --load-order-file config/load-orders/mk1212-core.txt
   ```

6. Prepare the compatibility cache:

   ```sh
   ./bin/mk1212-mac-install --load-order-file config/load-orders/mk1212-core.txt
   ```

7. Open that app, or add it to Steam as a non-Steam game. Use its checkboxes to
   enable or disable optional submods for each launch.

To make Tycherious' 1212 Tweaks, Realistic Smoke, and the separate 4TPY utility
available in the chooser, use this file in both commands:

```text
config/load-orders/tycherious-1212-4tpy.txt
```

Do not enable the same Workshop packs in Feral's Mod Manager while using the
generated layer. The independent launcher uses an isolated copy of Feral's
preferences with mod toggles disabled.

## Verify

Quick verification runs automatically before every launch:

```sh
./bin/mk1212-mac-verify --quick
```

Full verification recomputes Workshop source hashes:

```sh
./bin/mk1212-mac-verify
```

If Steam updates a selected Workshop pack, verification will request a rebuild.
Quit ATTILA, uninstall, then install again with the same load-order file. A new
combination of already indexed submods is cached on first use; the launcher
shows a notice because this can take up to a minute.

## Uninstall

Quit ATTILA, then open `Uninstall MK1212 Mac Launcher.app` from the installed
folder, or run:

```sh
./bin/mk1212-mac-uninstall
```

The tool first recovers any stale transient activation, backs up the then-current
Feral manifest, and removes only its exact hidden cache. It never restores an
old manifest wholesale over a newer installation.

## Custom submod order

Create a UTF-8 text file containing one bare `.pack` filename per line. The
first line is the top of the published launcher order. Blank lines and comments
beginning with `#` are allowed.

Always inspect before installing. Installation stops if a listed pack is
missing, duplicated, or introduces an unsafe DDS override the tool cannot
transform safely.

## Data locations

Generated state, manifest backups, activation history, and diagnostic logs:

```text
~/Library/Application Support/MK1212 Mac Launcher
```

App error log:

```text
~/Library/Logs/MK1212 Mac Launcher/last-launch-error.log
```

Do not publish an unredacted `state.json` or diagnostic log. Local paths may
contain your macOS username. Follow [the testing guide](docs/TESTING.md) when
filing a report.

## Safety boundaries

The tool refuses compatibility writes while ATTILA is already running. It never
writes inside the Feral `.app` or a Workshop item directory. Cached files live
under `TotalWarAttilaData/.mk1212-cache`; selected generated packs, loose Lua,
`used_mods.txt`, and manifest entries exist in the live tree only for a custom
launcher session. Ordinary exits and handled termination signals clean up in a
`finally` path. A hard power loss or forced `SIGKILL` can leave a stale
activation until the next launcher command recovers it; run
`mk1212-mac-verify --quick` before a normal launch after such an interruption.

## Build from source

```sh
python3 -m unittest discover -s tests -v
./scripts/build-release
```

The build creates an ad-hoc-signed app and release archive under `dist/`.
Ad-hoc signing proves bundle integrity; it is not Apple Developer ID signing or
notarization. GitHub downloads may require the user to approve the app in
macOS Privacy & Security.

## Project status

This is an early community-testing release. Intel Mac validation, non-English
Feral manifests, non-APFS Steam libraries, and automatic dependency metadata
for submods remain open areas. See [compatibility notes](docs/COMPATIBILITY.md) and
[contribution guidance](CONTRIBUTING.md).
