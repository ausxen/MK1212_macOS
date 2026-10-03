# Security policy

This utility reads large third-party pack files and writes generated data under
the user's ATTILA installation. Treat new pack parsers and path handling as
security-sensitive.

Please report path traversal, unsafe overwrite, command execution, privilege
boundary, or destructive-uninstall issues privately to the repository owner.
Do not attach proprietary pack files or private logs.

The game launcher and compatibility-cache operations do not run as
administrator. The standard package installer uses macOS authorization to
write its exact folder under `/Applications`; the native uninstaller requests
authorization only to remove that same Installer-owned folder. Do not run the
launcher or its command-line tools with `sudo`.

The ten-slot feature loads the bundled, ad-hoc-signed ARM64 compatibility
library into the genuine Feral process. It refuses unknown executable hashes,
Mach-O UUIDs, or instruction preimages and writes only to private process
memory. Changes to supported versions, offsets, guards, or memory protections
should be reviewed as security-sensitive.
