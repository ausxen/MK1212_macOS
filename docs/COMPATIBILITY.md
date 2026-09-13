# Compatibility notes

## Confirmed

- Feral ATTILA 1.6.1 build `480285.103778`, native ARM64
- MK1212 core 13-pack load order
- Tycherious' 1212 Tweaks and Realistic Smoke 15-pack load order
- Campaign and battle loading for both tested sets
- Core-plus-Realistic-Smoke activation with Tycherious disabled
- Vanilla normal launch before cache preparation, after preparation, and after
  transient custom-launcher cleanup
- Exact Feral manifest path-and-size records with no forced final newline
- Independent launch from `TotalWarAttilaData`
- Workshop and Feral application inputs remain unchanged

## Strongly inferred

- Ordered type-4 representations bypass Feral's type-3 multi-mod conflict path.
- Feral's ARM64 asset failures are associated with mod DDS files whose
  dimensions or mip contracts are smaller than the same-path stock asset.
- Repair overlays must remain adjacent to their owning component to preserve
  component and submod priority.

## Unverified or unsupported

- Intel Macs
- Feral builds other than `480285.103778`
- Non-English manifests
- Steam libraries on non-APFS volumes
- Arbitrary submods and DDS encodings outside RGB32, DXT1, DXT3, and DXT5
- Automatic incremental rebuild after a Workshop update
- Behavior after a hard power loss or forced `SIGKILL`, before a launcher
  command has recovered the stale activation
- Automatic submod dependency metadata

Only two individual crash paths—the MK1212 sea texture and one helmet
texture—were isolated directly. The larger stock-contract candidate set is
preventive policy, not a claim that every candidate independently crashes.
Intentional mod-to-mod DDS differences are not transformed.
