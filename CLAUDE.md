# abs-census

Python scripts in this project must be run using the project-local virtual
environment at `.venv`, not system Python.

- Windows: `.venv\Scripts\python scripts\<script>.py`
- Before running anything, make sure dependencies are installed:
  `.venv\Scripts\python -m pip install -r requirements.txt`

## Fixing a failing check

If a check fails and the fix would change how a value is calculated or
defined, stop and show the proposed change before applying it. Definitions
change only through an ADR amendment.
