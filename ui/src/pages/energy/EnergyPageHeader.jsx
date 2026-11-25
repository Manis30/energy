import React, { useState, useRef, useEffect, useMemo } from 'react';
import './energy-filters.css';

const PLANT_OPTIONS = [
  { value: '', label: 'All Plants (Consolidated)', shortLabel: 'All Plants' },
  { value: 'IN-TN-01', label: 'Plant IN-TN-01 (Tamil Nadu)', shortLabel: 'Plant IN-TN-01' },
  { value: 'IN-KA-01', label: 'Plant IN-KA-01 (Karnataka)', shortLabel: 'Plant IN-KA-01' },
];

const MONTHS = [
  { value: 1, label: 'January', short: 'Jan' },
  { value: 2, label: 'February', short: 'Feb' },
  { value: 3, label: 'March', short: 'Mar' },
  { value: 4, label: 'April', short: 'Apr' },
  { value: 5, label: 'May', short: 'May' },
  { value: 6, label: 'June', short: 'Jun' },
  { value: 7, label: 'July', short: 'Jul' },
  { value: 8, label: 'August', short: 'Aug' },
  { value: 9, label: 'September', short: 'Sep' },
  { value: 10, label: 'October', short: 'Oct' },
  { value: 11, label: 'November', short: 'Nov' },
  { value: 12, label: 'December', short: 'Dec' },
];

const YEARS = [2025, 2026, 2027];
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

const DEFAULT_SHIFTS = [
  { value: 'ALL', label: 'All shifts', shortLabel: 'All shifts' },
  { value: 'A', label: 'Shift A (Morning • 06:00 – 14:00)', shortLabel: 'Shift A' },
  { value: 'B', label: 'Shift B (Evening • 14:00 – 22:00)', shortLabel: 'Shift B' },
  { value: 'C', label: 'Shift C (Night • 22:00 – 06:00)', shortLabel: 'Shift C' },
];

/**
 * Compact Modern Filter Toolbar for Energy Analytics
 * Exact single-row order: Plant | Month | Date | Shift | Clear Filters
 * Height: 64–76px, Control height: 38–42px (40px)
 */
export default function EnergyPageHeader({
  selectedPlant = null,
  onSelectPlant,
  selectedMonth = 10,
  onSelectedMonthChange,
  selectedYear = 2026,
  onSelectedYearChange,
  selectedDate = '',
  onSelectDate,
  selectedShift = 'ALL',
  onSelectShift,
  availableShifts = [],
  onResetFilters,
}) {
  const panelRef = useRef(null);
  const [activeDropdown, setActiveDropdown] = useState(null); // 'plant' | 'month' | 'date' | 'shift' | null

  // Close popovers on click outside or Escape
  useEffect(() => {
    function handleClickOutside(event) {
      if (panelRef.current && !panelRef.current.contains(event.target)) {
        setActiveDropdown(null);
      }
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setActiveDropdown(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const toggleDropdown = (name) => {
    setActiveDropdown((prev) => (prev === name ? null : name));
  };

  // Month information
  const currentMonthObj = useMemo(() => {
    return MONTHS.find((m) => m.value === selectedMonth) || MONTHS[9];
  }, [selectedMonth]);

  const daysInMonth = useMemo(() => {
    return new Date(selectedYear, selectedMonth, 0).getDate();
  }, [selectedYear, selectedMonth]);

  // Calendar calculations: first day of month (0 = Sun, ..., 6 = Sat)
  const firstDayOfWeek = useMemo(() => {
    return new Date(selectedYear, selectedMonth - 1, 1).getDay();
  }, [selectedYear, selectedMonth]);

  // Month change handler with automatic date reconciliation
  const handleMonthSelect = (newMonth) => {
    onSelectedMonthChange && onSelectedMonthChange(newMonth);
    // If selectedDate belongs to another month, clear it
    if (selectedDate) {
      const parts = selectedDate.split('-');
      if (parts.length === 3 && (Number(parts[1]) !== newMonth || Number(parts[0]) !== selectedYear)) {
        onSelectDate && onSelectDate('');
      }
    }
    setActiveDropdown(null);
  };

  // Year change handler with automatic date reconciliation
  const handleYearSelect = (newYear) => {
    onSelectedYearChange && onSelectedYearChange(newYear);
    if (selectedDate) {
      const parts = selectedDate.split('-');
      if (parts.length === 3 && Number(parts[0]) !== newYear) {
        onSelectDate && onSelectDate('');
      }
    }
  };

  // Date selection
  const handleDateClick = (day) => {
    const monthStr = String(selectedMonth).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    const fullDate = `${selectedYear}-${monthStr}-${dayStr}`;
    onSelectDate && onSelectDate(fullDate);
    setActiveDropdown(null);
  };

  const handleSelectAllDays = () => {
    onSelectDate && onSelectDate('');
    setActiveDropdown(null);
  };

  // Formatted date label for trigger button
  const formattedDateLabel = useMemo(() => {
    if (!selectedDate) {
      return `All Days (${daysInMonth}d)`;
    }
    const parts = selectedDate.split('-');
    if (parts.length === 3) {
      const [, m, d] = parts;
      const mIdx = parseInt(m, 10) - 1;
      const mShort = MONTHS[mIdx]?.short || m;
      return `${parseInt(d, 10)} ${mShort} ${parts[0]}`;
    }
    return selectedDate;
  }, [selectedDate, daysInMonth]);

  // Selected plant display label
  const selectedPlantLabel = useMemo(() => {
    const opt = PLANT_OPTIONS.find((p) => p.value === (selectedPlant || ''));
    return opt ? opt.shortLabel : 'All Plants';
  }, [selectedPlant]);

  // Extract selected day number if within the selected month & year
  const activeSelectedDay = useMemo(() => {
    if (!selectedDate) return null;
    const parts = selectedDate.split('-');
    if (parts.length === 3) {
      const [y, m, d] = parts.map(Number);
      if (y === selectedYear && m === selectedMonth) {
        return d;
      }
    }
    return null;
  }, [selectedDate, selectedYear, selectedMonth]);

  // Selected shift display label
  const selectedShiftLabel = useMemo(() => {
    const shiftList = availableShifts && availableShifts.length > 0 ? availableShifts : DEFAULT_SHIFTS;
    const opt = shiftList.find((s) => s.value === selectedShift);
    return opt ? opt.shortLabel || opt.label : 'All shifts';
  }, [selectedShift, availableShifts]);

  // Changed from defaults condition
  const hasActiveFilters = Boolean(
    (selectedPlant !== null && selectedPlant !== '') ||
    selectedDate !== '' ||
    selectedMonth !== 10 ||
    selectedYear !== 2026 ||
    (selectedShift && selectedShift !== 'ALL')
  );

  return (
    <div
      ref={panelRef}
      className="energy-filter-toolbar"
      role="toolbar"
      aria-label="Energy Analytics Filter Controls"
    >
      {/* 1. Plant Control */}
      <div className={`energy-filter-item plant-item ${activeDropdown === 'plant' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`energy-filter-trigger ${selectedPlant ? 'has-filter' : ''} ${
            activeDropdown === 'plant' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('plant')}
          aria-expanded={activeDropdown === 'plant'}
          aria-haspopup="listbox"
          aria-label="Filter by Plant"
          title={`Plant: ${selectedPlantLabel}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z" />
              <path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
              <path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" />
              <path d="M10 6h4" />
              <path d="M10 10h4" />
              <path d="M10 14h4" />
            </svg>
          </span>
          <span className="trigger-label">{selectedPlantLabel}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'plant' && (
          <div className="energy-dropdown-popover" role="listbox">
            {PLANT_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`energy-dropdown-option ${
                  (selectedPlant || '') === opt.value ? 'is-selected' : ''
                }`}
                role="option"
                aria-selected={(selectedPlant || '') === opt.value}
                onClick={() => {
                  onSelectPlant && onSelectPlant(opt.value || null);
                  setActiveDropdown(null);
                }}
              >
                <span>{opt.label}</span>
                {(selectedPlant || '') === opt.value && (
                  <svg className="option-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Month Selector Control */}
      <div className={`energy-filter-item month-item ${activeDropdown === 'month' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`energy-filter-trigger ${
            selectedMonth !== 10 || selectedYear !== 2026 ? 'has-filter' : ''
          } ${activeDropdown === 'month' ? 'is-active' : ''}`}
          onClick={() => toggleDropdown('month')}
          aria-expanded={activeDropdown === 'month'}
          aria-haspopup="dialog"
          aria-label="Select Month and Year"
          title={`Month: ${currentMonthObj.label} ${selectedYear}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="4" rx="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </span>
          <span className="trigger-label">{currentMonthObj.label} {selectedYear}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'month' && (
          <div className="energy-month-popover" role="dialog" aria-label="Select Month and Year">
            {/* Year Selector Nav */}
            <div className="energy-year-nav">
              <span style={{ fontSize: '0.72rem', fontWeight: 650, color: '#64748b' }}>Select Year:</span>
              <div style={{ display: 'flex', gap: '4px' }}>
                {YEARS.map((yr) => (
                  <button
                    key={yr}
                    type="button"
                    className={`energy-year-btn ${selectedYear === yr ? 'is-active' : ''}`}
                    onClick={() => handleYearSelect(yr)}
                  >
                    {yr}
                  </button>
                ))}
              </div>
            </div>

            {/* Months 3x4 Grid */}
            <div className="energy-months-grid">
              {MONTHS.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  className={`energy-month-btn ${selectedMonth === m.value ? 'is-selected' : ''}`}
                  onClick={() => handleMonthSelect(m.value)}
                >
                  {m.short}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 3. Date Selector Control (Calendar Popover strictly for selected month) */}
      <div className={`energy-filter-item date-item ${activeDropdown === 'date' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`energy-filter-trigger ${selectedDate ? 'has-filter' : ''} ${
            activeDropdown === 'date' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('date')}
          aria-expanded={activeDropdown === 'date'}
          aria-haspopup="dialog"
          aria-label="Select Date in Month"
          title={`Date: ${formattedDateLabel}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 2v4" />
              <path d="M16 2v4" />
              <rect width="18" height="18" x="3" y="4" rx="2" />
              <path d="M3 10h18" />
              <path d="m9 16 2 2 4-4" />
            </svg>
          </span>
          <span className="trigger-label">{formattedDateLabel}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'date' && (
          <div className="energy-calendar-popover" role="dialog" aria-label="Calendar Date Picker">
            {/* Quick "All Days" Button */}
            <div className="energy-cal-header">
              <button
                type="button"
                className={`energy-cal-all-btn ${!selectedDate ? 'is-active' : ''}`}
                onClick={handleSelectAllDays}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <rect width="18" height="18" x="3" y="4" rx="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                </svg>
                <span>All Days in {currentMonthObj.label} ({daysInMonth}d)</span>
              </button>
            </div>

            {/* Current Month & Year Header */}
            <div className="energy-cal-title-row">
              <span className="energy-cal-title">{currentMonthObj.label} {selectedYear}</span>
              <span className="energy-cal-hint">Single Month View</span>
            </div>

            {/* Weekday Row */}
            <div className="energy-cal-weekdays" aria-hidden="true">
              {WEEKDAYS.map((day) => (
                <span key={day} className="energy-cal-weekday">
                  {day}
                </span>
              ))}
            </div>

            {/* Days Grid: strictly dates of current selected month */}
            <div className="energy-cal-grid" role="grid" aria-label={`Days of ${currentMonthObj.label} ${selectedYear}`}>
              {/* Empty leading slots for alignment */}
              {Array.from({ length: firstDayOfWeek }).map((_, i) => (
                <div key={`empty-lead-${i}`} className="energy-cal-empty" aria-hidden="true" />
              ))}

              {/* Exact days for current month */}
              {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((day) => {
                const isSelected = activeSelectedDay === day;
                return (
                  <button
                    key={`day-${day}`}
                    type="button"
                    className={`energy-cal-day ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => handleDateClick(day)}
                    aria-label={`${currentMonthObj.label} ${day}, ${selectedYear}`}
                    aria-selected={isSelected}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 4. Shift Control (Immediately after All Days / Date) */}
      <div className={`energy-filter-item shift-item ${activeDropdown === 'shift' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`energy-filter-trigger ${selectedShift && selectedShift !== 'ALL' ? 'has-filter' : ''} ${
            activeDropdown === 'shift' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('shift')}
          aria-expanded={activeDropdown === 'shift'}
          aria-haspopup="listbox"
          aria-label="Filter by Shift"
          title={`Shift: ${selectedShiftLabel}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </span>
          <span className="trigger-label">{selectedShiftLabel}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'shift' && (
          <div className="energy-dropdown-popover shift-popover" role="listbox">
            {(availableShifts && availableShifts.length > 0 ? availableShifts : DEFAULT_SHIFTS).map((opt) => (
              <div
                key={opt.value}
                className={`energy-dropdown-option ${
                  (selectedShift || 'ALL') === opt.value ? 'is-selected' : ''
                }`}
                role="option"
                aria-selected={(selectedShift || 'ALL') === opt.value}
                onClick={() => {
                  onSelectShift && onSelectShift(opt.value);
                  setActiveDropdown(null);
                }}
              >
                <span>{opt.label}</span>
                {(selectedShift || 'ALL') === opt.value && (
                  <svg className="option-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Clear Filters Button (shown only when at least one filter is changed) */}
      {hasActiveFilters && (
        <div className="energy-filter-item clear-item">
          <button
            type="button"
            className="energy-clear-btn"
            onClick={() => {
              onResetFilters && onResetFilters();
              setActiveDropdown(null);
            }}
            title="Reset all filters to defaults (All Plants, October 2026, All Days)"
            aria-label="Clear all filters"
          >
            <svg
              className="clear-icon"
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            <span>Clear Filters</span>
          </button>
        </div>
      )}
    </div>
  );
}
