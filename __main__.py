"""Entry point: python -m cheatgui, or tools/cheatgui/run.sh"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    if "--list" in sys.argv:
        import cli
        return cli.main(sys.argv[1:])
    import ui
    return ui.main()


if __name__ == "__main__":
    raise SystemExit(main())
