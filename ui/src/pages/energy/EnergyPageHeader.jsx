import React from 'react';
import AnalyticsPageHeader from '../../components/common/AnalyticsPageHeader';

export default function EnergyPageHeader({
  dateRange,
  lastRefreshed,
  onRefresh,
  refreshing,
  selectedPlant,
  onSelectPlant,
}) {
  return (
    <AnalyticsPageHeader
      badge="Dataset Analytics"
      title="Energy Analytics"
      subtitle="Hourly interval energy consumption, power factor monitoring, and meter-level telemetry."
      selectedPlant={selectedPlant}
      onSelectPlant={onSelectPlant}
      dateRange={dateRange}
      onRefresh={onRefresh}
      refreshing={refreshing}
      lastRefreshed={lastRefreshed}
    />
  );
}
