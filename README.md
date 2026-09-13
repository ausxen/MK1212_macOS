# ausxen's MK1212 macOS Launcher

[_Reading is for geeks just give me the launcher_](https://github.com/ausxen/MK1212_macOS/blob/main/dist/MK1212_macOS-0.6.1.dmg)

## Table of ~~Condiments~~ Contents

1. [[#Why Tho]]
2. [[#The Boring Technical Part]]
	1. [[#Test Status & Limitations]]
	2. [[#What It Do?]]
	3. [[#Requirements]]
	4. [[#Install From Release]]
	5. [[#Verify]]
	6. [[#Uninstall]]
	7. [[#Data Locations]]
	8. [[#Safety First]]
3. [[#Build From Source]]
4. [[#Give Me DMG]]
5. [[#Bug Reporting]]

## Why Tho

If you're a contemptible, sub-human macOS gamer like me and recently started playing the Feral Interactive release of Attila, you may have been disappointed to find that the Medieval Kingdoms 1212 AD mod is not macOS-compatible.

I was not satisfied to let that status quo sit unchallenged. So I put on my equally-contemptible AI fanboy vibe-coder hat and threw together this launcher.

It keeps Steam Workshop packs byte-for-byte unchanged, does not edit or
re-sign Feral's application, and does not use any sort of Windows emulation. It makes a reversible compatibility cache beside ATTILA's data directory and activates only the selected profile while the independent `.app` supervises the genuine Feral executable.

**As of right now I cannot guarantee it will work 100% of the time or with 100% of the submods for MK1212.** Therefore, if you are using this launcher, you are effectively a beta tester. Or alpha tester, I guess, if you're sensitive about your masculinity. Either way you're a guinea pig, so find a way to cope.

Anyway now for all the boring stuff.

## The Boring Technical Part

_You should actually probably read at least the first part of this._

### Test Status & Limitations

I tested it as follows:

- Apple Silicon / ARM64
- macOS with Feral ATTILA 1.6.1, build `480285.103778`
- MK1212 Scripts, Cities, Base, Models 1–9, and Music
- Tycherious' 1212 Tweaks, Realistic Smoke, and Tycherious' 4TPY

Your mileage may vary. If it does, let me know, because I want us all to get as much mileage as possible. Gas is expensive these days.

**10-Slot Settlements _DOES NOT_ work. If anyone has a brilliant idea of how to make it work without getting a DMCA notice, let me know.**

### What It Do?

_Boring list of how this thing functions._

- Discovers Steam libraries, ATTILA, and Workshop item directories.
- Prepares ordered local type-4/movie representations in a hidden cache.
- Uses APFS clone-on-write copies, so source Workshop packs are not edited.
- Extracts the final load-order winner for each Lua path.
- Shows a checkbox and editable priority for every optional submod before each launch, so unrelated mods can be disabled and MK1212 submods can be ordered.
- Hard-links the selected cached representation into the live data tree only for the supervised ATTILA session.
- Adds exact path-and-size records to Feral's filesystem manifest only while that session is active, then removes them surgically.
- Detects smaller or incomplete same-path DDS overrides.
- Applies only defined DDS transformations and refuses unknown unsafe formats.
- Keeps hash ledgers and backs up the current manifest before preparation, activation, deactivation, or uninstallation.
- Uses an isolated Feral preference home and a controlled working directory.
- Writes one diagnostic JSON record per launch.
- Recovers an interrupted activation the next time any launcher command runs.
- Leaves normal Steam launches vanilla while the custom launcher is inactive.

### Requirements

_I mean at least, this is what I have._

- macOS 12 or newer
- A native Feral Total War: ATTILA Steam installation
- Python 3.9 or newer
- Steam Workshop subscriptions for every pack in the chosen load-order file
- Enough free space for generated packs; APFS is strongly recommended

The launcher checks `/usr/bin/python3`, Apple Silicon Homebrew, then Intel Homebrew. If none provides Python 3.9+, install Python before continuing. 

### Install From Release

_"I WANT IT AND I WANT IT NOW!"_

1. Download `MK1212_macOS-0.6.1.dmg`.
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

7. Open that app, or add it to Steam as a non-Steam game. Use each checkbox to enable or disable an optional mod, and set its priority number to control submod order (1 loads first).

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

If Steam updates a selected Workshop pack, verification will request a rebuild. 

Quit ATTILA, uninstall, then install again with the same load-order file. A new combination of already indexed submods is cached on first use; the launcher shows a notice because this can take up to a minute.

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

Do not make unredacted `state.json` or diagnostic logs public. I don't want to hack you and I don't want anyone else to either.

### Safety First

_Use protection! lol jk you play TW you don't get b!tches... or dudes... idk whatever you're into you don't get any and I know that for a fact on god fr fr no cap._

The tool refuses compatibility writes while ATTILA is already running. It never writes inside the Feral `.app` or a Workshop item directory.

Cached files live under `TotalWarAttilaData/.mk1212-cache`; selected generated packs, loose Lua, `used_mods.txt`, and manifest entries exist in the live tree only for a custom launcher session.

Ordinary exits and handled termination signals clean up in a `finally` path.

A hard power loss or forced `SIGKILL` can leave a stale activation until the next launcher command recovers it; run `mk1212-mac-verify --quick` before a normal launch after such an interruption.

### Build From Source

_In case you want to, which I know you don't._

```sh
python3 -m unittest discover -s tests -v
./scripts/build-release
```

The build creates an ad-hoc-signed app and release archive under `dist/`.
Ad-hoc signing proves bundle integrity; it is not Apple Developer ID signing or
notarization. GitHub downloads may require the user to approve the app in
macOS Privacy & Security.

## Give Me DMG

_In case you don't know how to download a file from a GitHub repo — which is fine, we're not all insufferable nerdcels who spend our lives in front of computers... though you're a Total War gamer which I'm not sure is much better._

[**DOWNLOAD THE LAUNCHER YES THIS IS A REAL LINK NOT A SCAM LINK THERE ARE NO LONELY MILFS NEAR YOU AND I DON'T EVEN KNOW WHAT AN EXTENDED WARRANTY IS**](https://github.com/ausxen/MK1212_macOS/blob/main/dist/MK1212_macOS-0.6.1.dmg)

## Bug Reporting

_The lanternflies! They're f&cking everywhere!_

DM me on Discord `@austenballard`

I will try to keep this updated through at least mid-2027.