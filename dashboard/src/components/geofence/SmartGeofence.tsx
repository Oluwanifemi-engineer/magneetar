"use client";

import { useState, useEffect, useCallback } from "react";
import {
  MapPin,
  Plus,
  Trash2,
  Brain,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Zap,
  Home,
  Briefcase,
  GraduationCap,
  MapPinned,
  RefreshCw,
} from "lucide-react";

interface SmartZone {
  id: string;
  name: string;
  zone_type: string;
  lat: number;
  lng: number;
  radius_meters: number;
  alert_on_enter: boolean;
  alert_on_exit: boolean;
  active_hours_start: number;
  active_hours_end: number;
}

interface Anomaly {
  device_id: string;
  device_name: string;
  anomaly_type: string;
  description: string;
  severity: string;
  detected_at: string;
  location: { lat: number; lng: number } | null;
}

interface RoutinePattern {
  device_id: string;
  location_name: string;
  avg_arrival_hour: number;
  avg_departure_hour: number;
  frequency_days_per_week: number;
  confidence: number;
}

const ZONE_TYPES = [
  { value: "home", label: "Home", icon: Home, color: "bg-blue-100 text-blue-700" },
  { value: "work", label: "Work", icon: Briefcase, color: "bg-amber-100 text-amber-700" },
  { value: "school", label: "School", icon: GraduationCap, color: "bg-emerald-100 text-emerald-700" },
  { value: "custom", label: "Custom", icon: MapPinned, color: "bg-purple-100 text-purple-700" },
];

const SEVERITY_CONFIG = {
  low: { color: "text-mag-text-muted", bg: "bg-mag-surface", label: "Low" },
  medium: { color: "text-amber-400", bg: "bg-amber-500/10", label: "Medium" },
  high: { color: "text-red-400", bg: "bg-red-500/10", label: "High" },
};

export function SmartGeofence() {
  const [zones, setZones] = useState<SmartZone[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [patterns, setPatterns] = useState<RoutinePattern[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [activeTab, setActiveTab] = useState<"zones" | "anomalies" | "patterns">("zones");
  const [loading, setLoading] = useState(false);
  const [autoDiscovering, setAutoDiscovering] = useState(false);
  const [form, setForm] = useState({
    name: "",
    zone_type: "custom",
    lat: 6.5244,
    lng: 3.3792,
    radius_meters: 200,
    alert_on_enter: true,
    alert_on_exit: true,
    active_hours_start: 0,
    active_hours_end: 23,
  });

  const fetchZones = useCallback(async () => {
    try {
      const res = await fetch("/api/geofence/zones", {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (res.ok) {
        const data = await res.json();
        setZones(data.zones);
      }
    } catch {
      // silently fail
    }
  }, []);

  const fetchAnomalies = useCallback(async () => {
    try {
      const res = await fetch("/api/geofence/anomalies", {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAnomalies(data.anomalies);
      }
    } catch {
      // silently fail
    }
  }, []);

  const fetchPatterns = useCallback(async () => {
    try {
      const res = await fetch("/api/geofence/patterns", {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (res.ok) {
        const data = await res.json();
        setPatterns(data.patterns);
      }
    } catch {
      // silently fail
    }
  }, []);

  useEffect(() => {
    fetchZones();
    fetchAnomalies();
    fetchPatterns();
  }, [fetchZones, fetchAnomalies, fetchPatterns]);

  const addZone = async () => {
    if (!form.name) return;

    setLoading(true);
    try {
      const res = await fetch("/api/geofence/zone", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify(form),
      });

      if (res.ok) {
        setShowAddForm(false);
        setForm({
          name: "",
          zone_type: "custom",
          lat: 6.5244,
          lng: 3.3792,
          radius_meters: 200,
          alert_on_enter: true,
          alert_on_exit: true,
          active_hours_start: 0,
          active_hours_end: 23,
        });
        fetchZones();
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  const deleteZone = async (id: string) => {
    if (!confirm("Delete this smart zone?")) return;

    try {
      await fetch(`/api/geofence/zone/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      fetchZones();
    } catch {
      // silently fail
    }
  };

  const autoDiscover = async () => {
    setAutoDiscovering(true);
    try {
      const res = await fetch("/api/geofence/auto-discover", {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (res.ok) {
        const data = await res.json();
        alert(`Discovered ${data.zones.length} new zones!`);
        fetchZones();
      }
    } catch {
      // silently fail
    } finally {
      setAutoDiscovering(false);
    }
  };

  const getZoneIcon = (type: string) => {
    const found = ZONE_TYPES.find((z) => z.value === type);
    return found ? found.icon : MapPinned;
  };

  const getZoneColor = (type: string) => {
    const found = ZONE_TYPES.find((z) => z.value === type);
    return found ? found.color : "bg-mag-surface text-mag-text";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-mag-primary to-blue-600 flex items-center justify-center">
            <Brain size={20} className="text-white" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-mag-text">Smart Geofencing</h2>
            <p className="text-sm text-mag-text-muted">AI-powered zones that learn your routines</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={autoDiscover}
            disabled={autoDiscovering}
            className="flex items-center gap-2 px-4 py-2 bg-mag-primary text-white rounded-lg hover:bg-mag-primary-dim disabled:opacity-50 text-sm font-medium"
          >
            <RefreshCw size={16} className={autoDiscovering ? "animate-spin" : ""} />
            Auto-Discover
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            <Plus size={16} />
            Add Zone
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-mag-surface rounded-lg p-1">
        {[
          { id: "zones" as const, label: "Zones", count: zones.length },
          { id: "anomalies" as const, label: "Anomalies", count: anomalies.length },
          { id: "patterns" as const, label: "Patterns", count: patterns.length },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-mag-surface-raised text-mag-text shadow-sm"
                : "text-mag-text-muted hover:text-mag-text-dim"
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-mag-surface-raised rounded-full text-xs text-mag-text">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Add Form */}
      {showAddForm && (
        <div className="bg-mag-surface rounded-xl border border-mag-border p-6">
          <h3 className="font-semibold text-mag-text mb-4">Create Smart Zone</h3>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Zone Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="My Home"
                className="w-full px-3 py-2 bg-mag-bg border border-mag-border rounded-lg focus:outline-none focus:border-mag-primary/50 text-mag-text"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Type</label>
              <div className="flex gap-2">
                {ZONE_TYPES.map((type) => {
                  const TypeIcon = type.icon;
                  return (
                    <button
                      key={type.value}
                      onClick={() => setForm({ ...form, zone_type: type.value })}
                      className={`flex items-center gap-1 px-3 py-2 rounded-lg border-2 text-sm ${
                        form.zone_type === type.value
                          ? `border-mag-primary ${type.color}`
                          : "border-mag-border/50 text-mag-text-muted"
                      }`}
                    >
                      <TypeIcon size={14} />
                      {type.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Latitude</label>
              <input
                type="number"
                step="0.0001"
                value={form.lat}
                onChange={(e) => setForm({ ...form, lat: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 bg-mag-bg border border-mag-border rounded-lg focus:outline-none focus:border-mag-primary/50 text-mag-text"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Longitude</label>
              <input
                type="number"
                step="0.0001"
                value={form.lng}
                onChange={(e) => setForm({ ...form, lng: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 bg-mag-bg border border-mag-border rounded-lg focus:outline-none focus:border-mag-primary/50 text-mag-text"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Radius (m)</label>
              <input
                type="number"
                value={form.radius_meters}
                onChange={(e) => setForm({ ...form, radius_meters: parseInt(e.target.value) })}
                className="w-full px-3 py-2 bg-mag-bg border border-mag-border rounded-lg focus:outline-none focus:border-mag-primary/50 text-mag-text"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Active Hours</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="0"
                  max="23"
                  value={form.active_hours_start}
                  onChange={(e) => setForm({ ...form, active_hours_start: parseInt(e.target.value) })}
                  className="w-20 px-3 py-2 bg-mag-bg border border-mag-border rounded-lg focus:outline-none focus:border-mag-primary/50 text-mag-text"
                />
                <span className="self-center text-mag-text-muted">to</span>
                <input
                  type="number"
                  min="0"
                  max="23"
                  value={form.active_hours_end}
                  onChange={(e) => setForm({ ...form, active_hours_end: parseInt(e.target.value) })}
                  className="w-20 px-3 py-2 bg-mag-bg border border-mag-border rounded-lg focus:outline-none focus:border-mag-primary/50 text-mag-text"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-mag-text-muted mb-1">Alerts</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.alert_on_enter}
                    onChange={(e) => setForm({ ...form, alert_on_enter: e.target.checked })}
                    className="rounded border-mag-border text-mag-primary"
                  />
                  <span className="text-sm text-mag-text">On Enter</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.alert_on_exit}
                    onChange={(e) => setForm({ ...form, alert_on_exit: e.target.checked })}
                    className="rounded border-mag-border text-mag-primary"
                  />
                  <span className="text-sm text-mag-text">On Exit</span>
                </label>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={addZone}
              disabled={loading || !form.name}
              className="px-4 py-2 bg-mag-primary text-white rounded-lg hover:bg-mag-primary-dim disabled:opacity-50 text-sm font-medium"
            >
              {loading ? "Creating..." : "Create Zone"}
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 border border-mag-border text-mag-text-muted rounded-lg hover:bg-mag-surface-raised hover:text-mag-text text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Zones Tab */}
      {activeTab === "zones" && (
        <div className="space-y-3">
          {zones.length === 0 ? (
            <div className="bg-mag-surface rounded-xl p-8 text-center">
              <MapPin size={40} className="mx-auto text-mag-text-muted mb-3" />
              <h3 className="font-medium text-mag-text mb-1">No Smart Zones Yet</h3>
              <p className="text-sm text-mag-text-muted">
                Create zones or use Auto-Discover to learn your routines.
              </p>
            </div>
          ) : (
            zones.map((zone) => {
              const ZoneIcon = getZoneIcon(zone.zone_type);
              return (
                <div
                  key={zone.id}
                  className="bg-mag-surface rounded-xl border border-mag-border p-4 flex items-center justify-between"
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-lg ${getZoneColor(zone.zone_type)} flex items-center justify-center`}>
                      <ZoneIcon size={18} />
                    </div>
                    <div>
                      <p className="font-medium text-mag-text">{zone.name}</p>
                      <p className="text-sm text-mag-text-muted">
                        {zone.radius_meters}m radius · {zone.active_hours_start}:00-{zone.active_hours_end}:00
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="flex gap-2">
                      {zone.alert_on_enter && (
                        <span className="px-2 py-1 bg-mag-primary/10 text-mag-primary rounded-full text-xs">
                          Enter
                        </span>
                      )}
                      {zone.alert_on_exit && (
                        <span className="px-2 py-1 bg-amber-500/10 text-amber-400 rounded-full text-xs">
                          Exit
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => deleteZone(zone.id)}
                      className="p-2 text-mag-text-muted hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Anomalies Tab */}
      {activeTab === "anomalies" && (
        <div className="space-y-3">
          {anomalies.length === 0 ? (
            <div className="bg-mag-surface rounded-xl p-8 text-center">
              <CheckCircle2 size={40} className="mx-auto text-emerald-400 mb-3" />
              <h3 className="font-medium text-mag-text mb-1">No Anomalies Detected</h3>
              <p className="text-sm text-mag-text-muted">
                All devices are following their usual patterns.
              </p>
            </div>
          ) : (
            anomalies.map((anomaly, i) => {
              const sevConfig = SEVERITY_CONFIG[anomaly.severity as keyof typeof SEVERITY_CONFIG];
              return (
                <div
                  key={i}
                  className="bg-mag-surface rounded-xl border border-mag-border p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <AlertTriangle size={18} className={sevConfig.color} />
                      <div>
                        <p className="font-medium text-mag-text">{anomaly.device_name}</p>
                        <p className="text-sm text-mag-text-muted">{anomaly.description}</p>
                        <p className="text-xs text-mag-text-muted mt-1">
                          <Clock size={12} className="inline mr-1 text-mag-text-muted" />
                          {new Date(anomaly.detected_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${sevConfig.bg} ${sevConfig.color}`}>
                      {sevConfig.label}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Patterns Tab */}
      {activeTab === "patterns" && (
        <div className="space-y-3">
          {patterns.length === 0 ? (
            <div className="bg-mag-surface rounded-xl p-8 text-center">
              <Brain size={40} className="mx-auto text-mag-text-muted mb-3" />
              <h3 className="font-medium text-mag-text mb-1">No Patterns Learned Yet</h3>
              <p className="text-sm text-mag-text-muted">
                Patterns emerge after 1+ weeks of location data.
              </p>
            </div>
          ) : (
            patterns.map((pattern, i) => (
              <div
                key={i}
                className="bg-mag-surface rounded-xl border border-mag-border p-4"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-mag-text">{pattern.location_name}</p>
                    <p className="text-sm text-mag-text-muted">
                      Usually {Math.floor(pattern.avg_arrival_hour)}:{String(Math.round((pattern.avg_arrival_hour % 1) * 60)).padStart(2, "0")} -{" "}
                      {Math.floor(pattern.avg_departure_hour)}:{String(Math.round((pattern.avg_departure_hour % 1) * 60)).padStart(2, "0")}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-mag-text">
                      {pattern.frequency_days_per_week} days/week
                    </p>
                    <div className="flex items-center gap-1">
                      <Zap size={12} className="text-amber-400" />
                      <span className="text-xs text-mag-text-muted">
                        {Math.round(pattern.confidence * 100)}% confidence
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* How It Works */}
      <div className="bg-mag-surface-raised rounded-xl p-6 border border-mag-border">
        <h3 className="font-semibold text-mag-text mb-3">How Smart Geofencing Works</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-mag-primary/10 flex items-center justify-center flex-shrink-0">
              <MapPin size={16} className="text-mag-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-mag-text">Create Zones</p>
              <p className="text-xs text-mag-text-muted">Define safe areas for your devices</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-mag-primary/10 flex items-center justify-center flex-shrink-0">
              <Brain size={16} className="text-mag-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-mag-text">Learn Patterns</p>
              <p className="text-xs text-mag-text-muted">AI learns daily routines over time</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-mag-primary/10 flex items-center justify-center flex-shrink-0">
              <AlertTriangle size={16} className="text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-mag-text">Detect Anomalies</p>
              <p className="text-xs text-mag-text-muted">Get alerts for unusual behavior</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-mag-primary/10 flex items-center justify-center flex-shrink-0">
              <Zap size={16} className="text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-mag-text">Predictive Alerts</p>
              <p className="text-xs text-mag-text-muted">"Usually arrives by 9am, not yet seen"</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
