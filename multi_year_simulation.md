# Multi-Year Simulation — Scope & Known Limitations

Branch: `multi-year-simulation` (based on `development`)

This branch extends the district generator so it can simulate **several consecutive
years** in one run instead of a single test reference year (TRY). It is intended as a
working starting point: the residential demand path is functional and validated on the
example district, but some areas are deliberately scoped and flagged below for follow-up.

The design goal throughout was **backward compatibility**: with no multi-year settings,
every default reduces to the original single-year behaviour.

---

## How to use it

Multi-year behaviour is driven entirely by configuration. Add the following to the
`.env.CONFIG.*` file you run with:

```
# Point at a multi-year weather file in data/weather/ (bypasses PLZ-based TRY selection)
WEATHERFILENAME=multi_year_weather_example.txt
WEATHERFILEHEADERROWS=33      # header rows to skip in that file
STARTYEAR=2020                # first calendar year (drives weekday/holiday alignment)
SIMULATIONYEARS=5             # number of consecutive years in the weather file
HOLIDAY_STATE=NW              # German federal state for public holidays
# RANDOMSEED=42               # optional: reproducible stochastic profiles (forces single-threaded demand gen)
```

If `WEATHERFILENAME` is **not** set, the run uses the normal single TRY workflow and
behaves exactly as before (the TRY year fixes the calendar and header rows automatically).

### Weather file requirements

A custom multi-year weather file must:

- follow the standard DWD TRY column layout;
- contain a **whole number of days**, including **Feb 29 for leap years**, so the
  calendar/holiday alignment doesn't drift;

> The shipped `multi_year_weather_example.txt` is currently a **placeholder**.

---

## What changed

| Area | File                                                               | Change |
|------|--------------------------------------------------------------------|--------|
| Config | `data_handling/config.py`                                          | New fields: `startYear`, `simulationYears`, `weatherFileHeaderRows`, `randomSeed` (TimeConfig); `weatherFileName` (LocationConfig); `holiday_state` (CalendarConfig). |
| Config docs | `data/.env.CONFIG.EXAMPLE`, `data/.env.CONFIG.MULTI_YEAR`          | Documented the new keys (defaults preserve single-year behaviour). |
| Environment | `classes/datahandler.py` → `generateEnvironment`                   | Custom-weather-file branch; simulation length derived from the file; multi-year holiday loop (cumulative Julian days); `initial_day` derived from `startYear`, with a TRY fallback that pins the calendar year from `TRYYear` for single-year runs. |
| Soil temperature | `functions/heating_network_simple.py` → `calculate_soil_temperature` | Timestep count and output time vector derived from the actual data length instead of a hardcoded single year. |
| Stochastic demands | `classes/users.py` → `calcProfiles`                                | Residential profiles (occupancy, electricity, dhw, gains, EV time series) generated for one representative year and **tiled** to the horizon. |
| Thermal model | `functions/_5R1C.py`, `functions/_7R2C.py`                         | `timesteps_per_day` is resolution-based (was `numberTimesteps/365`); the day index is split into a cumulative index (weekday + holidays) and a wrapped day-of-year (heating/cooling season), so seasons recur every year. |
| Reproducibility | `classes/datahandler.py`                                           | `randomSeed` seeds the RNGs before building/profile generation; demand generation runs single-threaded when a seed is set. |

---

## Design decisions

- **Heating/cooling run natively over the full multi-year weather**, so each year reflects
  its real weather. The thermal models loop the whole horizon; only the day-of-year logic
  needed fixing.
- **Stochastic profiles are tiled, not generated natively per year.** `richardsonpy` (and
  OpenDHW) only generate a single year. Consequently, occupancy/electricity/dhw/gains are
  **identical across years**; only the weather-driven heating/cooling varies year to year.
- **The calendar is driven by `startYear`.** Weekday alignment and the cumulative holiday
  list follow the real years simulated. Single-year TRY runs pin this from `TRYYear` so they
  are unchanged (incl. TRY2045).
- **Backward compatible.** All defaults (`simulationYears=1`, no `weatherFileName`, no
  `randomSeed`) reproduce the original single-year, threaded behaviour.

---

## Known limitations / follow-ups

1. **Non-residential buildings are not adapted.** The non-residential branch of
   `calcProfiles` and its generators still assume a single year. A district containing
   schools/offices etc. will produce wrong results or fail. Only residential building types
   (SFH, TH, MFH, AB) are supported multi-year.
2. **Stochastic years are repeated, not resampled.** See the tiling decision above. If
   genuine year-to-year stochastic variation is needed, `richardsonpy` would have to be
   replaced or extended, or per-year generation stitched together.
3. **EV multi-year is unvalidated.** Per-car profiles are tiled for length, but the example
   district has no EVs (`EV=0`). Multi-year runs with EVs should be checked before use.
4. **dhw seasonal water-temperature curve** is a single representative year tiled along with
   the dhw demand — adequate for the stochastic dhw model, but not a true multi-year curve.
5. **Custom weather file constraints** (whole days, leap days, no humidity zeros) are not
   enforced in code — a malformed file degrades silently (calendar drift, NaN soil temps).
6. **Seeding forces single-threaded demand generation**, which is slower. Without a seed,
   threaded generation is used and results vary between runs.
