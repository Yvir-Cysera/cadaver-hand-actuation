# Two-motor LabVIEW rig

**Starting from GitHub?** First follow [Build a source-only copy](#build-a-source-only-copy) below.

Copy this whole folder, including `runtime` and `labview/config.ini`, to the destination. The prepared folder contains 64-bit Python 3.10.11 and the pinned packages. You can rename the folder. Close the VI and any rig command prompts before moving it.

## Run the front panel

1. On the rig PC, close any `tview` windows using the adapters.
2. Open `labview/multi_final.vi` in 64-bit LabVIEW 2023 Q1. Confirm **Number of Motors** is **2** and both **Mode** entries show **Telemetry**.
3. Click **Run** and allow a few seconds for the bridge to initialize. The iteration count should advance, and both columns should show position, torque and force. Use the front-panel **STOP** button to finish.

LabVIEW resolves the Python runtime, scripts and INI from the VI location. The CMD launcher is optional. On a different Windows PC, install LabVIEW and the Phidget22 Windows driver. The motor configuration in `labview/rig_motor_runtime.py` checks COM5 and USB serial `1A34E4DF` for ID 1, and COM6 and `99877172` for ID 2. If Windows assigns different ports, verify the USB serial numbers before editing `ROUTES`.

## Use CMD or tview

Double-click `RES.cmd`. The prompt opens in this folder and selects the bundled Python. These commands check the runtime and show which adapters Windows sees.

```bat
python build_runtime.py --check
python -m serial.tools.list_ports -v
```

With LabVIEW stopped, run `tview --fdcanusb COM5 -t 1` for motor 1 or `tview --fdcanusb COM6 -t 2` for motor 2. Close the viewer before running the VI.

## Build a source-only copy

A prepared folder already includes `runtime\python310\python.exe`. A source-only checkout requires a one-time build. On a Windows build PC with python.org **CPython 3.10.11 x64** and pip installed, run these commands from the folder containing this README.

```bat
py -3.10 build_runtime.py
runtime\python310\python.exe build_runtime.py --check
```

The default build downloads the pinned packages. For an offline build with a complete wheel directory, use `py -3.10 build_runtime.py --wheelhouse "D:\wheels"`. Once built, the runtime travels with this folder. A fresh deployment also needs the rig's VIs and its own verified calibration and position limits in `labview/config.ini`.

## Verification on the lab rig

A relocated copy of the two-motor VI in LabVIEW 2023 Q1 reported position, torque, and force for both channels over 11,090 telemetry iterations with zero displayed motor errors and a normal front-panel STOP. Driven modes were checked with simulated controllers. To run the 15 hardware-free checks from this folder:

```bat
runtime\python310\python.exe -B -m unittest discover -s tests -v
```
