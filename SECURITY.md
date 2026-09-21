# Security policy

This utility reads large third-party pack files and writes generated data under
the user's ATTILA installation. Treat new pack parsers and path handling as
security-sensitive.

Please report path traversal, unsafe overwrite, command execution, privilege
boundary, or destructive-uninstall issues privately to the repository owner.
Do not attach proprietary pack files or private logs.

The project does not need administrator privileges and should not be run with
`sudo`.

The ten-slot feature loads the bundled, ad-hoc-signed ARM64 compatibility
library into the genuine Feral process. It refuses unknown executable hashes,
Mach-O UUIDs, or instruction preimages and writes only to private process
memory. Changes to supported versions, offsets, guards, or memory protections
should be reviewed as security-sensitive.
