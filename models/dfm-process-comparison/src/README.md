# Model catalog

Run each script with the repository cadgen Python environment. Outputs resolve
relative to each script and appear in `../STEP` and `../STL`.

- `baseline.py`: thin-wall starting mounting tray.
- `fdm.py`: thicker walls/floor and four gussets.
- `sheet.py`: uniform sheet with two circular bends.
- `injection.py`: Z-drafted walls and holes, plus four thin tapered ribs.
- `cnc.py`: thicker walls and optional floor root fillets.

Shared geometry lives in `lib/tray_geometry.py`. Checks and figure generation
live in `../scripts`; see the project README for reproduction and limitations.
