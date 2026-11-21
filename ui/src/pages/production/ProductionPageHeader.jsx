import React, { useState, useMemo, useEffect, useRef } from 'react';
import './production-filters.css';

const PLANT_OPTIONS = [
  { value: '', label: 'All Plants (Consolidated)', shortLabel: 'All Plants' },
  { value: 'IN-TN-01', label: 'Plant IN-TN-01 (Tamil Nadu)', shortLabel: 'Plant IN-TN-01' },
  { value: 'IN-KA-01', label: 'Plant IN-KA-01 (Karnataka)', shortLabel: 'Plant IN-KA-01' },
];

const LINE_OPTIONS = [
  { value: '', label: 'All Manufacturing Lines', shortLabel: 'All Lines' },
  { value: 'SMT-L1', label: 'SMT-L1 (SMT Line 1 · TN)', shortLabel: 'SMT-L1' },
  { value: 'SMT-L2', label: 'SMT-L2 (SMT Line 2 · KA)', shortLabel: 'SMT-L2' },
  { value: 'FAL-L1', label: 'FAL-L1 (Final Assembly 1 · TN)', shortLabel: 'FAL-L1' },
  { value: 'FAL-L2', label: 'FAL-L2 (Final Assembly 2 · KA)', shortLabel: 'FAL-L2' },
];

const PRODUCT_OPTIONS = [
  { value: '', label: 'All Product SKUs', shortLabel: 'All Products' },
  { value: 'SPH-A15-128', label: 'Aster 15 128GB', shortLabel: 'Aster 15 128GB' },
  { value: 'SPH-A15-256', label: 'Aster 15 256GB', shortLabel: 'Aster 15 256GB' },
  { value: 'SPH-PRO-256', label: 'Aster Pro 256GB', shortLabel: 'Aster Pro 256GB' },
];

const SHIFT_OPTIONS = [
  { value: '', label: 'All Operating Shifts', shortLabel: 'All Shifts' },
  { value: 'A', label: 'Shift A (Morning)', shortLabel: 'Shift A' },
  { value: 'B', label: 'Shift B (Afternoon)', shortLabel: 'Shift B' },
  { value: 'C', label: 'Shift C (Night)', shortLabel: 'Shift C' },
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

export default function ProductionPageHeader({
  selectedPlant,
  onSelectPlant,
  selectedLine,
  onSelectLine,
  selectedProduct,
  onSelectProduct,
  selectedShift,
  onSelectShift,
  selectedMonth = 10,
  onSelectedMonthChange,
  selectedYear = 2026,
  onSelectedYearChange,
  selectedDate = '',
  onSelectDate,
  onResetFilters,
}) {
  const panelRef = useRef(null);
  const [activeDropdown, setActiveDropdown] = useState(null);

  // Close dropdowns on outside click or Escape
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

  // Selected values labels
  const selectedPlantLabel = useMemo(() => {
    const opt = PLANT_OPTIONS.find((p) => p.value === (selectedPlant || ''));
    return opt ? opt.shortLabel : 'All Plants';
  }, [selectedPlant]);

  const selectedLineLabel = useMemo(() => {
    const opt = LINE_OPTIONS.find((l) => l.value === (selectedLine || ''));
    return opt ? opt.shortLabel : 'All Lines';
  }, [selectedLine]);

  const selectedProductLabel = useMemo(() => {
    const opt = PRODUCT_OPTIONS.find((pr) => pr.value === (selectedProduct || ''));
    return opt ? opt.shortLabel : 'All Products';
  }, [selectedProduct]);

  const selectedShiftLabel = useMemo(() => {
    const opt = SHIFT_OPTIONS.find((s) => s.value === (selectedShift || ''));
    return opt ? opt.shortLabel : 'All Shifts';
  }, [selectedShift]);

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

  return (
    <div
      ref={panelRef}
      className="production-filter-panel"
      role="toolbar"
      aria-label="Production Analytics Filter Controls"
    >
      {/* 1. Plant Control */}
      <div className={`prod-filter-item plant-item ${activeDropdown === 'plant' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`prod-filter-trigger ${selectedPlant ? 'has-filter' : ''} ${
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
          <div className="prod-dropdown-popover" role="listbox">
            {PLANT_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`prod-dropdown-option ${
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

      {/* 2. Line Control */}
      <div className={`prod-filter-item line-item ${activeDropdown === 'line' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`prod-filter-trigger ${selectedLine ? 'has-filter' : ''} ${
            activeDropdown === 'line' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('line')}
          aria-expanded={activeDropdown === 'line'}
          aria-haspopup="listbox"
          aria-label="Filter by Manufacturing Line"
          title={`Line: ${selectedLineLabel}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
          </span>
          <span className="trigger-label">{selectedLineLabel}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'line' && (
          <div className="prod-dropdown-popover" role="listbox">
            {LINE_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`prod-dropdown-option ${
                  (selectedLine || '') === opt.value ? 'is-selected' : ''
                }`}
                role="option"
                aria-selected={(selectedLine || '') === opt.value}
                onClick={() => {
                  onSelectLine && onSelectLine(opt.value || null);
                  setActiveDropdown(null);
                }}
              >
                <span>{opt.label}</span>
                {(selectedLine || '') === opt.value && (
                  <svg className="option-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Product Control */}
      <div className={`prod-filter-item product-item ${activeDropdown === 'product' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`prod-filter-trigger ${selectedProduct ? 'has-filter' : ''} ${
            activeDropdown === 'product' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('product')}
          aria-expanded={activeDropdown === 'product'}
          aria-haspopup="listbox"
          aria-label="Filter by Product SKU"
          title={`Product: ${selectedProductLabel}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
              <path d="m3.3 7 8.7 5 8.7-5" />
              <path d="M12 22V12" />
            </svg>
          </span>
          <span className="trigger-label">{selectedProductLabel}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'product' && (
          <div className="prod-dropdown-popover" role="listbox">
            {PRODUCT_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`prod-dropdown-option ${
                  (selectedProduct || '') === opt.value ? 'is-selected' : ''
                }`}
                role="option"
                aria-selected={(selectedProduct || '') === opt.value}
                onClick={() => {
                  onSelectProduct && onSelectProduct(opt.value || null);
                  setActiveDropdown(null);
                }}
              >
                <span>{opt.label}</span>
                {(selectedProduct || '') === opt.value && (
                  <svg className="option-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Shift Control */}
      <div className={`prod-filter-item shift-item ${activeDropdown === 'shift' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`prod-filter-trigger ${selectedShift ? 'has-filter' : ''} ${
            activeDropdown === 'shift' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('shift')}
          aria-expanded={activeDropdown === 'shift'}
          aria-haspopup="listbox"
          aria-label="Filter by Operating Shift"
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
          <div className="prod-dropdown-popover" role="listbox">
            {SHIFT_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`prod-dropdown-option ${
                  (selectedShift || '') === opt.value ? 'is-selected' : ''
                }`}
                role="option"
                aria-selected={(selectedShift || '') === opt.value}
                onClick={() => {
                  onSelectShift && onSelectShift(opt.value || null);
                  setActiveDropdown(null);
                }}
              >
                <span>{opt.label}</span>
                {(selectedShift || '') === opt.value && (
                  <svg className="option-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 5. Month & Year Control */}
      <div className={`prod-filter-item month-item ${activeDropdown === 'month' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`prod-filter-trigger ${
            activeDropdown === 'month' ? 'is-active' : ''
          }`}
          onClick={() => toggleDropdown('month')}
          aria-expanded={activeDropdown === 'month'}
          aria-haspopup="dialog"
          aria-label="Select Month and Year"
          title={`Month: ${currentMonthObj.label} ${selectedYear}`}
        >
          <span className="trigger-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </span>
          <span className="trigger-label">{`${currentMonthObj.short} ${selectedYear}`}</span>
          <span className="trigger-chevron" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </span>
        </button>

        {activeDropdown === 'month' && (
          <div className="prod-month-popover" role="dialog" aria-label="Month & Year Selector">
            {/* Year Switcher Header */}
            <div className="month-popover-year-bar">
              <button
                type="button"
                className="year-nav-btn"
                disabled={YEARS.indexOf(selectedYear) <= 0}
                onClick={() => {
                  const idx = YEARS.indexOf(selectedYear);
                  if (idx > 0) handleYearSelect(YEARS[idx - 1]);
                }}
                aria-label="Previous Year"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
              <span className="popover-year-label">{selectedYear}</span>
              <button
                type="button"
                className="year-nav-btn"
                disabled={YEARS.indexOf(selectedYear) >= YEARS.length - 1}
                onClick={() => {
                  const idx = YEARS.indexOf(selectedYear);
                  if (idx < YEARS.length - 1) handleYearSelect(YEARS[idx + 1]);
                }}
                aria-label="Next Year"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            </div>

            {/* 12 Months Grid */}
            <div className="month-popover-grid">
              {MONTHS.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  className={`month-cell-btn ${
                    selectedMonth === m.value ? 'is-selected' : ''
                  }`}
                  onClick={() => handleMonthSelect(m.value)}
                >
                  {m.short}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 6. Date Control (Calendar Popover) */}
      <div className={`prod-filter-item date-item ${activeDropdown === 'date' ? 'is-open' : ''}`}>
        <button
          type="button"
          className={`prod-filter-trigger ${selectedDate ? 'has-filter' : ''} ${
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
          <div className="prod-calendar-popover" role="dialog" aria-label="Calendar Date Picker">
            {/* "All Days" Quick Selection Button */}
            <div className="cal-popover-header">
              <button
                type="button"
                className={`cal-all-days-btn ${!selectedDate ? 'is-active' : ''}`}
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

            {/* Current Month & Year Display */}
            <div className="cal-month-title-row">
              <span className="cal-month-title">{currentMonthObj.label} {selectedYear}</span>
              <span className="cal-scope-hint">Single Month View</span>
            </div>

            {/* Weekday Labels Row */}
            <div className="cal-weekdays-row" aria-hidden="true">
              {WEEKDAYS.map((day) => (
                <span key={day} className="cal-weekday-label">
                  {day}
                </span>
              ))}
            </div>

            {/* Calendar Grid: Only dates for currently selected month */}
            <div className="cal-days-grid" role="grid" aria-label={`Days of ${currentMonthObj.label} ${selectedYear}`}>
              {/* Empty leading slots for days before 1st of the month (NO previous month dates) */}
              {Array.from({ length: firstDayOfWeek }).map((_, i) => (
                <div key={`empty-lead-${i}`} className="cal-cell-empty" aria-hidden="true" />
              ))}

              {/* Exact days for current month */}
              {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((day) => {
                const isSelected = activeSelectedDay === day;
                return (
                  <button
                    key={`day-${day}`}
                    type="button"
                    className={`cal-day-cell ${isSelected ? 'is-selected' : ''}`}
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

      {/* 7. Reset Button */}
      <div className="prod-filter-item reset-item">
        <button
          type="button"
          className="prod-reset-btn"
          onClick={() => {
            onResetFilters && onResetFilters();
            setActiveDropdown(null);
          }}
          title="Reset all filters to defaults"
          aria-label="Reset all filters"
        >
          <svg
            className="reset-icon"
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
          <span>Reset</span>
        </button>
      </div>
    </div>
  );
}
