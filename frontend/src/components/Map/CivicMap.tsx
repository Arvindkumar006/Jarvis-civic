import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { MapPin, Navigation, CheckCircle2, Crosshair, AlertCircle, ShieldAlert } from 'lucide-react';
import './CivicMap.css';

export interface MapMarkerItem {
  id: string;
  lat: number;
  lng: number;
  category: 'WATER' | 'ROAD' | 'LIGHT' | 'WASTE' | 'DEFAULT';
  title: string;
  subtitle: string;
  department?: string;
  urgency?: string;
  status?: string;
}

interface CivicMapProps {
  center?: [number, number]; // [lat, lng]
  zoom?: number;
  markers?: MapMarkerItem[];
  mode?: 'product_visualization' | 'case_tracking';
  interactive?: boolean;
  onLocationSelect?: (lat: number, lng: number, confirmedName?: string) => void;
  locationName?: string;
  landmark?: string;
  allowManualPin?: boolean;
  className?: string;
}

// Sample civic markers for product visualization
export const DEFAULT_SAMPLE_CIVIC_MARKERS: MapMarkerItem[] = [
  {
    id: 'sig-1',
    lat: 13.0604,
    lng: 80.2496,
    category: 'WATER',
    title: 'Severe Waterlogging',
    subtitle: 'Anna Salai near Thousand Lights',
    department: 'Drainage & Stormwater',
    urgency: 'Medium',
    status: 'Sample Signal',
  },
  {
    id: 'sig-2',
    lat: 13.0418,
    lng: 80.2341,
    category: 'ROAD',
    title: 'Dangerous Road Pothole',
    subtitle: 'Usman Road Flyover, T. Nagar',
    department: 'PWD Roads',
    urgency: 'High',
    status: 'Sample Signal',
  },
  {
    id: 'sig-3',
    lat: 13.0067,
    lng: 80.2024,
    category: 'LIGHT',
    title: 'Streetlight Grid Blackout',
    subtitle: 'Guindy Industrial Estate 4th Cross',
    department: 'Electrical Lighting',
    urgency: 'Medium',
    status: 'Sample Signal',
  },
  {
    id: 'sig-4',
    lat: 12.9815,
    lng: 80.218,
    category: 'WASTE',
    title: 'Commercial Waste Dump',
    subtitle: 'Bypass Road, Velachery',
    department: 'Solid Waste Management',
    urgency: 'Low',
    status: 'Sample Signal',
  },
];

// Known civic coordinates mapping for Chennai metropolitan area text detection
export const KNOWN_CIVIC_COORDINATES: Record<string, [number, number]> = {
  'anna salai': [13.0604, 80.2496],
  'thousand lights': [13.0604, 80.2496],
  'mg road': [12.9716, 77.5946],
  'sector 4': [12.9165, 77.6346],
  't. nagar': [13.0418, 80.2341],
  't nagar': [13.0418, 80.2341],
  'guindy': [13.0067, 80.2024],
  'velachery': [12.9815, 80.218],
  'adyar': [13.0012, 80.2565],
  'royapettah': [13.0538, 80.2612],
  'default': [13.0604, 80.2496], // Central Chennai corridor
};

export const getApproxCoordinates = (locationText?: string | null): [number, number] | null => {
  if (!locationText) return null;
  const lower = locationText.toLowerCase().trim();
  for (const [key, coords] of Object.entries(KNOWN_CIVIC_COORDINATES)) {
    if (key !== 'default' && lower.includes(key)) {
      return coords;
    }
  }
  return null;
};

export const CivicMap: React.FC<CivicMapProps> = ({
  center,
  zoom = 14,
  markers,
  mode = 'case_tracking',
  interactive = true,
  onLocationSelect,
  locationName,
  landmark,
  allowManualPin = true,
  className = '',
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const activeMarkerRef = useRef<L.Marker | null>(null);
  const [selectedCoords, setSelectedCoords] = useState<[number, number] | null>(null);
  const [isLocationConfirmed, setIsLocationConfirmed] = useState(false);
  const [selectedSignal, setSelectedSignal] = useState<MapMarkerItem | null>(null);

  // Read CARTO API key ONLY from environment (never hard-coded)
  const cartoApiKey = (import.meta.env.VITE_CARTO_API_KEY as string | undefined)?.trim();
  const isKeyConfigured = Boolean(cartoApiKey && cartoApiKey.length > 0);

  // Derive initial position
  const initialPos = center || getApproxCoordinates(locationName) || KNOWN_CIVIC_COORDINATES.default;

  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (mapInstanceRef.current) {
      mapInstanceRef.current.remove();
      mapInstanceRef.current = null;
    }

    if (!isKeyConfigured) {
      // Do not initialize raster tiles without key to prevent watermark pollution
      return;
    }

    try {
      const map = L.map(mapContainerRef.current, {
        center: initialPos,
        zoom: zoom,
        zoomControl: false,
        attributionControl: true,
      });

      // CARTO Dark Matter raster tile layer with environment API key
      L.tileLayer(`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=${cartoApiKey}`, {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
      }).addTo(map);

      // Add zoom control at bottom right
      L.control.zoom({ position: 'bottomright' }).addTo(map);

      mapInstanceRef.current = map;

      // Add signal markers: only use sample markers when explicitly in product visualization mode
      const activeMarkers = mode === 'product_visualization'
        ? (markers && markers.length > 0 ? markers : DEFAULT_SAMPLE_CIVIC_MARKERS)
        : (markers || []);
      activeMarkers.forEach((m) => {
        const markerIcon = L.divIcon({
          className: 'civic-map-div-icon',
          html: `<div class="marker-pulse-ring category-${m.category.toLowerCase()}">
                   <div class="marker-core-dot"></div>
                 </div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });

        const marker = L.marker([m.lat, m.lng], { icon: markerIcon }).addTo(map);

        marker.on('click', () => {
          setSelectedSignal(m);
          map.setView([m.lat, m.lng], Math.max(map.getZoom(), 14), { animate: true });
        });

        marker.bindPopup(
          `<div class="map-popup-card">
             <div class="popup-tag">${m.category} // SAMPLE CIVIC SIGNAL</div>
             <div class="popup-title">${m.title}</div>
             <div class="popup-sub">Location: ${m.subtitle}</div>
             ${m.department ? `<div class="popup-dept">Recommended Department: ${m.department}</div>` : ''}
             ${m.urgency ? `<div class="popup-urgency">Urgency: ${m.urgency}</div>` : ''}
             <div class="popup-notice">SAMPLE CIVIC SIGNAL • PRODUCT VISUALIZATION</div>
           </div>`,
          { className: 'civic-dark-popup' }
        );
      });

      // Handle map click for citizen manual pinning
      if (allowManualPin && interactive) {
        map.on('click', (e: L.LeafletMouseEvent) => {
          const { lat, lng } = e.latlng;
          setSelectedCoords([lat, lng]);
          setIsLocationConfirmed(false);

          if (activeMarkerRef.current) {
            activeMarkerRef.current.setLatLng([lat, lng]);
          } else {
            const activeIcon = L.divIcon({
              className: 'civic-active-pin-icon',
              html: `<div class="active-pin-shell">
                       <span class="pin-beacon"></span>
                       <div class="pin-head">📍</div>
                     </div>`,
              iconSize: [32, 32],
              iconAnchor: [16, 32],
            });
            activeMarkerRef.current = L.marker([lat, lng], {
              icon: activeIcon,
              draggable: true,
            }).addTo(map);

            activeMarkerRef.current.on('dragend', (dragEvent: any) => {
              const pos = dragEvent.target.getLatLng();
              setSelectedCoords([pos.lat, pos.lng]);
              setIsLocationConfirmed(false);
            });
          }
        });
      }
    } catch (e) {
      // jsdom or unsupported environment fallback
      console.warn('Leaflet map initialization skipped or not supported in this environment.', e);
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [markers?.length, allowManualPin, interactive, isKeyConfigured, cartoApiKey]);

  // Pan to location if updated
  useEffect(() => {
    if (mapInstanceRef.current && locationName) {
      const coords = getApproxCoordinates(locationName);
      if (coords) {
        try {
          mapInstanceRef.current.setView(coords, zoom, { animate: true });
        } catch {
          // ignore in jsdom
        }
      }
    }
  }, [locationName, zoom]);

  const handleConfirmLocation = () => {
    if (selectedCoords) {
      setIsLocationConfirmed(true);
      if (onLocationSelect) {
        onLocationSelect(selectedCoords[0], selectedCoords[1], locationName || 'Map-Confirmed Location');
      }
    }
  };

  return (
    <div className={`civic-map-wrapper crosshair-corner ${className}`} aria-label="Interactive Civic Map">
      {/* Map Header Overlay */}
      <div className="map-hud-overlay">
        <div className="map-telemetry-meta">
          <span className="map-live-dot" />
          <span className="technical-label">GEOSPATIAL AUDIT // CARTO DARK MATTER</span>
        </div>
        {locationName ? (
          <div className="map-reported-location text-detected">
            <MapPin size={13} color="var(--civic-cyan)" />
            <span className="location-name-text">TEXT LOCATION DETECTED: {locationName}</span>
            {landmark && <span className="location-landmark-text">({landmark})</span>}
          </div>
        ) : (
          <div className="map-reported-location dimmed">
            <Crosshair size={13} />
            <span>Click map to pin municipal issue location</span>
          </div>
        )}
      </div>

      {/* Quick Sample Signal Selector Strip */}
      <div className="map-sample-signals-strip">
        <span className="sample-strip-label">SAMPLE CIVIC SIGNALS:</span>
        <div className="sample-chips-row">
          {DEFAULT_SAMPLE_CIVIC_MARKERS.map((sig) => (
            <button
              key={sig.id}
              type="button"
              className={`sample-signal-chip ${selectedSignal?.id === sig.id ? 'active' : ''}`}
              onClick={() => {
                setSelectedSignal(sig);
                if (mapInstanceRef.current) {
                  mapInstanceRef.current.setView([sig.lat, sig.lng], 14, { animate: true });
                }
              }}
              title={`Inspect ${sig.title}`}
            >
              <span className="chip-cat">
                {sig.category === 'WATER' ? '💧' : sig.category === 'ROAD' ? '🛣' : sig.category === 'LIGHT' ? '💡' : '🗑'}{' '}
                {sig.category}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Floating Signal Detail Inspector */}
      {selectedSignal && (
        <div className="map-signal-inspector animate-fade-in crosshair-corner" role="region" aria-label="Signal Details">
          <div className="inspector-head">
            <div className="inspector-tag-row">
              <span className={`inspector-cat-pill cat-${selectedSignal.category.toLowerCase()}`}>{selectedSignal.category}</span>
              <span className="technical-label">SAMPLE CIVIC SIGNAL // PRODUCT VISUALIZATION</span>
            </div>
            <button
              type="button"
              className="btn-close-inspector"
              onClick={() => setSelectedSignal(null)}
              aria-label="Close signal inspector"
            >
              ✕
            </button>
          </div>
          <div className="inspector-title">{selectedSignal.title}</div>
          <div className="inspector-grid">
            <div className="insp-item">
              <span className="insp-key">LOCATION:</span>
              <span className="insp-val">{selectedSignal.subtitle}</span>
            </div>
            {selectedSignal.department && (
              <div className="insp-item">
                <span className="insp-key">RECOMMENDED DEPARTMENT:</span>
                <span className="insp-val highlight">{selectedSignal.department}</span>
              </div>
            )}
            {selectedSignal.urgency && (
              <div className="insp-item">
                <span className="insp-key">URGENCY:</span>
                <span className="insp-val urgency">{selectedSignal.urgency}</span>
              </div>
            )}
            <div className="insp-item">
              <span className="insp-key">STATUS:</span>
              <span className="insp-val">{selectedSignal.status || 'Sample Signal'}</span>
            </div>
          </div>
          <div className="inspector-notice">
            PROTOTYPE • PRODUCT VISUALIZATION • NOT A GOVERNMENT PORTAL
          </div>
        </div>
      )}

      {/* Map Canvas or Graceful Missing Configuration State */}
      {isKeyConfigured ? (
        <div ref={mapContainerRef} className="map-canvas-container" tabIndex={0} />
      ) : (
        <div className="map-config-required-canvas">
          <div className="map-config-dialog">
            <ShieldAlert size={28} color="var(--civic-amber)" />
            <h4 className="config-title">MAP CONFIGURATION REQUIRED</h4>
            <p className="config-desc">
              Add VITE_CARTO_API_KEY to frontend/.env.local to enable CARTO basemaps.
            </p>
            <div className="config-steps">
              <span>1. Add key to <code>frontend/.env.local</code></span>
              <span>2. Set: <code>VITE_CARTO_API_KEY=&lt;key&gt;</code> in <code>.env.local</code></span>
              <span>3. Restart Vite dev server</span>
            </div>
          </div>
        </div>
      )}

      {/* Map Control / Confirmation Footer */}
      <div className="map-footer-bar">
        <div className="map-coord-tag">
          {selectedCoords ? (
            <span>
              LOCATION PINNED: {selectedCoords[0].toFixed(4)}° N, {selectedCoords[1].toFixed(4)}° E •{' '}
              <strong style={{ color: isLocationConfirmed ? 'var(--civic-emerald)' : 'var(--civic-cyan)' }}>
                {isLocationConfirmed ? 'CONFIRMED' : 'Map position selected by citizen'}
              </strong>
            </span>
          ) : (
            <span>
              {locationName ? 'TEXT LOCATION REFERENCE (NOT GPS)' : 'STANDBY • TAP MAP TO PIN'}
            </span>
          )}
        </div>

        {allowManualPin && selectedCoords && isKeyConfigured && (
          <button
            type="button"
            className={`btn-confirm-location ${isLocationConfirmed ? 'confirmed' : ''}`}
            onClick={handleConfirmLocation}
            title="Confirm this spatial location for the civic record"
          >
            {isLocationConfirmed ? (
              <>
                <CheckCircle2 size={13} />
                <span>LOCATION CONFIRMED</span>
              </>
            ) : (
              <>
                <Navigation size={13} />
                <span>CONFIRM LOCATION</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
