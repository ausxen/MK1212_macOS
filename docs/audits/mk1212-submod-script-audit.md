# Optional submod script audit

Audit date: 2026-09-12. Workshop packs were read only; neither pack was
modified.

## Packs examined

| Pack | PFH type | SHA-256 | Contents relevant to portability |
|---|---:|---|---|
| `mk1212_smoke.pack` | 4 | `3d6c9a5151e4ea5dd4d7e091ca0639707c26c283082f30524bc2ec30529f4d67` | DB projectile tables, VFX XML, one DXT5 DDS |
| `Tycherious' All-in-one plus tweaks.pack` | 3 | `b9bd0cb069d8294a719723dc2ed0c93d02094fc23480dc8fe9eb8c56cb7b2621` | DB tables only |

## Findings

- **Confirmed:** neither pack contains Lua, executable, shell, batch,
  PowerShell, Python, DLL, or other script-like entries.
- **Confirmed:** a printable-payload scan found no `APPDATA`, Windows user
  paths, `os.execute`, `.exe`, `Program Files`, or PowerShell references.
- **Confirmed:** `mk1212_smoke.pack` contains no script; its XML uses normal
  engine-relative resource paths such as `fx/particle_vfx_library.hlsl`.
- **Confirmed:** the smoke DDS is 1024x1024, DXT5, with 11 mip levels. The
  compatibility planner generated no repair for it.
- **Confirmed:** the Tweaks pack contains DB data only. Its notable overrides
  are missions, campaign variables, skills, AI, diplomatic values, and
  projectile-related tables; these are data/load-order concerns, not
  Windows-specific script concerns.
- **Strongly inferred:** no macOS Lua workaround is required for either pack.
  The existing launcher’s type-3/type-4 handling is the relevant path.
- **Unverified:** the gameplay semantics of every Tweaks DB override and the
  visual/gameplay result of the smoke VFX have not yet been exercised in a
  campaign or battle.

## Clarification: four turns per year

- **Confirmed locally:** the selected `Tycherious' All-in-one plus tweaks.pack`
  contains DB tables only; it does not contain the Lua override that would
  replace MK1212's core `GetTurnFromYear` calculation.
- **Confirmed locally:** the core `1-1212scripts.pack` contains
  `mk1212_common.lua`, whose calculation is explicitly marked `2TPY` and uses
  `(year - 1212) * 2 + 1`.
- **Confirmed from the author's Workshop listing:** the 4TPY utility is a
  separate item, `Tycherious' 1212 4TPY - Four Turns Per Year` (Workshop ID
  `3507330550`), listed above the complete/tweaks bundle rather than as part
  of that bundle.
- **Confirmed locally after subscription:** the downloaded pack is named
  `Tycherious' 4TPY Updated Event Timing 2.0.pack`, is type 3, and contains a
  same-path replacement of `campaigns/main_attila/common/mk1212_common.lua`
  changing `(year - 1212) * 2 + 1` to `(year - 1212) * 4 + 1`.
- **Confirmed launcher defect fixed:** newly subscribed packs that Feral has
  not yet written into its preferences are now discovered directly from the
  Workshop inventory. Optional packs are emitted ahead of the required MK1212
  core, matching the author's stated priority, so the 4TPY Lua file can win.
- **Unverified:** an in-game campaign test of the newly selected 4TPY pack on
  this Feral/macOS profile remains to be run.

## Recommended test

Enable both packs in the launcher selector. Test one campaign load, one
battle load using gunpowder/projectile effects, and one turn advance. If a
failure occurs, investigate the relevant DB override or asset/load-order
collision rather than looking for a Windows-only script.
