"""WhyNot Cut installer core entry point: python -I -B wnc_install.py install | uninstall | plan [options].

Run by the bootstrap with the engine's own python-build-standalone interpreter. `-I` drops this script's folder from
sys.path, so it is put back here before importing the wnc_installer package that sits next to it.
"""
import os
import sys

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin folder

if sys.version_info < (3, 9):
    sys.stderr.write("WhyNot Cut installer needs Python 3.9 or newer\n")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from wnc_installer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
