#!/bin/zsh
set -euo pipefail

folder="${0:A:h}"
launcher="$folder/MK1212 Mac Launcher.app"

if [[ ! -d "$launcher" ]]; then
    print -u2 "MK1212 Mac Launcher.app was not found beside this helper."
    print -u2 "Run this helper from the MK1212 Mac Launcher folder after copying it to Applications."
    exit 1
fi

print "Removing the macOS download quarantine flag from:"
print "  $folder"
print ""
print "This changes only Finder security metadata for this launcher folder."
print "It does not modify Total War: ATTILA, Feral files, or Workshop content."
print ""

/usr/bin/xattr -dr com.apple.quarantine "$folder"

print "The launcher is prepared. You can now open:"
print "  $launcher"
print ""
print "Press any key to close this window."
read -k 1
print
