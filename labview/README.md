# LabVIEW Control Interface

Low-level Python control libraries and the LabVIEW front panels that drive them.

## Python libraries

Thin, synchronous wrappers around the `moteus` and `Phidget22` APIs, called from the
VIs via LabVIEW Python nodes.

| File | Purpose |
|---|---|
| `labview_moteus_funcs.py` | Single-motor control (move / hold / torque / velocity+torque). |
| `moteus_multi.py` | Multi-motor control with per-motor modes. |
| `rig_motor_runtime.py` | Maps each motor to its USB adapter and keeps a single event loop for the session. |
| `setup_funcs.py` | Controller setup: re-zero, soft position limits. |
| `phidget_funcs.py` | Dual load cell reading, calibrated to Newtons. |

## LabVIEW VIs

| File | Purpose |
|---|---|
| `sinlge_motor.vi` | Single-motor operator front panel. |
| `multi_final.vi` | Multi-motor operator front panel. |
| `move_multi.vi`, `multi_pos.vi`, `setup_mulit.vi` | Multi-motor move / position / setup sub-VIs. |
| `py_venv_init.vi`, `add_to_path.vi` | Open the folder-local Python 3.10 session and resolve file paths relative to the VIs. |
| `Read Ini File 2012 NIVerified.vi` | Stock NI utility for reading INI config (dependency). |

The two-motor rig setup, including the build command and `tview` examples, is in [RIG_SETUP.md](../RIG_SETUP.md).

## Notes

- The VIs reference the `.py` modules and one another **by filename**. Rename them
  only from within LabVIEW (which updates the call hierarchy) — renaming on disk
  breaks the sub-VI and Python-node links.
- Known filename typos to fix in LabVIEW when convenient: `sinlge_motor.vi` →
  `single_motor.vi`, `setup_mulit.vi` → `setup_multi.vi`.
- Load cell calibration constants in `phidget_funcs.py` are specific to the cells in
  use and must be re-measured for different hardware.
