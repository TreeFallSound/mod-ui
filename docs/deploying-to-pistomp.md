# Testing a mod-ui branch on a pi-Stomp

`deploy.sh` copies this working tree over the mod-ui that the `mod-ui` Debian
package installed on the device, restarts the service, and can put the packaged
version back afterwards. Nothing is rebuilt or repackaged, so a round trip takes
seconds.

## What gets replaced

The package (built by `pi-gen-pistomp/debpkgs/mod-ui`) installs mod-ui in three
places. `deploy.sh` overwrites the first two and leaves the third alone:

| On the device | From this repo | Deployed |
|---------------|----------------|----------|
| `/opt/pistomp/venvs/mod-ui/lib/python3.11/site-packages/{mod,modtools}` | `mod/`, `modtools/` | always |
| `/opt/pistomp/mod-ui/html` (`MOD_HTML_DIR`) | `html/` | always |
| `.../site-packages/modtools/libmod_utils.so` | `utils/` (C++) | only with `--build-utils` |

The service unit, its environment and the Python dependencies in the venv stay
as packaged.

## The recipe

```bash
git switch my-branch
./deploy.sh            # snapshot the packaged files (first time only), copy, restart, wait for port 80
# test at http://pistomp.local/ — hard-reload the browser so it drops cached JS/CSS
./deploy.sh logs       # follow the mod-ui journal while you test
# edit, then ./deploy.sh again; repeat
./deploy.sh status     # what is on the device right now
./deploy.sh restore    # back to the packaged mod-ui when you are done
```

Uncommitted changes are deployed too; `status` says so. The device is
`pistomp@pistomp.local` unless you set `PISTOMP_HOST` / `PISTOMP_USER`
(use the IP address if mDNS does not resolve).

## Snapshots and markers

- **Snapshot.** Before the first deploy, the packaged `mod`, `modtools` and `html`
  are saved to `~pistomp/mod-ui-snapshots/mod-ui-<package version>.tar.gz`.
  Later deploys reuse it. `restore` puts it back. It is keyed by package version,
  so after an `apt upgrade` of mod-ui the next deploy takes a fresh one.
- **Marker.** Each deploy writes `/opt/pistomp/mod-ui/DEV-DEPLOY` (branch, commit,
  time, package version). `restore` removes it. `deploy.sh` will not snapshot
  while a dev build sits on top of the installed package version, so a dev build
  is never saved as "packaged".
  If you hit that error, run `sudo apt install --reinstall mod-ui` on the device
  and deploy again.

## Things to know

- **A package upgrade overwrites a dev deploy.** `status` notices and says so.
- **Crash loops start recovery.** The unit has `OnFailure=pistomp-recovery.service`
  and `StartLimitBurst=3` in 60s. If the deployed code dies on startup three
  times, the device drops into the recovery UI. `deploy.sh` waits 90s for port
  80, prints the journal if it never answers, and you run `./deploy.sh restore`.
- **Edited `.less`? Rebuild `main.css` before deploying.** The device serves
  the compiled `html/css/main.css` and never compiles `.less` itself. This
  reproduces the committed file exactly:

  ```bash
  cd html/css
  npm install --no-save bootstrap@3.4.1
  npx -y -p less@2 lessc --compress less/main.less main.css
  ```

- **C++ changes (`utils/`) need `--build-utils`.** The `.so` must be built for
  ARM64 on the device, which needs `make`, `g++`, `liblilv-dev` and
  `libjack-jackd2-dev` there. Without the flag the packaged `.so` is kept, which
  is right as long as your branch does not touch `utils/` beyond what the
  installed package was built from.
- **Dependency changes are not deployed.** If a branch needs a new Python
  package or service environment variable, test it by building the package
  instead (set `MOD_UI_BRANCH` in `pi-gen-pistomp/config.sh` and run
  `debpkgs/mod-ui/build.sh`).
