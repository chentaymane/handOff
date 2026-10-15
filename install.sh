#!/bin/sh
# Install the handoff skill into every coding CLI on this computer (macOS and Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/chentaymane/handOff/main/install.sh | sh
#
# Options go to install.py:   ... | sh -s -- --dry-run      ... | sh -s -- --only claude,agents
# Run it again to update. To remove: python3 ~/.agents/skills/handoff/scripts/handoff.py skill uninstall
#
# HANDOFF_REF picks a branch or tag (default main); HANDOFF_ARCHIVE points at another .tar.gz (a URL or a file).

# Everything is inside a function, so a download cut short runs nothing.
main() {
    set -e
    repo="${HANDOFF_REPO:-chentaymane/handOff}"
    ref="${HANDOFF_REF:-main}"
    archive="${HANDOFF_ARCHIVE:-https://github.com/$repo/archive/$ref.tar.gz}"

    python=""
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
            python="$candidate"
            break
        fi
    done
    [ -n "$python" ] || fail "Python 3.8 or newer is needed and was not found. Get it from https://www.python.org/downloads/"
    command -v tar >/dev/null 2>&1 || fail "tar is needed and was not found."

    workdir=$(mktemp -d 2>/dev/null || mktemp -d -t handoff)
    trap 'rm -rf "$workdir"' EXIT
    trap 'exit 1' INT TERM

    echo "Downloading handoff ($ref)..."
    if [ -f "$archive" ]; then
        cp "$archive" "$workdir/handoff.tar.gz"
    elif command -v curl >/dev/null 2>&1; then
        curl -fsSL "$archive" -o "$workdir/handoff.tar.gz" || fail "Could not download $archive"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$workdir/handoff.tar.gz" "$archive" || fail "Could not download $archive"
    else
        fail "curl or wget is needed and neither was found."
    fi
    tar -xzf "$workdir/handoff.tar.gz" -C "$workdir" || fail "The download is not a valid archive: $archive"

    installer=""
    for folder in "$workdir"/*/; do
        if [ -f "${folder}install.py" ]; then
            installer="${folder}install.py"
            break
        fi
    done
    [ -n "$installer" ] || fail "The download has no install.py: $archive"

    echo
    "$python" "$installer" ${1+"$@"} </dev/null
}

fail() {
    echo "handoff: $*" >&2
    exit 1
}

main ${1+"$@"}
