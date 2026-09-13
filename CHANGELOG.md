# Changelog

## 0.6.1 — 2026-09-13

- Rebranded the public package as **ausxen's MK1212 macOS Launcher**.
- Added a drag-and-drop DMG distribution with a companion uninstaller app.
- Added the supplied MK1212 macOS launcher icon with Retina sizes.
- Discovered newly downloaded Workshop packs directly, even before Feral has
  recorded them in its preferences.
- Preserved optional-submod priority ahead of the MK1212 core packs.
- Added support for Tycherious' separate 4TPY pack and documented its test
  load order.

## 0.5.0 — 2026-09-11

- Replaced the persistent live compatibility layer with hidden cached profiles
  that activate only for a supervised custom-launcher session.
- Restored normal Steam/Feral launches to vanilla ATTILA.
- Added a checkbox chooser for independently enabling optional submods while
  keeping all 13 MK1212 core packs mandatory.
- Added on-demand profile caching, stale-activation recovery, per-activation
  manifest backups, and exact post-exit cleanup verification.
- Preserved highest-first published pack order and highest-priority loose-Lua
  winners when optional packs are filtered.
- Limited DDS transformations to violations of an original stock same-path
  contract; intentional mod-to-mod texture differences remain untouched.

## 0.4.0 — 2026-09-11

- Added explicit, duplicate-checked load-order files for submods.
- Added tested presets for MK1212 core and Tycherious' 1212 Tweaks plus
  Realistic Smoke.
- Built a standalone launcher app suitable for adding to Steam.
- Added ordered type-4 compatibility representations and format-aware DDS
  validation and repair overlays.
- Added source/generated-file hashing, manifest backups, diagnostic logs, full
  verification, and surgical uninstall.
