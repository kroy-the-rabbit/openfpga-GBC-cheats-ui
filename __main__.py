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
