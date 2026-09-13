# Total War: ATTILA / MK1212 Windows launch and mod-loading evidence

## Scope and evidence standard

This report documents one Windows installation of Steam App ID `325610` on 2026-09-10. It is intended as an empirical reference for a separate macOS comparison. It does not propose a macOS fix.

Evidence labels:

- **Confirmed** — directly observed in installed files, Process Monitor, process metadata, or the operator-visible game UI.
- **Strong inference** — the combined observations admit a clear technical explanation, but the engine's internal virtual-file-system code was not instrumented.
- **Unverified hypothesis** — plausible but not demonstrated here.

No Workshop pack was modified. The launcher mod-enable JSON was backed up, temporarily changed for the controlled cases, and restored byte-for-byte from that backup after testing. At completion the launcher again showed 13 active Attila mods. A generated 124-byte `used_mods.txt` from the forced-close Scripts-only test remains in the game root; it was not deleted because the investigation prohibited destructive changes. The launcher normally deletes/replaces this transient file when launching.

## Executive findings

1. **Confirmed:** Steam starts the Creative Assembly Electron launcher, not `attila.exe` directly. The launch tree is:

   ```text
   steam.exe
   └─ launcher.exe                  (Electron main process)
      └─ launcher.exe --type=renderer
         └─ attila.exe
   ```

   The Electron renderer is the immediate parent that creates `attila.exe`. Steam remains an ancestor. Both launcher processes exit just after game creation; neither relaunches itself as the game.

2. **Confirmed:** Vanilla and modded launches differ at the Attila command line:

   ```text
   Vanilla: "...\attila.exe" 
   Modded:  "...\attila.exe"  used_mods.txt;
   ```

3. **Confirmed:** For a modded launch, the launcher writes `used_mods.txt` in the Attila installation root, starts the game with `used_mods.txt;`, and Attila reads that file. The game's current directory is the installation root, so the relative filename resolves correctly.

4. **Confirmed:** `used_mods.txt` contains two ordered blocks: one `add_working_directory "<absolute Workshop item directory>";` line per enabled item, then one `mod "<bare pack filename>";` line per item. Full MK1212 used 13 of each. Scripts-only used one of each.

5. **Confirmed:** Attila opens Workshop `.pack` files directly from their subscribed item directories. The first successful open of each of the 13 packs matched launcher order exactly.

6. **Confirmed:** There are no loose `.lua` files under the Attila installation, the App ID 325610 Workshop tree, or `%APPDATA%\The Creative Assembly\Attila`. The Scripts pack itself contains 154 Lua files.

7. **Confirmed:** During the successful full-MK launch, Attila attempted operating-system lookups for loose Lua under `%APPDATA%\...\Attila\maps`, installation `data`, and each enabled Workshop directory in load order. Those lookups failed; no loose Lua open succeeded.

8. **Strong inference:** Windows executes Lua from the mounted pack virtual filesystem. This follows from the absence of loose Lua, successful direct opening of `1-1212scripts.pack`, visible successful full-MK frontend, and the pack's internal Lua paths. Individual archive-member reads are not exposed to Process Monitor as separate filesystem paths, so this is not claimed as direct per-file tracing.

9. **Confirmed:** The Scripts-only control generated the correct single-pack list and opened only `1-1212scripts.pack`, but the game remained frozen at the splash screen. This is an observed outcome, not a diagnosis; that component is not a complete playable mod by itself.

## System, installation, and build

| Item | Observed value |
|---|---|
| Windows | Windows 10 Home 22H2, `10.0.19045.2965`, x64 OS |
| Steam root/library | `C:\Program Files (x86)\Steam` |
| App manifest | `C:\Program Files (x86)\Steam\steamapps\appmanifest_325610.acf` |
| Attila root | `C:\Program Files (x86)\Steam\steamapps\common\Total War Attila` |
| Attila executable | `C:\Program Files (x86)\Steam\steamapps\common\Total War Attila\attila.exe` |
| Launcher | `C:\Program Files (x86)\Steam\steamapps\common\Total War Attila\launcher\launcher.exe` |
| Workshop root | `C:\Program Files (x86)\Steam\steamapps\workshop\content\325610` |
| Scripts item | `...\325610\1934544571\1-1212scripts.pack` |
| Steam app build ID | `24237927` |
| Manifest SizeOnDisk | `24,850,232,855` bytes |
| `attila.exe` | file `1.6.0.0`, product `3.2.1.0`, 598,016 bytes, 32-bit process |
| `launcher.exe` | file `3.25.3`, product `3.25.3.0`, 49,625,224 bytes, 32-bit process |

`libraryfolders.vdf` contained only library index 0 at the Steam path above and associated App ID 325610 with it. The Steam uninstall registry record was present under the usual `Steam App 325610` key and pointed to `steam://uninstall/325610`; no mod list was found in the registry.

The local Steam application configuration had no custom `LaunchOptions` value for 325610. This distinguishes the observed `used_mods.txt;` argument from a user-supplied Steam launch option.

Hashes and the complete Workshop inventory are in `installation-binaries.csv` and `workshop-packs.csv`. The Scripts pack SHA-256 is recorded there.

## Controlled cases

| Case | Enabled representation | Attila command | Workshop opens | Outcome |
|---|---|---|---|---|
| Full MK1212 | 13 active entries, order 1–13 | `attila.exe  used_mods.txt;` | 13 packs, exact launcher order | MK1212 menu reached; normal exit |
| Vanilla | all 13 inactive | `attila.exe` | none | Vanilla pre-menu videos/menu observed; normal exit |
| Scripts only | only item 1934544571 active | `attila.exe  used_mods.txt;` | only `1-1212scripts.pack` | froze at splash; process ended after capture |

The vanilla conclusion has two independent observations: the operator saw the vanilla videos and vanilla menu, and Process Monitor recorded no Workshop pack open. A 13-pack `used_mods.txt` copied during the transition into that test had an earlier timestamp belonging to the preceding full-MK run and was not passed to or opened by the vanilla game. It is not treated as vanilla-load evidence.

## Process tree, command lines, and lifetime

The process IDs changed per run; the structure did not.

### Full MK1212 example

| Process | PID / parent | Start UTC | End UTC | Command |
|---|---:|---|---|---|
| Steam | 11404 / 11700 | 15:51:50.440845 | remained running | `"C:\Program Files (x86)\Steam\steam.exe" -silent` |
| launcher main | 14224 / 11404 | 16:34:38.616718 | 16:34:54.365634 | `"...\launcher\launcher.exe"` |
| launcher renderer | 13032 / 14224 | 16:34:39.500303 | 16:34:54.401946 | Electron renderer command, including `--type=renderer`, `--app-path=...\app.asar`, and `--preload=...\preload.js` |
| Attila | 14064 / 13032 | 16:34:53.723988 | 16:36:29.670926 | `"...\attila.exe"  used_mods.txt;` |

The renderer's complete captured command line is retained in the sanitized `*-processes.json` files. Ephemeral Electron IPC token values are redacted.

The renderer issued the Attila `Process Create` at `16:34:53.723989Z`; the Attila `Process Start` followed at `16:34:53.724002Z`. The launcher processes exited about 0.64–0.68 seconds later. Thus Steam is an ancestor but not Attila's direct parent during these launches.

### Working directory and environment

For all three Attila processes, Process Monitor directly recorded:

```text
Current directory: C:\Program Files (x86)\Steam\steamapps\common\Total War Attila\
PROCESSOR_ARCHITECTURE=x86
SteamClientLaunch=1
SteamGameId=325610
SteamAppId=325610
SteamOverlayGameId=325610
SteamEnv=1
SteamPath=C:\Program Files (x86)\Steam
APPDATA=%USERPROFILE%\AppData\Roaming
LOCALAPPDATA=%USERPROFILE%\AppData\Local
TEMP/TMP=%USERPROFILE%\AppData\Local\Temp
MESA_*_CACHE_DIR=C:\Program Files (x86)\Steam\steamapps\shadercache\325610
```

The sanitized PATH and per-case data are in `*-process-context.json`. Steam credentials, Steam account IDs, user/computer names, unrelated environment variables, and authentication data were excluded. Launcher current directories and full environments were not separately recovered, so they remain unverified.

## How the launcher represents and passes mods

### Persistent selection

The authoritative launcher file observed here was:

```text
%APPDATA%\The Creative Assembly\Launcher\20190104-moddata.dat
```

It is JSON. Each Attila record includes `uuid` (pack filename), `order`, `active`, `game`, absolute `packfile`, `name`, category, and ownership metadata. Sanitized state snapshots for all three cases are included.

Electron Local Storage contained `mod-reordered.attila=TRUE`. Static inspection of the installed launcher shows that, when this is true, `activeModsForGame("attila")` filters to active records and sorts on numeric `order`; otherwise it sorts on `uuid`. The ordered result maps to each absolute `packfile` and is passed to the native `playWithMods` call.

Installed launcher game metadata states:

```json
{
  "exe": "attila.exe",
  "app_data_dir": "Attila",
  "app_ids": [325610, 315700],
  "supports_mod_manager": true,
  "supports_continue": true,
  "supports_dx12": false
}
```

The installed `steam.service` calls:

```text
playWithMods(targetAppId, exe, app_data_dir, flags, orderedMods, launcherArgs)
```

Attila's normal modded-play flags evaluate to 4 (`FLAG_OUTDATED_MODS`); Attila is marked as not supporting DX12. This value is an installed-launcher static finding rather than a Process Monitor field.

### Transient `used_mods.txt`

For the full run, the launcher successfully wrote a 1,613-byte file in the Attila root, then created the game about 6.4 ms later. Attila read the same file. Its exact sanitized content is supplied as `03-full-mk1212-used_mods.txt`.

The ordering was:

1. Scripts — 1934544571
2. Custom cities — 3010246623
3. Base pack — 1429109380
4. Models 1 — 1429140619
5. Models 2 — 1371434091
6. Models 3 — 1371420895
7. Models 4 — 1371491650
8. Models 5 — 1592154821
9. Models 6 — 1934591700
10. Models 7 — 2221976170
11. Models 8 — 2660365008
12. Models 9 — 3003589041
13. Music — 1582067661

All 13 `add_working_directory` lines precede all 13 `mod` lines. Direct binary-string inspection of the installed native launcher module independently found format strings `add_working_directory "%1";`, `mod "%1";`, `used_mods.txt`, `/tmp_args.txt`, and `Found arguments file in %1`. No `tmp_args.txt` existed or was observed in these runs.

Scripts-only produced:

```text
add_working_directory "C:/Program Files (x86)/Steam/steamapps/workshop/content/325610/1934544571";
mod "1-1212scripts.pack";
```

Vanilla received no argument, generated no mod list for consumption, and opened no Workshop pack.

## Pack opening and `manifest.txt`

Attila opened and read installation `data\manifest.txt` before opening Workshop packs in all cases. This 32,244-byte vanilla manifest maps virtual relative asset names to sizes, including installation packs; it is supplied unchanged as `vanilla-data-manifest.txt`. It is not a generated mod manifest and it does not enumerate enabled Workshop packs.

In the full case, first successful Workshop pack `CreateFile` events occurred from `16:34:55.337698Z` through `16:34:55.397692Z`, in the exact 13-item order listed above. The Scripts pack opened first. The detailed order and event indices are in `workshop-pack-open-order.csv`; the interleaved installation and Workshop pack order is in `all-pack-first-open-order.csv`.

In the Scripts-only case, the only successful Workshop pack path was:

```text
C:\Program Files (x86)\Steam\steamapps\workshop\content\325610\1934544571\1-1212scripts.pack
```

Vanilla successfully opened 20 distinct installation `data` packs and zero Workshop packs; Scripts-only opened those installation packs plus the Scripts pack; full MK opened the installation set plus all 13 Workshop packs.

## Scripts pack internals and Lua resolution

The Scripts pack was inspected read-only. Raw header observations:

```text
signature = PFH4
pack_type = 3
flags = 0
file_count = 1589
index_size = 81585
pack_bytes = 343198063
```

The complete member index is `scripts-pack-index.csv`. It contains 154 `.lua` members:

| Internal root | Lua count |
|---|---:|
| `campaigns\...` | 137 |
| `lua_scripts\...` | 16 |
| `script\...` | 1 |

Representative exact internal paths include:

```text
lua_scripts\frontend_scripted.lua
lua_scripts\frontend_pack_check.lua
campaigns\main_attila\scripting.lua
campaigns\main_attila\mk1212_start.lua
campaigns\main_attila\common\main.lua
campaigns\main_attila\mechanics\main.lua
script\_lib\lib_event_handler.lua
```

No internal `manifest.txt`, `user.script.txt`, or `used_mods.txt` member exists.

### Observed path behavior

There were no loose `.lua` files anywhere in the installation root, Workshop 325610 tree, or Attila AppData tree. During full MK startup, all 1,410 recorded operating-system events whose path ended in `.lua` were non-successes:

| Result | Count |
|---|---:|
| `PATH NOT FOUND` | 1,044 |
| `NAME NOT FOUND` | 96 |
| `FAST IO DISALLOWED` | 270 |

For a representative name such as `lua_scripts\frontend_scripted.lua`, Attila probed in this order:

1. `%APPDATA%\The Creative Assembly\Attila\maps\lua_scripts\frontend_scripted.lua`
2. `...\Total War Attila\data\lua_scripts\frontend_scripted.lua`
3. each enabled Workshop item directory plus `\lua_scripts\frontend_scripted.lua`, in mod order

Every loose lookup failed, including the apparent filesystem path beneath item 1934544571. That failure does not mean the member is absent: it is inside the pack, not loose beside it. Process Monitor sees the outer pack handle, while the engine's archive reads occur through that handle.

`script\_lib` showed the same scheme for compiled candidates such as `script\_lib\lib_header.luac`: AppData maps, installation data, and each working directory were probed. `data\campaigns\main_attila` itself exists as a directory and was enumerated, while MK1212's Lua files under that virtual root reside in the pack.

### `require()` and package roots inside the pack

The pack's frontend entry explicitly replaces `package.path` with:

```lua
package.path = ";?.lua;data/ui/templates/?.lua;data/ui/?.lua"
require "data.lua_scripts.all_scripted"
require("lua_scripts.fe_script_header")
require("lua_scripts/frontend_pack_check")
```

It uses both dot and slash module spellings. The campaign entry appends:

```lua
package.path = package.path .. ";data/campaigns/" .. campaign_name .. "/?.lua"
package.path = package.path .. ";data/campaigns/" .. campaign_name .. "/factions/?.lua"
```

and then calls modules relative to the `campaigns/main_attila` virtual root, including:

```lua
require("mk1212_start")
require("common/main")
require("mechanics/main")
```

The internal `script\_lib\lib_event_handler.lua` calls `require("lua_scripts/dev")`. The extracted call inventory is in `scripts-pack-require-calls.csv` (textual occurrences include a small number of commented calls).

The MK1212 `frontend_pack_check.lua` itself uses `util.fileExists("used_mods.txt")` and `io.open("used_mods.txt", "r")`. Because Attila's current directory is the installation root, this relative access resolves to the launcher-generated file there. It reads that list to warn about missing or misordered packs; it is not the mechanism that initially mounts the packs.

### Interpretation boundary

- **Confirmed:** the pack contains these Lua members; there are no loose copies; full MK opens the pack; loose Lua probes fail; full MK reaches its modified frontend.
- **Strong inference:** Attila's VFS satisfies the script/module load from the already-mounted PFH4 pack and presents members under logical `data`, `lua_scripts`, `campaigns/main_attila`, and `script/_lib` roots.
- **Unverified:** the exact internal precedence rules when two mounted packs provide the same virtual Lua member were not tested with a deliberately conflicting submod.

## Generated configuration, logs, and changed files

Observed AppData roots:

```text
%APPDATA%\The Creative Assembly\Attila
%APPDATA%\The Creative Assembly\Launcher
```

No `user.script.txt` was present anywhere under `%APPDATA%\The Creative Assembly` before, during, or after the tests. The relevant persistent files were:

- `Attila\scripts\preferences.script.txt` — standard game settings; sanitized copy included.
- `Attila\logs\gfx.log.txt` — GPU selection summary; copy included.
- `Attila\logs\modified.log` — zero bytes after the Scripts-only attempt.
- `Launcher\20190104-moddata.dat` — persistent mod activation and order.
- `Launcher\launcher.log` — confirms Attila connection, Mod Manager initialization, and “Mods Enabled,” but does not replace the process/file evidence for the actual argument list.
- Launcher Electron Local Storage — held `mod-reordered.attila=TRUE` and `dxVersion-attila=dx11`.

Per-case writes under the two AppData roots are summarized in `changed-config-paths.csv`. Attila commonly wrote preferences, GPU log, UI cache, event metrics, and advice history. The launcher wrote its moddata JSON, log, cache, and LevelDB storage. No registry-based mod list was observed.

## Exact capture and analysis commands

The workspace path is parameterized only to avoid embedding the Windows account name:

```powershell
$caseRoot = '<workspace>\i-am-investigating-why-medieval-kingdoms'
$steam = 'C:\Program Files (x86)\Steam'
$game = "$steam\steamapps\common\Total War Attila"
$workshop = "$steam\steamapps\workshop\content\325610"
$python = '<bundled-python>\python.exe'
```

Core discovery and static inspection:

```powershell
Get-Content "$steam\steamapps\libraryfolders.vdf" -Raw
Get-Content "$steam\steamapps\appmanifest_325610.acf" -Raw
Get-Item "$game\attila.exe","$game\launcher\launcher.exe" | Select FullName,Length,VersionInfo
Get-ChildItem $workshop -Directory | ForEach-Object { Get-ChildItem $_.FullName -Filter '*.pack' }
Get-ChildItem "$env:APPDATA\The Creative Assembly" -Recurse -Filter 'user.script.txt'
rg --files $game $workshop "$env:APPDATA\The Creative Assembly\Attila" | Where-Object { $_ -match '(?i)\.lua$' }
```

Process Monitor was obtained from the official [Microsoft Sysinternals Process Monitor page](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon). Captures used:

```powershell
& "$caseRoot\work\ProcessMonitor\Procmon64.exe" /AcceptEula /Quiet /Minimized `
  /LoadConfig "$caseRoot\work\procmon-attila-filter.pmc" `
  /BackingFile "$caseRoot\work\captures\<case>\trace.pml"
& "$caseRoot\work\ProcessMonitor\Procmon64.exe" /Terminate /AcceptEula
```

Controlled launcher states and restoration:

```powershell
& $python "$caseRoot\work\set_launcher_mod_case.py" `
  "$env:APPDATA\The Creative Assembly\Launcher\20190104-moddata.dat" `
  "$caseRoot\work\backups\20190104-moddata.original.dat" vanilla `
  "$caseRoot\outputs\01-vanilla-mod-state.json"

& $python "$caseRoot\work\set_launcher_mod_case.py" <moddata> <backup> scripts-only `
  "$caseRoot\outputs\02-scripts-only-mod-state.json"

& $python "$caseRoot\work\set_launcher_mod_case.py" <moddata> <backup> restore `
  "$caseRoot\outputs\restored-full-mk1212-mod-state.json"
```

Read-only pack and PML reduction:

```powershell
& $python "$caseRoot\work\parse_pfh4.py" `
  "$workshop\1934544571\1-1212scripts.pack" `
  "$caseRoot\outputs\scripts-pack-index.csv" `
  "$caseRoot\work\scripts-pack-text"

& $python "$caseRoot\work\filter_pml.py" <trace.pml> <key-events.csv> <processes.json>
& $python "$caseRoot\work\extract_process_context.py" <trace.pml> <Process-Start-index> <context.json>
```

All helper scripts used are included under `tools/`. The PFH4 helper extracts only Lua/text members to the working area and never writes to the source pack.

## Evidence-package contents

- `windows-launch-and-mod-loading-report.md` — this report.
- `installation-binaries.csv`, `workshop-packs.csv` — paths, versions, sizes, timestamps, and hashes.
- `01-vanilla-*`, `02-scripts-only-*`, `03-full-mk1212-*` — sanitized process, context, state, `used_mods`, and reduced Process Monitor evidence.
- `workshop-pack-open-order.csv`, `all-pack-first-open-order.csv` — first successful pack opens.
- `lua-os-lookups.csv` — grouped operating-system `.lua`/`.luac` probes.
- `scripts-pack-index.csv`, `scripts-pack-require-calls.csv` — read-only Scripts pack analysis.
- `changed-config-paths.csv` — files written in the relevant AppData roots.
- `vanilla-data-manifest.txt`, `preferences.script.txt`, `gfx.log.txt`, `sound.log.txt`, `modified.log` — small relevant text files.
- `procmon-attila-filter.pmc` — exported Process Monitor filter configuration.
- `tools/` — exact helper scripts.

Raw PMLs remain under the investigation working directory rather than the deliverable folder; the full capture is approximately 4.0 GB. The reduced CSV retains relevant process, pack, script, manifest, and AppData events. The third-party PML parser skipped three Procmon 4.1 event detail records in the full capture that it could not decode; paths, process metadata, and the cited events were decoded successfully. No screenshots were captured because native game-window automation was unavailable; the operator-visible outcomes are explicitly identified as such.

## What the macOS comparison should measure

Compare the macOS port empirically against these Windows facts, without assuming the implementation is equivalent:

1. What process receives the Steam launch, and whether a Feral launcher or game process receives a mod-list argument.
2. The game process's exact current directory when a relative `used_mods.txt` or equivalent is read.
3. Whether there is an equivalent to the two-block `add_working_directory` / `mod` list, including separators, quoting, semicolons, case, encoding, and order.
4. Whether the port adds the subscribed item directory or the pack path itself to its search roots.
5. Whether the port opens `1-1212scripts.pack` directly and recognizes PFH4 type 3.
6. Whether its virtual filesystem exposes the same logical roots: `data/lua_scripts`, `data/campaigns/main_attila`, and `data/script/_lib`.
7. How its Lua loader transforms dot versus slash module names, and whether it appends `.lua` and/or `.luac` identically.
8. Whether relative `io.open("used_mods.txt")` inside `frontend_pack_check.lua` lands in the same directory.
9. Whether pack first-open order matches the persisted launcher order exactly.
10. Whether loose-lookup failures are followed by successful reads from the outer pack, rather than being treated as terminal failures.

These are comparison targets only. No macOS root cause is asserted in this report.
