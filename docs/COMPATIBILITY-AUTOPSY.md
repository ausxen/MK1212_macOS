# MK1212 native macOS compatibility autopsy

Date: 2026-09-11; updated for submod test  
Target: Feral Interactive Total War: ATTILA 1.6.1, build `480285.103778`, ARM64  
Result: working native compatibility layer; campaign launch confirmed under the consolidated launcher

## Confidence labels

- **Confirmed**: directly observed in files, process state, hashes, or the running game.
- **Strongly inferred**: best explanation of multiple observations, but not proven inside the closed-source engine.
- **Unverified**: plausible and relevant, but the available evidence does not distinguish it from alternatives.

## Outcome

- **Confirmed:** `MK1212 Mac Launcher.app` started the genuine Feral executable without modifying or re-signing it.
- **Confirmed:** Feral's multi-mod conflict alert did not appear during the consolidated launcher test.
- **Confirmed:** the live ATTILA process used `TotalWarAttilaData` as its current working directory.
- **Confirmed:** all 13 ordered compatibility content packs and six immediately-following DDS repair overlays were open in the live process.
- **Confirmed:** the game displayed the MK1212 campaign map, and the operator confirmed that both the campaign and a battle ran under the consolidated launcher.
- **Confirmed:** an earlier controlled external-launch configuration reached the MK1212 menu, loaded a campaign, and loaded a battle. That earlier run still depended on the previous one-file Base repair and loose-Lua layer; it is comparison evidence rather than the final consolidated test.
- **Confirmed:** all 13 Workshop source packs retained their recorded SHA-256 hashes through installation. The Feral executable SHA-256 remained `13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e`.
- **Strongly inferred:** the independent-launcher architecture succeeds because it bypasses Feral's type-3 multi-selection path while giving the engine equivalent content through ordered type-4 local representations, loose Lua visibility, and format-aware DDS repairs.

## Windows versus Feral

| Area | Controlled Windows installation | Feral macOS installation | Conclusion |
|---|---|---|---|
| Executable chain | `steam.exe` -> Electron launcher main -> renderer -> `attila.exe` | Steam normally enters Feral's signed `.app` and HTML Options/Mod Manager frontend. The independent launcher directly executes the genuine outer Feral binary. | **Confirmed** on both tested systems. |
| Modded command line | `attila.exe used_mods.txt;` | The consolidated Mac launcher passes no mod-list argument. A separate direct Mac test did pass `used_mods.txt;`; Feral still showed its generic conflict alert, although dismissing it led to a working campaign. | Windows behavior and Mac argv are **confirmed**; whether Feral fully honors the Windows argument is **unverified**. |
| Current working directory | Attila installation root, so relative `used_mods.txt` resolves there | The ordinary Steam/Feral launch had an unsuitable-looking directory in earlier tracing. The consolidated launcher explicitly changes to `TotalWarAttilaData`; this was confirmed with `lsof`. | Directory difference is **confirmed**. CWD matters for relative paths, but is **confirmed not to be the sole failure cause**. |
| Persistent mod list | `%APPDATA%\The Creative Assembly\Launcher\20190104-moddata.dat`, JSON records with absolute pack paths, active flags, and numeric order | Feral `Preferences Data`, XML keys whose mod values encode `timestamp|enabled|order` | **Confirmed.** |
| Transient mod list | `used_mods.txt`: all `add_working_directory` records first, then ordered `mod` records | Feral's native representation was not observed to reproduce Windows' exact handoff. The shim writes a comparison-compatible list for frontend compatibility, but normal launch does not pass it as argv. | Windows is **confirmed**; Feral equivalence is **unverified**. |
| Pack discovery | Enabled type-3 Workshop packs are opened directly from their Workshop directories in exact launcher order | Feral scans Workshop packs for its UI, but enabling multiple MK1212 type-3 packs invokes the generic conflict path. Type-4 packs in the game data directory auto-load without Feral mod toggles. | Discovery and the conflict are **confirmed**. Whether every open Workshop handle represents a mounted VFS pack when disabled is **unverified**. |
| Load order | Numeric launcher order; observed pack-open order exactly matched Scripts, Cities, Base, Models 1–9, Music | Generated filenames carry zero-padded order prefixes. Live first-open order matched each content pack followed immediately by its repair overlay, then the next component. | **Confirmed** for the generated pack-open order. Engine conflict resolution following that sequence is **strongly inferred** from the successful campaign and override tests. |
| Loose-file visibility | Loose Lua probes occur under AppData maps, installation data, then each working directory; all failed because Windows used Lua inside the mounted Scripts pack | Feral hides files not listed in `feral/en/manifest.txt`. Exact path-and-size records make loose Lua visible. | **Confirmed.** |
| Lua search paths | Pack Lua sets roots including `?.lua`, `data/ui/templates/?.lua`, `data/ui/?.lua`, and campaign-relative roots | The same internal Lua paths are extracted under the data tree; 155 load-order-winning Lua files are listed in Feral's manifest | File visibility and counts are **confirmed**; execution of every individual Lua member is **unverified**. Successful MK frontend/campaign behavior is strong functional evidence. |
| Relative-path behavior | `used_mods.txt` resolves relative to the installation-root CWD; Lua probes use AppData, installation, and working-directory roots | The independent launcher uses the data root as CWD and an isolated Feral home while linking the real Feral VFS user/local data | CWD and isolated-home use are **confirmed**. The complete closed-source relative-path search algorithm is **unverified**. |

## What the reported separate `.command` launcher most likely reproduced

1. **Confirmed requirement:** it launched the real Feral executable as a separate entry rather than asking Feral's Mod Manager to enable several MK1212 type-3 packs.
2. **Strongly inferred requirement:** it supplied auto-loading local pack representations, most likely type-4/movie packs, because this avoids the type-3 multi-mod conflict path without altering Workshop content.
3. **Strongly inferred requirement:** it arranged deterministic component order and exposed Scripts-pack Lua as loose, manifest-whitelisted files. Both operations were independently required by controlled Mac tests.
4. **Strongly inferred requirement:** it established a useful game-relative current directory and Steam App ID environment.
5. **Unverified:** it may have generated or passed a Windows-style `used_mods.txt`. The direct Mac argument test proves that the argument is accepted without an immediate command-line error, but it did not bypass Feral's conflict warning and did not isolate the argument's contribution from the compatibility layer already present.
6. **Unverified:** it may have manipulated Feral preferences. The new launcher instead uses an isolated preference home with all mod toggles disabled, leaving the user's normal Feral preferences untouched.

## Implemented architecture

The installer discovers the Steam library/game/Workshop roots, reads the installed pack set, and builds a ledger-owned layer under the existing ATTILA data tree:

1. It selects the canonical Windows-confirmed 13-pack MK1212 order. Installed and enabled non-core submods are appended in Feral order. `--profile feral` can instead import only currently enabled, still-present packs.
2. It creates APFS clone-on-write pack copies and changes only their PFH pack type from type 3 to type 4. Workshop sources remain byte-for-byte unchanged.
3. It validates DDS overrides against the lower-priority winning DDS contract.
4. For a transformable unsafe DDS, it renames that one member inside the content clone so it no longer overrides the path, then writes a small type-4 repair overlay immediately after that component. This preserves component/submod priority.
5. It extracts the final load-order winner for each Lua path and writes exact Feral manifest entries.
6. It records source hashes, generated-file hashes, exact manifest hashes, and a complete uninstall ledger.
7. At launch it verifies the installed layer, creates an isolated Feral preference home, changes to `TotalWarAttilaData`, sets Steam App ID `325610` if absent, writes a diagnostic JSON log, and executes the untouched Feral binary.

No Workshop pack, Feral application file, application signature, DB, XML, Lua, model, or arbitrary texture payload is edited in place.

## Generic smaller-asset handling

- **Confirmed:** the known Base sea texture has the same 1016x720 base dimensions as stock but only one mip level; the stock contract has ten. Suppressing only that override previously allowed a campaign to load and advance a turn.
- **Confirmed:** the known `eastern_ridge_helmet_02_diffuse.dds` override is 256x256 while the stock contract is 512x512, and its use produced the same repeatable ARM64 `_platform_memmove` crash family.
- **Strongly inferred:** Feral contains one or more unsafe assumptions when a higher-priority DDS provides a smaller storage contract than the lower-priority asset at the same virtual path. The matching crash family and the successful sea suppression support this, but do not prove a single internal cause for every candidate.
- **Confirmed:** format-aware scanning found 54 transformable DDS contract mismatches in the selected 13-pack graph: Cities 2, Base 1, Models 1 19, Models 4 20, Models 5 5, and Models 9 7.
- **Strongly inferred policy:** repair DDS overrides when they omit required mip levels or reduce dimensions relative to the lower-priority contract, but only when their exact DDS encoding has a defined transformation.
- **Confirmed implementation:** uncompressed 32-bit DDS files gain synthesized lower mip levels while preserving mip 0 exactly. DXT1/DXT3/DXT5 files can gain missing upper power-of-two levels using index-preserving block expansion, retaining their existing lower chain byte-for-byte. Unsupported cases abort with the exact path.
- **Unverified:** all 54 candidates would crash without repair. Only the sea and named helmet failures are directly crash-confirmed. The broader set is preventive compatibility policy, not 54 asserted crash diagnoses.

## Installed state and reversibility

- Compatibility state: `~/Library/Application Support/MK1212 Mac Launcher/state.json`
- Generated files: 174 total — 13 content packs, 6 repair packs, 155 loose Lua files
- Source packs: 13, each with recorded size, modification time, and SHA-256
- DDS repairs: 54
- Manifest before install: `c65f9103473bcf8686827e6c39d3e2c8b653035e9ba954a4ff723f7628b84f6e`
- Manifest after install: `58a80f7828c914bbb8a4a512e051820c2545c408a0f4d209a3c71664df9d9340`
- Exact pre-install backup: `~/Library/Application Support/MK1212 Mac Launcher/backups/manifest.20260911T101344.install.c65f9103473bcf8686827e6c39d3e2c8b653035e9ba954a4ff723f7628b84f6e.txt`
- Generated `used_mods.txt`: SHA-256 `5a6be68a6d1eed46f923a9ef06b6e9dea0d07cc6af93f12280f6c3c6bec1fb31`, 1,861 bytes

The uninstaller first verifies ledger ownership, backs up the then-current manifest, removes only this installation's exact manifest entries and generated files, and does not restore an old manifest wholesale. This prevents an obsolete backup from overwriting newer unrelated changes.

## Controls and limitations

- **Confirmed:** vanilla Attila previously reached its unmodified menu with no Workshop packs open. That remains the baseline control.
- **Confirmed:** the launcher refuses to install, uninstall, or rewrite compatibility files while ATTILA is running.
- **Confirmed:** quick verification detects source size/mtime changes; full verification recomputes hashes.
- **Current limitation:** a Workshop or selected-submod change is detected but is not rebuilt in place. Quit ATTILA, run uninstall, then install again. The process is deterministic and surgical, but not yet an automatic incremental refresh.
- **Current limitation:** automatic submod inclusion depends on the submod being installed and enabled in Feral preferences at install time. Re-run installation after changing the intended set/order.
- **Unverified:** future unsupported DDS encodings or non-DDS engine incompatibilities. The installer stops rather than guessing or padding an unknown asset.
- **Confirmed caveat:** Apple's tools currently report the installed Feral bundle's signature as invalid/internal signing-subsystem error, while still showing a hardened-runtime CodeDirectory, Team ID `XH73Y9BGP8`, and a stapled notarization ticket. Both its executable and `_CodeSignature/CodeResources` have 2026-09-04 timestamps, before this investigation, and the executable hash remained unchanged. The compatibility tools never write inside the `.app`. The cause and date of that pre-existing bundle verification condition are **unverified**.

## Delivered commands

- `mk1212-mac-install`
- `mk1212-mac-launch`
- `mk1212-mac-verify`
- `mk1212-mac-uninstall`
- `MK1212 Mac Launcher.app`, installed at `/Applications/MK1212 Mac Launcher.app`
- portable `MK1212-Mac-Launcher.zip`

Recommended routine:

1. Quit ATTILA.
2. Run `mk1212-mac-verify --quick` before launch or after a Steam update.
3. Open `MK1212 Mac Launcher.app` (or use `mk1212-mac-launch`).
4. If verification reports a changed source, quit ATTILA, uninstall the compatibility layer, and install it again.
5. Use `mk1212-mac-uninstall` for surgical removal.

## Addendum: Tycherious' 1212 Tweaks and Realistic Smoke

- **Confirmed:** Workshop items `3415546839` (`Tycherious' All-in-one plus tweaks.pack`) and `2880264357` (`mk1212_smoke.pack`) were discovered locally and hashed before installation.
- **Confirmed:** Feral had not yet created mod-manager records for either new pack, so the previous default enabled-submod import would have omitted them.
- **Confirmed:** tool v0.4.0 adds `--load-order-file`, accepting an explicit, duplicate-checked list of bare pack filenames. This prevents Feral's stale/missing records from silently choosing the wrong set or order.
- **Confirmed:** the explicit order used was Tweaks, Realistic Smoke, Scripts, Cities, Base, Models 1–9, Music, matching the author's published order.
- **Confirmed:** the dry run found no new unsafe DDS overrides in either submod. The complete graph still requires 54 repairs and exposes 155 load-order-winning Lua files.
- **Confirmed:** the surgical rebuild backed up the clean manifest at SHA-256 `c65f9103473bcf8686827e6c39d3e2c8b653035e9ba954a4ff723f7628b84f6e` before installation. The installed 15-pack manifest is SHA-256 `0d7c6824417731c8f9882fb2434e4a50927eb8ebc4f65af8046535cc0492679f` and 43,501 bytes.
- **Confirmed:** full pre-launch verification passed for 176 generated files and all 15 Workshop source hashes.
- **Confirmed:** the running game opened the generated packs in the exact explicit order, with each repair overlay immediately after its owning component, and reached the campaign map without Feral's multi-mod conflict alert.
- **Confirmed:** the operator subsequently confirmed that both the campaign and a battle ran under the 15-pack configuration.
