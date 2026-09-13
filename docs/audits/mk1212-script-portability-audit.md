# MK1212 Lua portability audit

Date: 2026-09-11

Scope: the effective core MK1212 Lua set used by the local macOS launcher.
No Workshop file was changed and no embedded executable was run.

## Evidence baseline

- **Confirmed:** `1-1212scripts.pack` is byte-identical to the pack examined on
  Windows: SHA-256
  `3ffe61270c953602783fcfde4723abf1d5bc698b958ef618f329d2e5b6369255`.
- **Confirmed:** that pack contains 154 `.lua` entries. The effective core
  profile contains 155 because Base contributes
  `lua_scripts/export_ancillaries.lua`.
- **Confirmed:** all 155 effective files were inventoried. All calls involving
  `os`, `io`, `package`, native payload names, path separators, and frontend or
  campaign UI geometry were searched; every resulting executable-code hit was
  inspected manually.
- **Confirmed:** there are 46 executable `Resize` calls across 11 scripts, 84
  `MoveTo` calls, and 53 geometry-query calls. None of the original 46 resize
  calls supplies the optional child-resize argument.

## Principal conclusions

### 1. Ten building slots is genuinely Windows-native

Status: **confirmed hard blocker**

Files:

- `campaigns/main_attila/mk1212_slots.lua`
- `lua_scripts/slots_binaries.lua`
- `lua_scripts/frontend_disclaimer.lua` (duplicate frontend implementation,
  currently not required by `frontend_scripted.lua`)

The campaign-side Lua and UI listeners are portable. The operation that raises
the hardcoded slot limit is not. `ModifyHardcodedLimits()` reconstructs
`MK1212_10slots.exe` in the working directory and invokes it with
`os.execute()`.

The embedded payload was reconstructed in a temporary audit directory and
inspected without execution:

- SHA-256:
  `90dd406a1131d642829e95b7c7fe696122df62f478aa38de2a2c3305fd48e987`
- Size: 10,240 bytes
- Format: PE32 console executable, Intel 80386, Windows
- Imports/strings include `OpenProcess`, `GetProcessId`,
  `ReadProcessMemory`, `WriteProcessMemory`, `GetWindowThreadProcessId`,
  `KERNEL32.dll`, and `USER32.dll`.

This is a Windows process-memory patcher, not merely a Lua script with a bad
path. It cannot patch the native ARM64 Feral process as written. The correct
macOS solution must first determine the semantic limit changed by the Windows
program, then reproduce it without altering or re-signing the Feral app. Until
that is understood, the Mac shim should intercept the button action and must
not emit or attempt to run the PE file.

### 2. Change Capital is also genuinely Windows-native

Status: **confirmed hard blocker, feature-local**

Files:

- `campaigns/main_attila/mk1212_change_capital.lua`
- `lua_scripts/change_capital_binaries.lua`

The Lua creates `faction_capital_change.exe` plus a .NET configuration file,
runs the executable with a region-array argument, and then quick-loads the
changed save.

The embedded executable was inspected without execution:

- SHA-256:
  `fec2367070ed18dfd3d15b5923ec359e9144ff46925b60c195302da3167e775b`
- Size: 87,040 bytes
- Format: PE32 Intel 80386 Mono/.NET console assembly for Windows
- Embedded names indicate ESF/save-file parsing and rewriting.

This feature is a better candidate than ten slots for a launcher-supervised,
cross-platform helper: Lua can write a narrowly scoped request, a native helper
can back up and transform the save, and Lua can quick-load only after a success
response. The binary format and transformation still need to be reverse
engineered and validated before implementation.

### 3. Custom-battle faction-menu expansion is not Windows-native

Status: **strongly inferred Feral UI compatibility defect**

File: `lua_scripts/frontend_scripted.lua`, approximately lines 153-216.

The code resizes `popup_menu` to a fixed 225 pixels per column and 30 pixels per
row, then manually moves every faction option. It calls `Resize(width, height)`
on a parent containing `popup_list`, leaving child resizing implicit. This is
the same hazardous pattern that compressed the campaign faction-description
children. It also relies on two fixed callbacks and a delay derived from child
count.

Likely first repair:

1. preserve the popup's children with `Resize(width, height, false)`;
2. derive row width/height from an actual option component where possible;
3. log bounds before and after the delayed relayout;
4. test at multiple display scales and with the full faction set.

This should be the next controlled UI test. It is likely fixable in the same
compatibility-transform layer as the confirmed faction-description repair.

## Other confirmed Windows assumptions

| Priority | Script | Finding | Expected impact | Status |
|---|---|---|---|---|
| High | `lua_scripts/frontend_cb_crash_fix.lua` | Builds army-setup and battle-preference paths from `APPDATA` plus Windows backslashes, then removes files. | A nil or unmapped `APPDATA` can break its first-run callback; incorrect mapping risks deleting the wrong preference files. | **Unverified on a clean Feral state.** Feral contains an APPDATA/VFS compatibility layer, so this may already work. |
| High | `campaigns/main_attila/ironman/ironman.lua` | Renames and replaces saves through `APPDATA\\The Creative Assembly\\Attila\\save_games`. | Non-Legendary Ironman autosave renaming may fail or target the wrong location. | **Unverified; requires copied-save testing.** |
| Medium | `campaigns/main_attila/mechanics/hre/mechanics_hre.lua` | `DebugLog()` writes to a developer-specific `C:\\Users\\mitch\\...` path and is called throughout active HRE logic. | Gameplay continues, but logging is misplaced and creates an unwanted file. | **Confirmed on this Mac.** A literal 35,607-byte filename beginning `C:\\Users\\mitch` was created in `TotalWarAttilaData`. |
| Low | `lua_scripts/frontend_discord.lua` | Uses Windows shell command `start https://...`. | Frontend Discord button cannot open the link correctly. | **Confirmed Windows-specific.** |
| Low | `campaigns/main_attila/mk1212_discord.lua` | Uses the same Windows `start` command. | Campaign Discord button cannot open the link correctly. | **Confirmed Windows-specific.** |
| Low/dormant | `lua_scripts/dev.lua` | Contains `IF NOT EXIST ... ( mkdir ... )`. | None with the current hardcoded `fileMethod = "preface"`; the Windows branch is not executed. | **Confirmed dormant.** |
| None/current | `lua_scripts/frontend_pack_check.lua` | Contains an APPDATA/Kaedrin path only inside a comment. Its active code reads relative `used_mods.txt`. | The active portion works with the launcher's generated mod list. | **Confirmed not an active Windows dependency.** |
| Dormant | `lua_scripts/frontend_disclaimer.lua` | Contains the frontend copy of the ten-slot PE extraction and execution path. | No current frontend impact because its `require` is commented out. | **Confirmed dormant but unsafe if re-enabled.** |

## Feral-sensitive UI candidates

Status for this section: **potential compatibility risk unless separately
marked confirmed**. Fixed coordinates are not inherently Windows-specific, but
parent resizing with implicit child propagation and absolute screen positions
can behave differently under Feral's display scaling and older UI runtime.

### Highest priority

- `lua_scripts/frontend_scripted.lua`
  - Custom-battle faction-menu expansion: parent resize plus manual grid.
  - Campaign faction panel: two parent resizes. **Confirmed fixed locally** by
    explicitly setting child propagation to false.
  - Strength/weakness, population, difficulty, faction icon, and faction list
    positions are all hardcoded relative to the leader window.
- `campaigns/main_attila/mechanics/hre/mechanics_hre_ui.lua`
  - 6 resizes and 28 moves, including `settlement_captured`, `button_parent`,
    `panReformsView`, and a dynamically sized vote bar.
- `campaigns/main_attila/mechanics/decisions/mechanics_decisions_ui.lua`
  - 8 resizes and 16 moves, including parchment/panel parents and dynamically
    created decision controls.
- `campaigns/main_attila/common/ui/mk1212_unit_information.lua`
  - Resizes `info_panel_background`, which is likely a container, and manually
    moves it.

### Medium priority

- `lua_scripts/frontend_changelog.lua`
- `lua_scripts/frontend_mp_campaign.lua`
- `lua_scripts/frontend_pack_check.lua`

Each resizes a nested event/popup hierarchy at three levels and then moves text
and buttons with fixed offsets. These should receive explicit child-resize
arguments after their current behavior is captured.

- `campaigns/main_attila/mechanics/pope/mechanics_pope_ui.lua`
- `campaigns/main_attila/ironman/ironman_achievements_ui.lua`

These combine fixed-size icons or progress bars with custom component trees;
they should be visually tested but are less similar to the confirmed failure.

### Lower priority

- `campaigns/main_attila/mechanics/population/mechanics_population_ui.lua`
- `campaigns/main_attila/common/ui/mk1212_occupation_decisions.lua`

Most resized targets appear to be leaf text or image components, so implicit
child propagation is less likely to matter.

## Relative-path and state behavior

- **Confirmed:** the launcher's data-directory working directory allows the
  active scripts to create `MK1212_config.txt`, `MK1212_achievements`, and
  `MK1212_log.txt` in `TotalWarAttilaData`.
- **Confirmed:** those files remain after a supervised launch because they are
  runtime outputs, not transient profile inputs. They do not load MK1212 during
  vanilla operation, but they should eventually be redirected or explicitly
  ledgered for surgical uninstall.
- **Confirmed:** the hardcoded HRE debug path is treated as a literal filename
  on this installation rather than as the intended Windows user path.
- **Strongly inferred:** Feral's compatibility layer maps its own synthetic
  Windows paths such as APPDATA into `VFS/User/AppData`; hardcoded paths for an
  unrelated Windows username fall outside that mapping.

## Require/search-path findings

- **Confirmed:** no internal mod-to-mod `require` was found whose only match
  differed by filename case.
- **Confirmed:** unresolved static names are stock/runtime modules or a dynamic
  achievement path, not missing effective MK1212 files.
- **Confirmed:** the campaign script extends `package.path` with forward-slash
  paths, which is portable in the Feral runtime once the loose Lua files are
  visible through the manifest.
- **Potential risk:** frontend `package.path` replaces rather than appends the
  previous value. It currently succeeds with the launcher and is therefore not
  a present blocker, but future submods may assume the original search path is
  retained.

## Recommended repair/test order

1. **Custom-battle faction selector:** A/B test `popup_menu:Resize(..., false)`
   and capture popup/list/option bounds.
2. **Ten slots:** prevent PE extraction/execution on macOS; reverse engineer the
   precise memory values and locate an allowed native or data-driven mechanism.
3. **APPDATA probe:** log the actual Lua-visible environment value and resolve
   a harmless known preference path on a fresh isolated Feral state.
4. **Ironman:** test rename/delete behavior only against copied disposable save
   files.
5. **Change Capital:** document the exact ESF delta on Windows, then prototype a
   launcher-supervised native transformation with automatic save backup.
6. **HRE logging:** redirect to launcher state or disable release logging.
7. **Remaining UI screens:** add geometry logging and test the high-priority UI
   candidates at more than one resolution/scale before applying broad edits.

## What should not be done

- Do not attempt to run either embedded Windows executable through Wine.
- Do not patch or re-sign the Feral application.
- Do not mass-rewrite all 46 `Resize` calls to add `false`; leaf controls and
  deliberate child scaling must be distinguished from container bugs.
- Do not translate every backslash blindly. Feral provides a synthetic Windows
  filesystem layer, so each path must first be tested against the runtime's
  actual APPDATA value and VFS mapping.
- Do not test Ironman or Change Capital against the only copy of a save.
