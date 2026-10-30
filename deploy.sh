#!/usr/bin/env bash
# Deploy this mod-ui working tree onto a pi-Stomp over the packaged install, and
# put the packaged version back when you are done. See docs/deploying-to-pistomp.md.
# Override PISTOMP_HOST / PISTOMP_USER if your device differs from the default.
#
# Usage:
#   ./deploy.sh                 # sync Python + HTML, restart service, wait until it serves
#   ./deploy.sh --build-utils   # also rsync utils/ source, build on device, install .so
#   ./deploy.sh status          # packaged version, what is deployed over it, service state
#   ./deploy.sh logs [args]     # follow the mod-ui journal (args go to journalctl)
#   ./deploy.sh snapshot        # save the packaged install (done automatically on first deploy)
#   ./deploy.sh restore         # put the snapshot back and restart
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

HOST="${PISTOMP_HOST:-pistomp.local}"
USER="${PISTOMP_USER:-pistomp}"
TARGET="${USER}@${HOST}"

VENV="/opt/pistomp/venvs/mod-ui"
HTML_DIR="/opt/pistomp/mod-ui/html"
MARKER="/opt/pistomp/mod-ui/DEV-DEPLOY"
SNAPSHOT_DIR="/home/${USER}/mod-ui-snapshots"

# One SSH connection for the whole run: one password prompt at most, and faster.
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=/tmp/mod-ui-deploy-%r@%h:%p" -o ControlPersist=60 -o ConnectTimeout=10)
export RSYNC_RSH="ssh ${SSH_OPTS[*]}"

remote() { ssh "${SSH_OPTS[@]}" "${TARGET}" "$@"; }

connect() {
    if ! remote true; then
        echo "error: cannot reach ${TARGET}. Is the pi-Stomp on the network? Set PISTOMP_HOST to its IP if mDNS fails." >&2
        exit 1
    fi
    PKG_VERSION="$(remote "dpkg-query -W -f='\${Version}' mod-ui")"
    PYTHON_VERSION="$(remote "ls ${VENV}/lib/" | grep -oE 'python[0-9]+\.[0-9]+' | head -1 | grep -oE '[0-9]+\.[0-9]+')"
    SITE_PACKAGES="${VENV}/lib/python${PYTHON_VERSION}/site-packages"
    SNAPSHOT="${SNAPSHOT_DIR}/mod-ui-${PKG_VERSION}.tar.gz"
}

# Must only ever capture the packaged files: refuses while a dev deploy is in place.
snapshot() {
    if remote "test -f ${SNAPSHOT}"; then
        echo "==> Snapshot of packaged mod-ui ${PKG_VERSION} already at ${SNAPSHOT}"
        return
    fi
    # A marker from an older package version means an upgrade already replaced the dev files.
    if remote "grep -qx 'package=${PKG_VERSION}' ${MARKER} 2>/dev/null"; then
        echo "error: a dev build is deployed and there is no snapshot of mod-ui ${PKG_VERSION}." >&2
        echo "       Reinstall the package first (sudo apt install --reinstall mod-ui), then retry." >&2
        exit 1
    fi
    echo "==> Saving packaged mod-ui ${PKG_VERSION} to ${SNAPSHOT}"
    remote "mkdir -p ${SNAPSHOT_DIR} && tar -C / -czf ${SNAPSHOT}.tmp \
        ${SITE_PACKAGES#/}/mod ${SITE_PACKAGES#/}/modtools ${HTML_DIR#/} && mv ${SNAPSHOT}.tmp ${SNAPSHOT}"
}

wait_until_serving() {
    echo "==> Waiting for mod-ui to answer on port 80"
    for _ in $(seq 1 45); do
        if remote "${VENV}/bin/python -c \"import urllib.request; urllib.request.urlopen('http://localhost/', timeout=3)\"" 2>/dev/null; then
            echo "==> mod-ui is up: http://${HOST}/"
            return
        fi
        sleep 2
    done
    echo "error: mod-ui did not come up within 90s. Last journal lines:" >&2
    remote "sudo journalctl -u mod-ui -n 40 --no-pager" >&2 || true
    echo "Put the packaged version back with: ./deploy.sh restore" >&2
    exit 1
}

deploy() {
    local build_utils="${1:-}"

    echo "==> Checking Python syntax locally"
    python3 -W ignore -m py_compile mod/*.py modtools/*.py

    connect
    remote "command -v rsync >/dev/null" || { echo "error: rsync is not installed on the device (sudo apt install rsync)" >&2; exit 1; }
    snapshot

    local sha branch dirty=""
    sha="$(git rev-parse --short HEAD)"
    branch="$(git rev-parse --abbrev-ref HEAD)"
    [[ -n "$(git status --porcelain)" ]] && dirty=" + uncommitted changes"
    echo "==> Deploying ${branch} @ ${sha}${dirty} to ${TARGET} (Python ${PYTHON_VERSION})"

    rsync -az --delete --exclude='__pycache__' --exclude='*.pyc' \
        mod/ "${TARGET}:${SITE_PACKAGES}/mod/"

    # Exclude libmod_utils.so: it is ARM64 and must be built on the device (see --build-utils).
    rsync -az --delete --exclude='__pycache__' --exclude='*.pyc' --exclude='libmod_utils.so' \
        modtools/ "${TARGET}:${SITE_PACKAGES}/modtools/"

    rsync -az --delete --exclude='node_modules' --exclude='.DS_Store' \
        html/ "${TARGET}:${HTML_DIR}/"

    if [[ "${build_utils}" == "--build-utils" ]]; then
        echo "==> Building utils on device"
        rsync -az --delete --exclude='*.o' --exclude='*.so' \
            utils/ "${TARGET}:/tmp/mod-ui-utils/"
        remote "make -C /tmp/mod-ui-utils && cp /tmp/mod-ui-utils/libmod_utils.so ${SITE_PACKAGES}/modtools/"
    fi

    remote "printf '%s\n' 'branch=${branch}' 'commit=${sha}${dirty}' 'package=${PKG_VERSION}' \
        'deployed=$(date '+%Y-%m-%d %H:%M:%S %z')' 'from=$(whoami)@$(hostname -s)' > ${MARKER}"

    echo "==> Restarting mod-ui"
    remote "sudo systemctl restart mod-ui"
    wait_until_serving
}

restore() {
    connect
    if ! remote "test -f ${SNAPSHOT}"; then
        echo "error: no snapshot of mod-ui ${PKG_VERSION} at ${SNAPSHOT}." >&2
        echo "       Fall back to: ssh ${TARGET} sudo apt install --reinstall mod-ui" >&2
        exit 1
    fi
    echo "==> Restoring packaged mod-ui ${PKG_VERSION} from ${SNAPSHOT}"
    remote "rm -rf ${SITE_PACKAGES}/mod ${SITE_PACKAGES}/modtools ${HTML_DIR} \
        && tar -C / -xzf ${SNAPSHOT} && rm -f ${MARKER}"
    echo "==> Restarting mod-ui"
    remote "sudo systemctl restart mod-ui"
    wait_until_serving
}

status() {
    connect
    echo "Device:          ${TARGET}"
    echo "Package:         mod-ui ${PKG_VERSION}"
    if remote "test -f ${MARKER}"; then
        echo "Dev deploy:      yes"
        remote "sed 's/^/                 /' ${MARKER}"
        if ! remote "grep -qx 'package=${PKG_VERSION}' ${MARKER}"; then
            echo "                 (the package was upgraded after this deploy, so its files have replaced the dev build)"
        fi
    else
        echo "Dev deploy:      no (packaged files)"
    fi
    echo "Snapshots:       $(remote "ls ${SNAPSHOT_DIR} 2>/dev/null | tr '\n' ' '")"
    echo "Service:         $(remote "systemctl is-active mod-ui" || true)"
}

case "${1:-}" in
    ""|--build-utils) deploy "${1:-}" ;;
    status)           status ;;
    logs)             shift; ssh "${SSH_OPTS[@]}" -t "${TARGET}" "sudo journalctl -u mod-ui ${*:--f}" ;;
    snapshot)         connect; snapshot ;;
    restore)          restore ;;
    -h|--help)        sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
    *)                echo "unknown command: $1 (try --help)" >&2; exit 1 ;;
esac
