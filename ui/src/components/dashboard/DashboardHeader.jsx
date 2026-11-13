import React from 'react';
import AnalyticsPageHeader from '../common/AnalyticsPageHeader';

export default function DashboardHeader({
  dateRange,
  lastRefreshed,
  onRefresh,
  refreshing,
  selectedPlant,
  onSelectPlant,
}) {
  return (
    <AnalyticsPageHeader
      badge="Manufacturing Intelligence"
      title="Industrial Energy Dashboard"
      subtitle="Operational overview of plant-wide energy consumption, production throughput, Specific Energy Consumption (SEC), and automated anomaly monitoring."
      selectedPlant={selectedPlant}
      onSelectPlant={onSelectPlant}
      dateRange={dateRange}
      onRefresh={onRefresh}
      refreshing={refreshing}
      lastRefreshed={lastRefreshed}
    />
  );
}
