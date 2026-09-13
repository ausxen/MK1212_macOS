# MK1212 ten-building-slot compatibility autopsy

Date: 2026-09-11

## Conclusions

- **Confirmed:** MK1212's embedded `MK1212_10slots.exe` is a 10,240-byte
  Windows x86 PE executable. It finds ATTILA's process and changes the integer
  `6` to `10` in an eight-byte machine-code signature.
- **Confirmed:** the current open-source Windows `twdll` implementation
  independently identifies the changed value as
  `CampaignSettlementCallback::m_max_slots`. Its hook changes the callback's
  UI rendering-loop limit before settlement-panel initialization.
- **Confirmed:** the Feral ARM64 executable contains the corresponding capital
  flag and maximum-slot fields at object offsets `0x70` and `0x74`. Two native
  initialization paths store `6` into the latter field.
- **Confirmed:** Feral's stock `ui/campaign ui/settlement_panel` layout contains
  six named capital controls (`building_slot_1` through `building_slot_6`) and
  four minor-settlement controls.
- **Confirmed:** ordinary debugger attachment to the untouched hardened Feral
  executable is denied on this Mac. The application does not expose a usable
  `get-task-allow` entitlement.
- **Confirmed:** an edited test save reports ten model slots for Londinium.
- **Confirmed:** Feral dynamically exposes visible `building_slot_1` through
  `building_slot_10` containers for that settlement, but its native callback
  populates only the first six. Slots 7-10 exist and have no children.
- **Confirmed:** immediately before the sixth model slot was unlocked, the UI
  populated only slots 1-5. Unlocking it caused slot 6 to gain its expected
  child while slots 7-10 remained empty. This matches the native callback's
  hardcoded six-iteration limit exactly.
- **Strongly inferred:** MK1212's campaign/database logic is functioning; the
  missing native operation is construction-slot callback binding/population
  for model indexes 6-9.

## Reversible test

Launcher compatibility revision `feral-slot-probe-v1` transforms only the
cached winning loose copy of `campaigns/main_attila/mk1212_slots.lua`. It:

1. suppresses reconstruction and attempted execution of the Windows PE helper;
2. records the selected settlement's model slot count;
3. records whether each of ten named UI slot controls exists, is visible, and
   has a bound child;
4. writes the result to the launcher's state `logs/slot-diagnostic.log` path
   supplied through the child process environment.

Workshop packs and all Feral application files remain unchanged. Deactivation
continues to remove the transformed loose Lua file and restore the manifest to
its pre-launch state.

Revision `feral-slot-callback-probe-v2` extends the same read-only probe to log
container and child callback IDs, child states, positions, and bounds. This is
intended to determine whether Lua can instantiate a callback-bearing template;
it does not attempt to fabricate an unbound visual slot.

## Callback probe result

- **Confirmed:** all ten visible `building_slot_N` containers report the native
  callback ID `CampaignConstructionSlotCallback`.
- **Confirmed:** slots 1-6 receive a child whose callback ID is
  `ConstructionItemInterface`; slots 7-10 receive no child at all. The first
  five were existing buildings and slots 5-6 were correctly generated as
  `Slot4_Construction_Site` and `Slot5_Construction_Site` as development
  points unlocked them.
- **Confirmed:** the native ARM64 callback constructor sets its private
  maximum-slot field to `6` at offset `0x74`; it does this before its UI update
  function constructs the children. The test result is exactly consistent with
  that limit.
- **Confirmed:** the exposed Lua UI API can observe `CallbackId` and alter
  layout/properties, but it provides no callback-state setter or slot-context
  setter in this Feral build. A copied child would retain the wrong
  `ConstructionItemInterface` context, so it would be a deceptive visual
  patch rather than a functioning seventh slot.
- **Strongly inferred:** no native ten-slot solution exists solely in the
  current Lua/UI-layout surface. The actual repair must change the native
  callback's maximum from 6 to 10 before settlement-panel population.

## Constraint boundary

The required native change is known and tiny, but the untouched Feral ARM64
process is hardened and rejects ordinary debugger attachment/library injection.
Consequently, applying it in place would require modifying or re-signing the
Feral application, which remains out of scope. The user subsequently authorized
a copied, separately signed local compatibility clone for experimental use. The
original Steam installation remains the vanilla-control path.

## Local native-clone implementation

- **Confirmed:** a private clone was created at
  `~/Library/Application Support/MK1212 Mac Launcher/native-clone/Total War
  ATTILA MK1212.app`; it is derived locally from the user's Steam installation
  and is not a distributable game copy.
- **Confirmed:** the source executable is accepted only at SHA-256
  `13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e`
  (Feral 1.6.1 build `480285.103778`). Any other build is refused.
- **Confirmed:** the clone patcher verified the surrounding three-instruction
  context at each location and changed only the two ARM64 `mov w8, #6`
  instructions at file offsets `0x3457244` and `0x34577f4` to `mov w8, #10`.
  The original executable's SHA-256 remained unchanged.
- **Confirmed:** the resulting clone executable SHA-256 is
  `90d7676df6085a7a3e95004f0fbca48649ca06b1e0826e1094dce97575f5cc82`
  and the independently signed clone passes strict macOS code-signature
  verification.
- **Confirmed:** the first clone launch crashed before ATTILA initialized. The
  clone was located in shim state without the bundle-relative
  `TotalWarAttilaData` sibling expected by Feral's macOS startup path. The
  launcher now creates only a shim-state symlink named `TotalWarAttilaData`
  beside the clone, pointing to the original unmodified data directory; it does
  not create or alter anything in the Steam game directory.
- **Strongly inferred:** this missing relative data path caused the early
  null-pointer startup crash. The repaired clone needs a new launch test.
- **Unverified:** functional ten-slot behavior in a campaign. The next test
  must load the edited Londinium save through the MK1212 launcher and confirm
  that slots 7-10 receive `ConstructionItemInterface` children and open a
  functioning construction browser.

## Post-test integrity check

- **Confirmed:** after the callback-probe test exited, the launcher removed all
  active compatibility files and restored the stock manifest hash
  `c65f9103473bcf8686827e6c39d3e2c8b653035e9ba954a4ff723f7628b84f6e`.
- **Confirmed:** the ATTILA executable SHA-256 remained
  `13f5d523019f291f489353fa5d3661bc9a668bb2b0375d6c3201e01d74525c5e`,
  identical to the records before this test and to the new launch record.
- **Unverified:** current macOS `codesign --verify --strict` rejects the
  existing ATTILA bundle despite that unchanged executable hash. No app file
  has a modification timestamp from this test, and the launcher does not write
  inside the app bundle. Do not repair or re-sign it as part of this work; use
  Steam verification only as a separate, user-approved maintenance operation.

## First probe-launch incident

- **Confirmed:** launch `20260911T163734` ran for about 80 seconds and then
  received `EXC_BAD_ACCESS`/`SIGSEGV` on worker thread 69. The slot diagnostic
  file was never created, so the new probe callback did not execute.
- **Confirmed:** the crashing addresses are in Feral's statically linked Wwise
  audio implementation (the nearest executable code is under
  `CAkMeterManager`). This is not the previously isolated `_platform_memmove`
  texture signature.
- **Confirmed:** the failed core-only profile has the same 13 packs and 33 DDS
  repairs as the last known-good core-only launch. Its 1212 Music compatibility
  clone is byte-identical to the Workshop source after the four-byte pack-type
  field.
- **Strongly inferred:** this individual failure is an audio-worker crash and
  not evidence that the slot Lua probe caused the fault. A same-profile retry
  is required before changing the probe. If it repeats at the same offsets,
  the next controlled test is the same profile without the Music pack.
- **Confirmed:** transient cleanup completed and the inactive launcher verified
  the vanilla live tree after the crash.
