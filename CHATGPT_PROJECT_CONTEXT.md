# MK1212_macOS project context

## Project purpose

`MK1212_macOS` is the source and release repository for **ausxen's MK1212
macOS Launcher**, an independent compatibility launcher for running the
Medieval Kingdoms 1212 AD mod with Feral Interactive's macOS release of
*Total War: ATTILA*.

The project is not affiliated with or endorsed by Creative Assembly, Feral
Interactive, SEGA, Valve, or the Medieval Kingdoms 1212 AD team. The repository
must not contain proprietary game files or Steam Workshop pack content. Users
must own ATTILA and obtain mods through their authorized distribution sources.

## Current release and supported target

- Current release: `0.8.0`
- Platform: Apple Silicon / ARM64
- Minimum supported macOS: 12
- Supported game: Feral ATTILA 1.6.1, build `480285.103778`
- Supported executable SHA-256:
  `13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e`
- Python requirement: 3.9 or newer
- Release artifact: `dist/MK1212_macOS-0.8.0.dmg`

Do not claim compatibility with Intel Macs, other ATTILA builds, arbitrary
submods, or unsupported asset formats without new evidence and testing.

## How the launcher works

The launcher discovers ATTILA, subscribed MK1212 Workshop packs, and optional
submods. It creates local compatibility profiles under:

```text
TotalWarAttilaData/.mk1212-cache
```

Workshop sources remain byte-for-byte unchanged. Generated type-4/movie pack
representations, loose Lua, `used_mods.txt`, and exact Feral manifest entries
are activated only for a supervised launcher session and are removed afterward.
Normal Steam launches remain vanilla while the custom launcher is inactive.

Before each launch, a native foreground GUI lets users enable optional submods
and drag them into priority order, with highest priority at the top. The GUI
also provides Help and Rebuild Cache. Initial setup, cache rebuilding, and the
first use of a new submod combination all have foreground progress windows.
When Feral's own launcher subsequently appears, users must leave every mod
unchecked because this launcher has already activated the selected packs.

Executable compatibility is checked after any stale activation is recovered
and before cache/profile preparation. An unknown ATTILA hash must produce the
native foreground “ATTILA has been updated” explanation and stop before profile
activation, runtime injection, or process creation. A missing executable is a
distinct error. Do not conflate this with Workshop-source changes, which retain
their normal rebuild flow.

Ten-slot settlements are enabled through the bundled heap-only ARM64 runtime
patch. It observes matching settlement-slot objects and changes the relevant
heap field from six to ten. It must not write to ATTILA executable code pages,
edit the installed Feral application, or re-sign Feral's app.

## Critical regression history

Version 0.7.0 used an executable-code patch for ten-slot settlements. After a
few minutes it could cause delayed or ignored clicks followed by the rendered
game surface repeatedly scaling inside the window while hover coordinates and
keyboard input remained active. Controlled testing isolated that failure to
the old ten-slot implementation.

Version 0.8.0 replaced it with the tested heap-only implementation in
`src/mk1212_heap_slot_patch.cpp`. Extended campaign and battle testing—with
multiple ten-slot settlements and common submods—did not reproduce the input
or scaling failures.

**Never restore the obsolete code-page patch or treat it as a viable fallback.**
The obsolete `src/mk1212_slot_runtime_patch.c` was intentionally removed.

## Important safety invariants

- Fail closed on an unknown ATTILA executable hash, UUID, or guarded runtime
  condition.
- Never modify or re-sign the installed Feral `.app`.
- Never edit Workshop source packs in place.
- Refuse compatibility writes while ATTILA is running.
- Keep generated destinations under the exact ledgered cache and data roots;
  reject traversal, symlink, and unexpected-target cases.
- Back up the current Feral manifest before operations that may alter transient
  manifest state. Never restore an old manifest wholesale over a newer one.
- Ensure transient activation is cleaned in normal exits and recovered on the
  next command after interruption.
- Keep the uninstaller surgical. It removes the generated compatibility cache,
  then requests macOS authorization only to remove the exact Installer-owned
  `/Applications/MK1212 Mac Launcher` folder.
- Do not add macOS notification banners. User-visible progress belongs in the
  launcher's foreground windows and detailed status belongs in its logs.
- Do not include proprietary ATTILA or Workshop content in source, fixtures,
  diagnostics, packages, or releases.

## Submod ordering

The GUI displays optional submods in user-controlled priority order, highest
first. Generated type-4/movie filenames must preserve the intended collision
winner. This requires later movie filenames for higher-priority packs. A prior
forward-numbering implementation caused lower-priority packs to win and broke
submods such as Tycherious' 4TPY.

The tested optional set includes:

- Tycherious' 1212 Tweaks
- Realistic Smoke
- Tycherious' 4TPY

These are validation examples, not a universal compatibility guarantee.

## User-facing installation

The DMG contains `Install MK1212 Mac Launcher.pkg`, release notes, a read-me,
and the independent-project notice. The package installs:

```text
/Applications/MK1212 Mac Launcher/
├── MK1212 Mac Launcher.app
└── Uninstall MK1212 Mac Launcher.app
```

The enclosing Applications folder uses the same custom icon as the launcher.
The installer has no license-agreement page. The repository intentionally has
no software license or copyright claim; retain the independent-project notice.

The embedded apps are ad-hoc signed. The installer is not Developer ID signed
or Apple-notarized, so users may need to right-click it and choose Open or use
Privacy & Security > Open Anyway after verifying the published checksum.

## Repository map

- `src/mk1212_mac_tool.py` — discovery, cache/profile construction, validation,
  activation, launch supervision, configuration, and cleanup
- `src/mk1212_heap_slot_patch.cpp` — heap-only ten-slot runtime library
- `src/mk1212_launcher_gui.m` — native submod picker, Help, and progress windows
- `src/mk1212_uninstaller.m` — native surgical uninstaller
- `app/` — launcher and nested-app bundle metadata and icons
- `installer/` — package distribution metadata, resources, and postinstall
- `scripts/` — reproducible component, package, ZIP, and DMG build scripts
- `bin/` — source-checkout command wrappers
- `tests/test_mk1212_mac_tool.py` — automated regression tests
- `_docs/` — compatibility research, audits, diagnostics, and testing notes
- `RELEASE-NOTES-0.8.0.md` — release notes suitable for GitHub
- `dist/` — release artifacts and checksums

## Development and validation

Run the automated tests:

```sh
python3 -B -m unittest discover -s tests -v
```

Build individual native components:

```sh
./scripts/build-runtime-patch
./scripts/build-launcher-gui
./scripts/build-uninstaller
```

Build the installer package or final DMG:

```sh
./scripts/build-package
./scripts/build-dmg
```

Native builds require Apple's Xcode Command Line Tools. DMG creation uses
macOS `hdiutil`. Build scripts refuse to overwrite existing release artifacts.

Before publishing a release:

1. Run the complete automated test suite.
2. Validate all plists and the Installer distribution XML.
3. Build from the repository scripts rather than modifying an app bundle by
   hand.
4. Mount the final DMG read-only.
5. Confirm its documentation matches the repository copies.
6. Expand the packaged payload and verify both embedded app signatures.
7. Confirm the package has no license resource or license screen.
8. Confirm the installed folder retains its custom icon metadata.
9. Verify the DMG with `hdiutil verify` and check its published SHA-256 file.
10. Test installation, first-run preparation, launching, cache rebuilding, and
    native uninstallation on a real supported Mac before publishing.

## Current validated release

The staged 0.8.0 DMG was verified by mounting and expanding its package payload.
Both embedded apps passed deep strict signature verification, the custom folder
icon metadata survived packaging. The current source suite contains 49 automated
tests, including fail-closed executable-update handling.

Staged DMG SHA-256:

```text
7f156de0ce91d0ac0c8f074bb7fefda63761de8ec3aeae4056cde95320486edc
```

Rebuild and republish the checksum whenever the DMG changes; do not assume this
digest applies to later builds.

## Maintenance expectations

- Inspect the relevant source, tests, documentation, and audit notes before
  changing behavior.
- Preserve established working behavior unless a requested change requires it.
- Add or update regression tests for behavioral changes.
- Keep user-facing language clear and non-technical where possible.
- Keep README, Help text, installer text, release notes, and build scripts in
  sync.
- Treat local game files, user paths, saves, logs, and Workshop content as
  private. Never commit absolute personal paths or unredacted diagnostics.
- Do not publish, upload, tag, or create a GitHub release without explicit user
  authorization.
