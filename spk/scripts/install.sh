#!/bin/sh
# Shared install/upgrade steps for the native DSM package.
# The build script substitutes @ACTION@ with "install" or "upgrade".
set -u
ACTION="@ACTION@"

PKGDEST="${SYNOPKG_PKGDEST:-/var/packages/OnlyFansDL/target}"
PKGVAR="${SYNOPKG_PKGVAR:-/var/packages/OnlyFansDL/var}"
PKGROOT="${SYNOPKG_PKGROOT:-$(dirname "$PKGDEST")}"
DATA="$PKGVAR/data"
LOGS="$PKGVAR/logs"
CONFIG="$PKGVAR/config"
TMP="$PKGVAR/tmp"
HOME_DIR="$PKGVAR/home"
VENV="$PKGVAR/venv"
PY313="/var/packages/python313/target/bin/python3"

umask 077
mkdir -p "$DATA" "$LOGS" "$CONFIG" "$TMP" "$HOME_DIR" 2>/dev/null || true
chmod 700 "$PKGVAR" "$DATA" "$LOGS" "$CONFIG" "$TMP" "$HOME_DIR" 2>/dev/null || true

if [ ! -x "$PY313" ]; then
    echo "ERROR: SynoCommunity Python 3.13 was not found at $PY313."
    echo "Install the python313 package from the SynoCommunity package source first."
    exit 1
fi

# Create a private virtual environment with the dependency package interpreter.
# The DSM system Python and its site-packages are never modified.
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)' >/dev/null 2>&1; then
    rm -rf "$VENV"
    if ! "$PY313" -m venv "$VENV" >/dev/null 2>&1; then
        rm -rf "$VENV"
        if ! "$PY313" -m virtualenv "$VENV" >/dev/null 2>&1; then
            echo "ERROR: Could not create the private Python environment."
            echo "python313 is present, but neither venv nor virtualenv succeeded."
            exit 1
        fi
    fi
fi

if [ ! -f "$PKGDEST/requirements-dsm.lock" ] || [ ! -d "$PKGDEST/wheelhouse" ]; then
    echo "ERROR: Bundled Python wheels are missing. Reinstall the package."
    exit 1
fi

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1
export PIP_NO_INPUT=1
export TMPDIR="$TMP"
export HOME="$HOME_DIR"
if ! "$VENV/bin/python" -m pip install --no-index --find-links "$PKGDEST/wheelhouse" \
        --require-hashes --no-cache-dir -r "$PKGDEST/requirements-dsm.lock" \
        >> "$LOGS/install.log" 2>&1; then
    echo "ERROR: Installing the bundled Python wheels failed."
    echo "See $LOGS/install.log for the pip output."
    exit 1
fi

if ! "$VENV/bin/python" -c 'import requests, curl_cffi, PIL, m3u8, socks' >/dev/null 2>&1; then
    echo "ERROR: The private Python environment is incomplete."
    echo "Remove Python 3.13 and reinstall the package, or check $LOGS/install.log."
    exit 1
fi

# Restore the pre-upgrade snapshot only if the live database/session is missing
# or corrupt. This is deliberately before bootstrap: a failed restore must stop
# the upgrade instead of silently creating a fresh, empty control database.
if [ "$ACTION" = "upgrade" ]; then
    if ! PYTHONPATH="$PKGDEST" OFDL_DATA_DIR="$DATA" OFDL_CONFIG_DIR="$CONFIG" \
        "$VENV/bin/python" -m ofdl.dsm.preserve restore >> "$LOGS/install.log" 2>&1; then
        echo "ERROR: The previous settings/session could not be restored."
        echo "See $LOGS/install.log; the upgrade was stopped to avoid data loss."
        exit 1
    fi
    # A post-upgrade snapshot helps if this version's preupgrade was unavailable
    # (for example when upgrading from an older package revision).
    PYTHONPATH="$PKGDEST" OFDL_DATA_DIR="$DATA" OFDL_CONFIG_DIR="$CONFIG" \
        "$VENV/bin/python" -m ofdl.dsm.preserve snapshot --reason postupgrade \
        >> "$LOGS/install.log" 2>&1 || true
fi

if [ -n "${wizard_app_password:-}" ]; then
    if [ "${wizard_app_password}" != "${wizard_app_password_confirm:-}" ]; then
        echo "ERROR: The two web-interface passwords do not match."
        exit 1
    fi
    # The password is sent on stdin; it never appears in the process list.
    if ! printf '%s' "$wizard_app_password" | \
        PYTHONPATH="$PKGDEST" OFDL_DATA_DIR="$DATA" \
        "$VENV/bin/python" -m ofdl.dsm.bootstrap --password-stdin --if-missing \
        >/dev/null 2>&1; then
        echo "ERROR: The web-interface password could not be stored."
        echo "Use the setup page in the web interface or reinstall the package."
        exit 1
    fi
else
    PYTHONPATH="$PKGDEST" OFDL_DATA_DIR="$DATA" \
        "$VENV/bin/python" -m ofdl.dsm.bootstrap \
        >/dev/null 2>&1 || true
fi

# Keep the runtime, database and logs private to the package account.
chmod 700 "$DATA" "$LOGS" "$CONFIG" "$TMP" "$HOME_DIR" 2>/dev/null || true
chmod 600 "$DATA/session.json" "$DATA/control.sqlite3" 2>/dev/null || true
if [ -f "$LOGS/install.log" ]; then
    chmod 600 "$LOGS/install.log" 2>/dev/null || true
fi

echo "OnlyFans DL $ACTION completed. Python runtime and wheels are ready."
exit 0
