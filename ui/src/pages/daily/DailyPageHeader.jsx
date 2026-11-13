import React from 'react';
import AnalyticsPageHeader from '../../components/common/AnalyticsPageHeader';

export default function DailyPageHeader({
  selectedDate,
  onDateChange,
  selectedPlant,
  onSelectPlant,
  lastRefreshed,
  onRefresh,
  refreshing,
  dateWarning,
  minDate = '2026-01-01',
  maxDate = '2030-12-31',
}) {
  return (
    <AnalyticsPageHeader
      badge="Operational Intelligence"
      title="Daily Analysis"
      subtitle="Daily energy and production performance overview, Specific Energy Consumption (SEC) benchmarks, and automated anomaly auditing."
      selectedPlant={selectedPlant}
      onSelectPlant={onSelectPlant}
      isDaily={true}
      selectedDate={selectedDate}
      onDateChange={onDateChange}
      minDate={minDate}
      maxDate={maxDate}
      dateWarning={dateWarning}
      onRefresh={onRefresh}
      refreshing={refreshing}
      lastRefreshed={lastRefreshed}
    />
  );
}
