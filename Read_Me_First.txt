ausxen's MK1212 macOS Launcher

FIRST LAUNCH — READ THIS BEFORE OPENING THE APP
================================================

1. Verify the SHA-256 checksum of the DMG you downloaded. The matching
   `.dmg.sha256` file is in the repository's `dist/` folder.

2. Open this DMG and drag the `MK1212 Mac Launcher` folder onto the
   Applications shortcut.

3. Open `/Applications/MK1212 Mac Launcher/` and run:

       Prepare MK1212 Mac Launcher.command

   This is a user-invoked preparation step. It removes only the downloaded-app
   quarantine metadata from this launcher folder. It does not modify ATTILA,
   Feral files, Workshop content, or your saves, and it does not require an
   administrator password.

4. After the helper finishes, open `MK1212 Mac Launcher.app` and follow the
   normal setup instructions in `README.txt`.

If macOS blocks the helper itself, right-click it, choose Open, and confirm the
user-initiated launch. The equivalent Terminal command is:

    xattr -dr com.apple.quarantine "/Applications/MK1212 Mac Launcher"

Do not skip checksum verification for an untrusted download.
