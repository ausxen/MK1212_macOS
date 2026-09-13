# Community testing guide

## Before testing

1. Back up important campaigns.
2. Record macOS version, Mac model/chip, memory, ATTILA version/build, language,
   Steam-library volume format, and free space.
3. Save the exact load-order file used.
4. Quit ATTILA before installation, verification, or uninstall.
5. Run a full verification immediately after installation.

## Suggested test ladder

1. Confirm vanilla ATTILA reaches its menu.
2. Prepare a load-order file containing core plus the optional submods under test.
3. Launch with every optional checkbox clear and reach the MK1212 menu.
4. Start or load a campaign.
5. End one turn.
6. Load a battle and return to the campaign.
7. Repeat with exactly one optional submod checkbox enabled.
8. Quit and confirm a normal Steam launch reaches vanilla ATTILA.
9. Run full verification again.

Stop at the first repeatable failure. Do not keep changing multiple variables.

## Evidence to report

- Exact step that failed and whether it is repeatable
- Load-order file
- Output of `./bin/mk1212-mac-verify --quick --json`
- Last launcher error log, if present
- Feral crash time and top exception/signature lines
- Whether core-only and vanilla controls work
- Exact optional-submod checkbox selection

Redact the macOS username and any account identifiers from paths and logs.
Do not upload game or Workshop pack files.
