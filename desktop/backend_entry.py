"""Entry point for the bundled processing engine."""
from multiprocessing import freeze_support

from drumscore.server import main

if __name__ == '__main__':
    freeze_support()
    main()
