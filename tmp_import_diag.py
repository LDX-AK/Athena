import importlib

mods = [
    "numpy",
    "pandas",
    "sklearn",
    "lightgbm",
    "aiohttp",
    "athena.core",
]

for m in mods:
    print(f"IMPORT {m}", flush=True)
    importlib.import_module(m)
    print(f"OK {m}", flush=True)
