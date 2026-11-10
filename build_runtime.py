"""Build the folder-local Windows Python used by the LabVIEW 2023 Q1 rig.

One-time build using an installed python.org CPython 3.10.11 x64 with pip:
    py -3.10 build_runtime.py
    py -3.10 build_runtime.py --wheelhouse C:\\packages\\towles310

The offline wheelhouse must include all pinned wheels, including asyncqt. The
result is an ordinary Python installation, not a venv. Copy it with the project.
No generator interpreter or pip cache is needed on the destination machine.
To verify it there, run:
    runtime\\python310\\python.exe -B build_runtime.py --check
Use runtime\\python310\\python.exe -m moteus_gui.tview for tview. Generated
Windows console-script launchers embed build paths and are intentionally omitted.
"""

import argparse
from contextlib import contextmanager
import csv
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


PROJECT = Path(__file__).resolve().parent
REQUIREMENTS = PROJECT / "requirements.txt"
DEST = PROJECT / "runtime" / "python310"


def place_runtime_dlls(runtime):
    site = runtime / "Lib" / "site-packages"
    record, = site.glob("msvc_runtime-*.dist-info/RECORD")
    with record.open(encoding="utf-8", newline="") as manifest:
        for item, _, _ in csv.reader(manifest):
            parts = Path(item).parts
            if len(parts) == 3 and parts[:2] == ("..", "..") and item.lower().endswith(".dll"):
                target = runtime / parts[2]
                if not target.exists():
                    shutil.copy2(site / parts[2], target)


@contextmanager
def scratch():
    with TemporaryDirectory(prefix="towles_runtime_check_") as work:
        local = dict(os.environ, MPLCONFIGDIR=work, IPYTHONDIR=work,
                     JUPYTER_CONFIG_DIR=work, PYTHONDONTWRITEBYTECODE="1")
        yield work, local


def verify(path):
    if (path / "pyvenv.cfg").exists():
        raise RuntimeError("Found pyvenv.cfg; this runtime must not depend on an external base.")
    python = path / "python.exe"
    with scratch() as (work, env):
        env.update(PYTHONHOME=work, PYTHONPATH=work)
        cmd = [str(python), "-B"]
        subprocess.run([*cmd, "-m", "pip", "--disable-pip-version-check", "check"],
                       cwd=work, env=env, check=True)
        code = """
from importlib import metadata
from pathlib import Path
import struct, sys
expected = Path(sys.argv[1]).resolve()
if (sys.version_info[:3] != (3, 10, 11) or struct.calcsize('P') != 8
        or Path(sys.prefix).resolve() != expected or Path(sys.base_prefix).resolve() != expected):
    raise RuntimeError(f'Wrong Python runtime: {sys.version}, {sys.prefix}, {sys.base_prefix}')
outside = [p for p in sys.path if not Path(p).resolve().is_relative_to(expected)]
if outside:
    raise RuntimeError(f'External Python search paths: {outside}')
requirements = [s.strip().split('==') for s in Path(sys.argv[2]).read_text().splitlines()
                if s.strip() and not s.lstrip().startswith('#')]
for name, version in requirements:
    dist = metadata.distribution(name)
    if dist.version != version or not Path(dist.locate_file('')).resolve().is_relative_to(expected):
        raise RuntimeError(f'{name}: expected local {version}, found {dist.version} at {dist.locate_file("")}')
import moteus, numpy, scipy, serial.tools.list_ports, Phidget22.Devices.VoltageRatioInput
from scipy.fft import rfft
assert rfft([1.0, 0.0]).size == 2
gui = next(ep for ep in metadata.distribution('moteus-gui').entry_points if ep.name == 'tview')
if not callable(gui.load()):
    raise RuntimeError('tview entry point did not import')
print(f'OK: Python {sys.version.split()[0]} x64, {len(requirements)} pins, native imports, tview: {expected}')
"""
        subprocess.run([*cmd, "-c", code, str(path), str(REQUIREMENTS)],
                       cwd=work, env=env, check=True)


def build(wheelhouse):
    if (os.name != "nt" or sys.implementation.name != "cpython"
            or sys.version_info[:3] != (3, 10, 11) or struct.calcsize("P") != 8):
        raise RuntimeError("Build with python.org CPython 3.10.11 x64 on Windows.")
    if DEST.exists():
        raise FileExistsError(f"{DEST} exists; use --check. A build never replaces an existing runtime.")
    if wheelhouse is not None and not wheelhouse.is_dir():
        raise FileNotFoundError(f"Wheelhouse does not exist: {wheelhouse}")
    base = Path(sys.base_prefix).resolve()
    if base == DEST.resolve() or not (base / "Lib" / "ensurepip").is_dir():
        raise RuntimeError("Use a full installed CPython base (including pip/ensurepip).")
    DEST.parent.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix=".python310-build-", dir=DEST.parent) as staging:
        stage = Path(staging).resolve()
        if stage.parent != DEST.parent.resolve():
            raise RuntimeError("Unexpected staging directory")
        runtime = stage / "Python 310 image"
        runtime.mkdir()
        print(f"Copying CPython {sys.version.split()[0]} standard library and DLLs...", flush=True)
        for name in ("python.exe", "pythonw.exe", "python3.dll", "python310.dll",
                     "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
            shutil.copy2(base / name, runtime / name)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "site-packages")
        for name in ("Lib", "DLLs", "tcl", "include", "libs"):
            if (base / name).is_dir():
                shutil.copytree(base / name, runtime / name, ignore=ignore)
        (runtime / "python310._pth").write_text(
            ".\nDLLs\nLib\nLib\\site-packages\nimport site\n", encoding="ascii")
        site = runtime / "Lib" / "site-packages"
        bundled = base / "Lib" / "ensurepip" / "_bundled"
        bootstrap = ["==".join(file.name.split("-")[:2]) for file in bundled.glob("*.whl")]
        pip_args = [sys.executable, "-I", "-B", "-m", "pip", "--isolated",
                    "--disable-pip-version-check", "install", "--no-compile",
                    "--target", str(site), "--find-links", str(bundled),
                    "-r", str(REQUIREMENTS), *bootstrap]
        if wheelhouse:
            pip_args.extend(["--no-index", "--find-links", str(wheelhouse)])
        print("Installing pinned wheels...", flush=True)
        subprocess.run(pip_args, cwd=stage, check=True)
        place_runtime_dlls(runtime)
        for name in ("Scripts", "bin"):
            generated = (site / name).resolve()
            if generated.parent != site.resolve():
                raise RuntimeError("Unexpected console script path")
            if generated.is_dir():
                shutil.rmtree(generated)
        verify(runtime)
        for attempt in range(6):
            try:
                runtime.rename(DEST)
                break
            except PermissionError as exc:
                if DEST.exists():
                    raise
                if getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 5:
                    raise PermissionError(
                        f"Could not publish the runtime to {DEST}. No runtime was partially "
                        "installed. Check the folder permissions and close processes using "
                        "this directory, then run the build again."
                    ) from exc
                time.sleep(0.25 * (attempt + 1))
    verify(DEST)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wheelhouse", type=lambda s: Path(s).resolve(),
                        help="Use pinned wheels from this directory instead of a package index")
    parser.add_argument("--check", action="store_true", help="Validate the built runtime; open no hardware")
    opts = parser.parse_args()
    if opts.check:
        verify(DEST)
    else:
        build(opts.wheelhouse)
