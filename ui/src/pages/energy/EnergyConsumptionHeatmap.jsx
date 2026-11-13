import React, { useEffect, useMemo, useState } from 'react';
import { formatDate, formatNumber } from '../../utils/formatters';
import './EnergyConsumptionHeatmap.css';

const isNumber = (value) => value !== null
  && value !== undefined
  && !(typeof value === 'string' && value.trim() === '')
  && Number.isFinite(Number(value));

const isValidDate = (value) => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
};

const exactNumber = (value) => Number(value).toLocaleString('en-IN', {
  maximumFractionDigits: 20,
});

const weekdayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function getHeatLevel(value, maximum) {
  if (value === 0 || maximum <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((value / maximum) * 4)));
}

function buildMonths(startDate, endDate, recordsByDate) {
  const months = [];
  const [startYear, startMonth] = startDate.split('-').map(Number);
  const [endYear, endMonth] = endDate.split('-').map(Number);

  for (let year = startYear, month = startMonth; year < endYear || (year === endYear && month <= endMonth);) {
    const monthStart = new Date(Date.UTC(year, month - 1, 1));
    const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const leadingBlanks = (monthStart.getUTCDay() + 6) % 7;
    const cells = Array.from({ length: leadingBlanks }, (_, index) => ({
      key: `blank-start-${year}-${month}-${index}`,
      blank: true,
    }));

    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const inPeriod = date >= startDate && date <= endDate;
      cells.push({
        key: date,
        blank: !inPeriod,
        date,
        record: inPeriod ? recordsByDate.get(date) || null : null,
      });
    }

    while (cells.length % 7 !== 0) {
      cells.push({
        key: `blank-end-${year}-${month}-${cells.length}`,
        blank: true,
      });
    }

    months.push({
      key: `${year}-${String(month).padStart(2, '0')}`,
      label: monthStart.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' }),
      cells,
    });

    if (month === 12) {
      year += 1;
      month = 1;
    } else {
      month += 1;
    }
  }

  return months;
}

function getRecordDescription(date, entry) {
  if (entry.duplicate) return `${formatDate(date)}: multiple daily records returned; consumption is ambiguous.`;
  if (!isNumber(entry.record?.consumption_kwh) || Number(entry.record.consumption_kwh) < 0) {
    return `${formatDate(date)}: consumption unavailable.`;
  }
  return `${formatDate(date)}: ${exactNumber(entry.record.consumption_kwh)} kWh`;
}

export default function EnergyConsumptionHeatmap({
  dailyTrend = [],
  dataAvailable = false,
  selectedPlant,
}) {
  const [selectedDate, setSelectedDate] = useState(null);
  const trendRecords = Array.isArray(dailyTrend) ? dailyTrend : [];

  const {
    recordsByDate,
    startDate,
    endDate,
    invalidDateCount,
    duplicateDateCount,
    validReadings,
  } = useMemo(() => {
    const byDate = new Map();
    let invalidDates = 0;
    let duplicateDates = 0;

    trendRecords.forEach((record) => {
      if (!isValidDate(record?.date)) {
        invalidDates += 1;
        return;
      }

      const existing = byDate.get(record.date);
      if (existing) {
        if (!existing.duplicate) duplicateDates += 1;
        byDate.set(record.date, { duplicate: true, record: null });
      } else {
        byDate.set(record.date, { duplicate: false, record });
      }
    });

    const dates = [...byDate.keys()].sort();
    const readings = [...byDate.values()]
      .filter((entry) => !entry.duplicate
        && isNumber(entry.record?.consumption_kwh)
        && Number(entry.record.consumption_kwh) >= 0)
      .map((entry) => Number(entry.record.consumption_kwh));

    return {
      recordsByDate: byDate,
      startDate: dates[0] || null,
      endDate: dates[dates.length - 1] || null,
      invalidDateCount: invalidDates,
      duplicateDateCount: duplicateDates,
      validReadings: readings,
    };
  }, [trendRecords]);

  useEffect(() => {
    setSelectedDate(null);
  }, [dailyTrend, dataAvailable, selectedPlant]);

  const maximumConsumption = validReadings.length > 0 ? Math.max(...validReadings) : null;
  const months = startDate && endDate
    ? buildMonths(startDate, endDate, recordsByDate)
    : [];
  const selectedEntry = selectedDate ? recordsByDate.get(selectedDate) : null;
  const missingDateCount = startDate && endDate
    ? Math.max(0, Math.round((Date.parse(`${endDate}T00:00:00Z`) - Date.parse(`${startDate}T00:00:00Z`)) / 86400000) + 1 - recordsByDate.size)
    : 0;

  return (
    <section className="dashboard-section energy-consumption-heatmap">
      <div className="section-header">
        <div>
          <h3 className="section-title">Daily Energy Consumption Calendar</h3>
          <p className="section-desc">
            Calendar view of returned daily energy totals. Color intensity is relative to the highest reported day in this period, not an anomaly or efficiency threshold.
          </p>
        </div>
        <span className="energy-heatmap-scope">{selectedPlant || 'All plants'}</span>
      </div>

      {!dataAvailable ? (
        <div className="energy-heatmap-state" role="status">
          Daily energy trend is unavailable; no heatmap values can be shown.
        </div>
      ) : trendRecords.length === 0 ? (
        <div className="energy-heatmap-state" role="status">
          No daily trend records were returned for this plant scope.
        </div>
      ) : months.length === 0 ? (
        <div className="energy-heatmap-state" role="status">
          Daily trend records were returned, but none contained a valid date.
        </div>
      ) : (
        <>
          <div className="energy-heatmap-period">
            <span>{formatDate(startDate)} – {formatDate(endDate)}</span>
            <span>{validReadings.length} returned day(s) with usable energy values</span>
            <span>{missingDateCount} date(s) with no returned record</span>
            <span>Coverage uses the earliest and latest valid returned daily dates.</span>
          </div>

          {(invalidDateCount > 0 || duplicateDateCount > 0) && (
            <p className="energy-heatmap-state" role="status">
              {invalidDateCount > 0 && `${invalidDateCount} record(s) with invalid dates were omitted. `}
              {duplicateDateCount > 0 && `${duplicateDateCount} duplicate date(s) are marked unavailable rather than combined.`}
            </p>
          )}

          <div className="energy-heatmap-legend" role="group" aria-label="Heatmap color scale">
            {maximumConsumption !== null && maximumConsumption > 0 ? (
              <>
                <span>Reported consumption:</span>
                <span className="energy-heatmap-legend-item">
                  <i className="heat-level-0" aria-hidden="true" /> 0 kWh
                </span>
                {[1, 2, 3, 4].map((level, index) => (
                  <span key={level} className="energy-heatmap-legend-item">
                    <i className={`heat-level-${level}`} aria-hidden="true" />
                    {`>${index * 25}–${(index + 1) * 25}%`}
                  </span>
                ))}
                <span className="energy-heatmap-legend-note">
                  of maximum returned day ({exactNumber(maximumConsumption)} kWh)
                </span>
              </>
            ) : (
              <>
                <span className="energy-heatmap-legend-item">
                  <i className="heat-level-0" aria-hidden="true" /> 0 kWh (no positive values returned)
                </span>
              </>
            )}
            <span className="energy-heatmap-legend-item">
              <i className="heat-missing" aria-hidden="true" /> No record
            </span>
            <span className="energy-heatmap-legend-item">
              <i className="heat-unavailable" aria-hidden="true" /> Value unavailable
            </span>
          </div>

          <div className="energy-heatmap-months">
            {months.map((month) => (
              <section key={month.key} className="energy-heatmap-month" aria-label={month.label}>
                <h4>{month.label}</h4>
                <div className="energy-heatmap-calendar">
                  {weekdayNames.map((day) => (
                    <span key={`${month.key}-${day}`} className="energy-heatmap-weekday" aria-hidden="true">
                      {day}
                    </span>
                  ))}
                  {month.cells.map((cell) => {
                    if (cell.blank) {
                      return <span key={cell.key} className="energy-heatmap-blank" aria-hidden="true" />;
                    }

                    const entry = cell.record;
                    const value = !entry?.duplicate && isNumber(entry?.record?.consumption_kwh)
                      ? Number(entry.record.consumption_kwh)
                      : null;
                    const validValue = value !== null && value >= 0;
                    const level = validValue ? getHeatLevel(value, maximumConsumption || 0) : null;
                    const selected = selectedDate === cell.date;

                    if (!entry) {
                      return (
                        <span
                          key={cell.key}
                          className="energy-heatmap-day heat-missing"
                          role="img"
                          aria-label={`${formatDate(cell.date)}: no record returned`}
                          title={`${formatDate(cell.date)}: no record returned`}
                        >
                          {Number(cell.date.slice(-2))}
                        </span>
                      );
                    }

                    const description = getRecordDescription(cell.date, entry);
                    return (
                      <button
                        key={cell.key}
                        type="button"
                        className={`energy-heatmap-day ${validValue ? `heat-level-${level}` : 'heat-unavailable'}${selected ? ' selected' : ''}`}
                        aria-label={description}
                        aria-pressed={selected}
                        title={description}
                        onClick={() => setSelectedDate(selected ? null : cell.date)}
                      >
                        {Number(cell.date.slice(-2))}
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>

          {selectedEntry && (
            <div className="energy-heatmap-selected-detail" role="status" aria-live="polite">
              <strong>{formatDate(selectedDate)}</strong>
              <span>
                {selectedEntry.duplicate
                  ? 'Consumption unavailable: multiple daily records were returned for this date.'
                  : isNumber(selectedEntry.record?.consumption_kwh) && Number(selectedEntry.record.consumption_kwh) >= 0
                    ? `${exactNumber(selectedEntry.record.consumption_kwh)} kWh`
                    : 'Consumption unavailable in the returned record.'}
              </span>
              {!selectedEntry.duplicate && isNumber(selectedEntry.record?.reading_count) && (
                <span>{formatNumber(selectedEntry.record.reading_count, 0)} returned reading(s)</span>
              )}
              {!selectedEntry.duplicate && isNumber(selectedEntry.record?.avg_power_factor) && (
                <span>Energy-weighted average PF: {formatNumber(selectedEntry.record.avg_power_factor, 4)}</span>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
