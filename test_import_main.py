import importlib, traceback, sys

# Ensure current directory is on path
import os
sys.path.insert(0, os.path.dirname(__file__))

importlib.invalidate_caches()
try:
    importlib.import_module('main')
    print('IMPORT OK')
except Exception:
    traceback.print_exc()
    sys.exit(1)
