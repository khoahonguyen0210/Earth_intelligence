# Hot-Dry-Windy Index

The Hot-Dry-Windy Index (HDW) is a fire-weather index from Srock et al.
(2018). It uses weather only: no fuel, drought or terrain data. A high
value means hot, dry and windy air near the ground, which makes a fire
harder to control.

## Definition

From the paper:

- **Formula:** HDW = highest wind speed × highest vapor pressure deficit
  (VPD) in the lowest 500 m of the atmosphere. Wind is in m/s and VPD is
  in hPa.
- **Surface-adjusted VPD:** air from each level is lowered to the surface
  without heat exchange (dry adiabatic), keeping its moisture. VPD is
  computed at the surface pressure.
- **Pressure levels:** with data on pressure levels, the paper uses the
  surface plus every level up to and including the first level more than
  50 hPa above the surface. This code does the same.
- **Daily value:** the highest value of the day, from 12, 18 and 00 UTC.

Choices the paper leaves open:

- **Saturation vapor pressure:** the Magnus formula with the constants of
  Alduchov and Eskridge (1996). The project's relative humidity uses the
  same formula. The paper's two worked examples (4.9 hPa at 0 °C and
  34.0 hPa at 30 °C, both at 20% relative humidity) are matched within
  0.15 hPa.
- **Missing values:** the result is missing (NaN) when any value the
  column uses is missing. Levels below the ground or above the layer are
  never used, so missing values there do not matter.

A version that uses only 2 m temperature, 2 m dew point and 10 m wind is
called the **surface approximation**. It is not the paper's index.

## Code

| File | Purpose |
|---|---|
| `kernels/hdwi_reference.py` | The index in plain PyTorch. It is the reference for every faster version. |
| `kernels/fixtures.py` | Random columns and edge cases: calm wind, saturated air, missing values, extreme values, high terrain. |

Run the tests with:

```bash
cd ml
uv run pytest tests/kernels
```

## Reference

Srock, A. F., Charney, J. J., Potter, B. E., and Goodrick, S. L. (2018).
The Hot-Dry-Windy Index: A New Fire Weather Index. *Atmosphere*, 9(7),
279. https://doi.org/10.3390/atmos9070279
