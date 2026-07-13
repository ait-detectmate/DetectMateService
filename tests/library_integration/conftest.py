import os
import sys

# pytest's default import mode only puts this directory (tests/library_integration)
# on sys.path, not the repo root or tests/. (needed for dummy class imports)
#  conftest.py is always imported before any
# test module in this directory, so add tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
