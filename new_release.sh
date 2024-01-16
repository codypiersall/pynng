#!/usr/bin/bash

# Create a new release of pynng.
# This script ensures that the version in pynng/_version.py is consistent with the
# repository tag. It then adds "+dev" the revision in pynng/_version.py, so that the
# tagged release is on *exactly one* revision.
#
# This script changes the state of your repository, so be careful with it!
function usage() {
    echo >&2 "$0 RELEASE"
    echo >&2 "    RELEASE must be of the form major.minor.micro, e.g. 0.12.4"
    exit
}

if [ "$#" -lt "1" ]; then
    echo >&2 "Not enough args: Must provide a new release version"
    usage
    exit
fi

VERSION_FILE=pynng/_version.py

new_version="$1"

# make sure the new version actually has the right pattern
if ! echo "$new_version" | grep -E "^[0-9]+\.[0-9]+\.[0-9]+$" > /dev/null; then
    echo >&2 "RELEASE must match pattern MAJOR.MINOR.MICRO"
    usage
fi

echo "__version__ = \"$new_version\"" > $VERSION_FILE
git add $VERSION_FILE
git commit -m "Version bump to v$new_version"
git tag -a v"$new_version" -m "Release version $new_version."
echo "__version__ = \"$new_version+dev\"" > $VERSION_FILE
git add $VERSION_FILE
git commit -a -m "Add +dev to version ($new_version+dev)"
