# SYNTHETIC TEST DATA — Daily Reports, Nov 1–7, 2026

**All 14 CSV files in this archive are SYNTHETIC TEST DATA. They are not actual factory measurements and must never be represented as such.**
Purpose: testing the Industrial Energy Intelligence Platform's Daily Reports ingestion (validation, preview, reconciliation, ingestion, anomaly detection, analytics).

## 1. Files, dates and row counts

| Date | Energy file | Energy rows | Production file | Production rows |
|---|---|---:|---|---:|
| 2026-11-01 | energy_2026-11-01.csv | 240 | production_2026-11-01.csv | 96 |
| 2026-11-02 | energy_2026-11-02.csv | 240 | production_2026-11-02.csv | 96 |
| 2026-11-03 | energy_2026-11-03.csv | 240 | production_2026-11-03.csv | 96 |
| 2026-11-04 | energy_2026-11-04.csv | 240 | production_2026-11-04.csv | 96 |
| 2026-11-05 | energy_2026-11-05.csv | 240 | production_2026-11-05.csv | 96 |
| 2026-11-06 | energy_2026-11-06.csv | 240 | production_2026-11-06.csv | 96 |
| 2026-11-07 | energy_2026-11-07.csv | 240 | production_2026-11-07.csv | 96 |
| Total | 7 files | 1,680 | 7 files | 672 |

Each file contains exactly one calendar date, hourly slots 00:00 through 23:00.
Registered counts (from the supplied master data): **10 energy meters** (2 plants × 5) and **4 production lines**, so 24 × 10 = 240 and 24 × 4 = 96 rows per file.

- Plants: IN-TN-01, IN-KA-01.
- Meters (per plant): MTR-SMT, MTR-FAL, MTR-HVAC, MTR-COMPRESSOR, MTR-CHILLER (areas SMT, FAL, HVAC, COMPRESSOR, CHILLER).
- Lines: SMT-L1 and FAL-L1 (IN-TN-01); SMT-L2 and FAL-L2 (IN-KA-01).
- Products: SPH-A15-128, SPH-A15-256, SPH-PRO-256.

## 2. Column schemas (identical to the source fact tables; no columns added)

**Energy (14):** `meter_reading_id, timestamp, date, plant_id, meter_id, area, energy_source, consumption_kwh, demand_kw, power_factor, tariff_inr_per_kwh, cost_inr, co2e_kg, reading_quality`

**Production (23):** `event_id, event_ts, event_date, year, month, week, day, hour, plant_id, line_id, shift_id, product_id, production_order_id, target_qty, actual_qty, good_qty, reject_qty, rework_qty, downtime_min, downtime_reason, operator_team, source_system, data_quality`

Format: UTF-8 (no BOM), LF line endings, header row, comma-separated, timestamps `YYYY-MM-DDTHH:00:00` (no timezone), dates `YYYY-MM-DD`.

## 3. Units and rules (derived from the source data, then reproduced)

- `consumption_kwh`: kWh per hour (interval, not cumulative). `demand_kw`: kW. `cost_inr`: INR. `co2e_kg`: kg CO2e. Production quantities: pieces per hour; `downtime_min`: minutes in the hour.
- Energy: `demand_kw = 0.92 × kWh`, `co2e_kg = 0.716 × kWh`, `cost_inr = 8.25 × kWh`, `tariff_inr_per_kwh = 8.25`, `power_factor` 0.910–0.990, `energy_source = ELECTRICITY`, `reading_quality = VALID`.
- Production: `actual_qty = good_qty + reject_qty`; `rework_qty` is a subset of `good_qty`; `target_qty` is 390 (SMT) or 270 (FAL); `downtime_min = 60` if and only if `actual_qty = 0`; shift A = 06–13, B = 14–21, C = 22–05; `week` is the ISO week (Nov 1 = week 44; Nov 2–7 = week 45).
- IDs continue the source sequences in chronological order across the files: `EN-000022081`…`EN-000023760` and `PRD-00008833`…`PRD-00009504`.

## 4. Daily scenarios (times are inclusive hourly timestamps)

| Date | Scenario |
|---|---|
| 2026-11-01 | Normal operation. |
| 2026-11-02 | Low power-factor episode: IN-KA-01 MTR-HVAC, 14:00–17:00, power factor 0.910–0.915 (kWh normal). Otherwise normal. |
| 2026-11-03 | Moderately elevated consumption: IN-TN-01 MTR-COMPRESSOR ×1.30, 10:00–21:00. Reduced production: SMT-L1 at about 20–40% of target, 08:00–13:00, with IN-TN-01 MTR-SMT ×1.30 over the same hours (elevated energy during reduced production). SMT-L1 recovery at 14:00–15:00 (about 85–95% of normal), normal from 16:00. |
| 2026-11-04 | Short zero-production period: FAL-L2, 02:00–03:00 (all quantities 0, 60 min downtime), with IN-KA-01 MTR-FAL continuing at non-zero consumption; recovery hour 04:00, then normal. Temporary reject-rate increase: SMT-L2, 10:00–15:00, reject rate about 6–8% (baseline ≤ 3.5%). |
| 2026-11-05 | Normal operation (recovery). |
| 2026-11-06 | Normal operation. |
| 2026-11-07 | Normal operation. |

Four of the seven days (Nov 1, 5, 6, 7) contain no scenarios. The only zero-output rows in the entire set are FAL-L2 on Nov 4 at 02:00 and 03:00.
No equipment faults, root causes or savings are asserted: scenario hours use `downtime_reason = NONE`, which also occurs with non-zero downtime in your source data.

## 5. Validation results (all passed, for all 14 files)

- Column names, order and inferred dtypes identical to the source fact tables.
- Row counts per file: 240 energy and 96 production; 24 hourly records for every meter and line; hours 00–23 present.
- Each file contains only its own date (`date`, `event_date`, and the date part of every timestamp).
- No nulls. No duplicate (plant_id, meter_id, timestamp) or (line_id, event_ts) keys, within each file or across all 14 files. All IDs unique and non-overlapping with the source ID ranges.
- Foreign keys: meter/plant/area triples match the source; line/plant pairs match `dim_production_line`; product IDs exist in `dim_product`.
- Energy: positive kWh within each meter's historical min/max, power factor within 0.910–0.990, derived fields match the source formulas.
- Production: quantity balance, no negatives, actual ≤ each line's historical maximum, downtime/zero-output rule, shift mapping and calendar columns consistent; baseline reject rate ≤ 3.5%.
- Cross-file: for every date, the energy and production files cover identical hourly timestamps and plants; scenario windows are aligned.

## 6. Assumptions and limitations

1. **Source energy is independent of production** (correlation ≈ 0, no hour-of-day or weekday pattern, including at zero-output hours). The baseline preserves this; energy–production links exist only in the explicit scenarios above.
2. **Low power factor:** source power factor is roughly uniform on 0.910–0.990 and cannot go lower, so the episode is a four-hour run at the range floor. A fixed threshold alone will also flag some normal rows.
3. **Reject-rate scenario:** 6–8% exceeds the source maximum (3.5%); this is deliberate. If your validation enforces a reject ceiling, those 6 rows may be flagged.
4. **Baseline downtime reasons** are resampled from the source distribution (including EQUIPMENT_FAULT, FEEDER_JAM, etc.) and are not synthetic claims about any cause. The source also contains `downtime_reason = NONE` with downtime > 0, and `actual_qty` above `target_qty`; both appear here.
5. **Production orders:** there is no order table, so `production_order_id` is drawn at random from the source range PO-000001…PO-000450, as in the source. Products are drawn at random per row, as in the source.
6. **ID continuation** is an assumption; the source defines no rule for new IDs.
7. **No timezone** is declared in the source timestamps, so none is added. The energy-meter-to-line pairing (SMT meter ↔ SMT line, FAL meter ↔ FAL line, per plant) is inferred from area and line type.
8. Source master-data observation: `dim_product.standard_unit_cost_inr` is 11,800 for both SPH-A15-128 and SPH-PRO-256 (22,100 for SPH-A15-256), which may be a data-entry issue. It does not affect these files.
9. These daily files supersede the earlier single 5-day files: energy values for Nov 1–5 are identical, but production values and scenario downtime reasons differ.

Generated with a fixed random seed (20261101).
