# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m cheatgui, or tools/cheatgui/run.sh"""
import faulthandler
import os
import signal
import sys

# Everything this app does runs on the Tk thread, so anything that blocks looks
# identical from outside: a window that stops repainting. `kill -USR1 <pid>`
# prints the stack of wherever it actually is, which beats guessing.
faulthandler.enable()
if hasattr(signal, "SIGUSR1"):
    faulthandler.register(signal.SIGUSR1)

HERE = os.path.dirname(os.path.abspath(__file__))

# The GUI's own modules, then tools/cheats for chtparse and ggdecode. The
# parser there is the reference model the RTL is checked against, so the GUI
# reads cheat files through exactly the code the core is verified to match.
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "cheats"))


def main() -> int:
    if "--check-db" in sys.argv:
        # Prints what a support question needs: which build, which database,
        # and whether this machine can actually reach and verify upstream.
        # A frozen binary carries its own CA bundle and there is no other way
        # to find out whether the one it carries works.
        import db
        import ssl
        import version
        print(f"version:  {version.version()}"
              f"{' (packaged)' if version.frozen() else ' (checkout)'}")
        print(f"database: {db.db_dir()}")
        local = db.local_state()
        print(f"local:    {db.describe(local)}")
        try:
            import certifi
            print(f"ca store: {certifi.where()} (bundled)")
        except ImportError:
            p = ssl.get_default_verify_paths()
            print(f"ca store: {p.cafile or p.capath} (system)")
        try:
            remote = db.remote_state(timeout=20)
            print(f"upstream: {remote['sha'][:10]} {db.day(remote['date'])}")
            print("verdict:  upstream reachable and verified")
            return 0
        except Exception as e:                               # noqa: BLE001
            print(f"upstream: {type(e).__name__}: {e}")
            print("verdict:  COULD NOT REACH UPSTREAM")
            return 1

    if "--list" in sys.argv:
        # Read only, so any number of these can run at once.
        import cli
        return cli.main(sys.argv[1:])

    import single
    handle, holder = single.acquire()
    if handle is None:
        print(f"the cheat picker is already running (pid {holder}).",
              file=sys.stderr)
        print("Use that window, or close it first.", file=sys.stderr)
        return 1

    import ui
    try:
        return ui.main()
    finally:
        # Explicit, so the lock goes as the window does rather than whenever
        # the handle happens to be collected.
        if hasattr(handle, "close"):
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
