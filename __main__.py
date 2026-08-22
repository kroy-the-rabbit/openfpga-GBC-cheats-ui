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
        import cli
        return cli.main(sys.argv[1:])
    import ui
    return ui.main()


if __name__ == "__main__":
    raise SystemExit(main())
