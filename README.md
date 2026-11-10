# Cadaver Hand Actuation

Motor control software and a LabVIEW operator interface for the biomechanical
evaluation of cadaveric human hands. The system drives tendon cables with
brushless motors while measuring cable tension with load cells, enabling
controlled, repeatable actuation of the fingers for biomechanics research.

Developed in the Towles biomechanics lab.

## Start the two-motor rig (Windows, LabVIEW 2023 Q1 x64)

GitHub downloads contain the source and VIs. On a Windows machine with a full python.org CPython **3.10.11 x64** installation (including pip and the Python launcher), extract the repository and run this once in CMD from the folder containing this README:

```bat
py -3.10 build_runtime.py
```

The build downloads the pinned packages and checks the resulting runtime. Open `labview/multi_final.vi` in 64-bit LabVIEW 2023 Q1. With both modes set to **Telemetry**, click **Run**. The target PC also needs the Phidget22 Windows driver. Once built, the entire folder, including `runtime`, can be moved or renamed. See [Rig setup and tview](RIG_SETUP.md) for adapter identities, the offline build option, and stop instructions.

## Overview

Each finger tendon is routed over a load cell and wound onto a motor-driven
spool. A [moteus](https://mjbots.com/) brushless servo controller commands each
motor in position, velocity, or torque mode, and [Phidget](https://www.phidgets.com/)
bridge inputs read load cells to measure the resulting tension in Newtons.

The project is organized in three layers:

- **Low-level control libraries** (`labview/`) — thin Python wrappers around the
  `moteus` and `Phidget22` APIs that expose simple, synchronous calls (move,
  hold, torque, read tension, set limits) for single- and multi-motor rigs.
- **Operator interface** (`labview/*.vi`) — LabVIEW front panels that call those
  Python functions, giving an operator real-time control and telemetry without
  touching code during an experiment.
- **Characterization scripts** (`motor_testing/`) — standalone scripts that drive
  the motor through known position/velocity/torque profiles, log motor telemetry
  and load cell output, and save plots and CSVs for analysis.

## Repository structure

```
.
├── load_cell_calibration.py   # Interactive load cell calibration + live tension readout
├── requirements.txt           # Pinned Python environment
│
├── labview/                   # Control libraries + LabVIEW front panels (see labview/README.md)
│   ├── labview_moteus_funcs.py  # Single-motor control (move / hold / torque / vel+torque)
│   ├── moteus_multi.py          # Multi-motor control with per-motor modes
│   ├── setup_funcs.py           # Controller setup: re-zero, soft position limits
│   ├── phidget_funcs.py         # Dual load cell reading, calibrated to Newtons
│   └── *.vi                     # LabVIEW VIs that call the above functions
│
└── motor_testing/
    ├── Tests/                 # Position, velocity, and torque characterization scripts
    └── Results/               # Saved plots, CSV logs, and per-experiment notes (see Results/README.md)
        ├── no_compensation/        # 2025-05-12  baseline, no cogging compensation
        ├── cogging_compensation/   # 2025-05-17  software cogging compensation
        ├── big_spool/              # 2025-07-01  large-spool configuration
        └── load_cell_comparison/   # 2025-07-01  inline vs. S-type load cell
```

## Hardware

- mjbots **moteus** brushless servo controller(s), one per motor (CAN-FD over USB)
- Brushless motor with a cable spool per actuated tendon
- **Phidget** VoltageRatioInput bridge (e.g. 1046) with S-type and/or inline load cells


## Usage

**Calibrate a load cell and stream live tension:**

```bash
python load_cell_calibration.py
```

Follow the prompts to tare, enter five known weights, and supply the cable wrap
angles. The script then prints live mass, force, and tension; press `0` + Enter
to re-zero and Ctrl+C to stop.

**Run a characterization test** (motor must be connected and calibrated):

```bash
python motor_testing/Tests/trq_test.py   # also: pos_test.py, vel_test.py
```

Each test drives a known command profile, logs telemetry and load cell output,
and saves a timestamped plot and CSV in the working directory.

**Operate the two-motor rig from LabVIEW:** open `labview/multi_final.vi` after the one-time build above. The VI locates its Python runtime and modules relative to its own folder.

## Notes

- Each motor has its own USB adapter. The production rig checks the ID, COM port and USB serial mappings in `labview/rig_motor_runtime.py`.
- Load cell calibration constants in `phidget_funcs.py` are specific to the cells
  and wiring used here and should be re-derived for a different setup using
  `load_cell_calibration.py`.
