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
  onLocationSelect?: (lat: number, lng: number, confirmedName?: string, source?: string) => void;
  locationName?: string;
  street?: string;
  area?: string;
  locality?: string;
  landmark?: string;
  latitude?: number | null;
  longitude?: number | null;
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
// Expanded civic coordinates gazetteer mapping across metropolitan areas in native scripts
export const KNOWN_CIVIC_COORDINATES: Record<string, [number, number]> = {
  // Chennai & Tamil Nadu
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
  'ambattur': [13.1143, 80.1548],
  'pudur': [13.1232, 80.1472],
  'kumaran street': [13.1205, 80.1500],
  'anna nagar': [13.0850, 80.2101],
  'annanagar': [13.0850, 80.2101],
  'mylapore': [13.0368, 80.2676],
  'porur': [13.0382, 80.1565],
  'tambaram': [12.9249, 80.1000],
  'vadapalani': [13.0500, 80.2121],
  'koyambedu': [13.0694, 80.1948],
  'perambur': [13.1075, 80.2434],
  'saidapet': [13.0213, 80.2231],
  'egmore': [13.0732, 80.2609],
  'omr': [12.9654, 80.2461],
  'sholinganallur': [12.9010, 80.2279],
  'chromepet': [12.9516, 80.1462],
  'avadi': [13.1147, 80.1018],
  'madhavaram': [13.1488, 80.2314],
  'triplicane': [13.0587, 80.2757],
  'alwarpet': [13.0336, 80.2520],
  'kodambakkam': [13.0524, 80.2255],
  'central': [13.0827, 80.2707],
  'broadway': [13.0891, 80.2870],
  'குமரன் தெரு': [13.1205, 80.1500],
  'அம்பத்தூர்': [13.1143, 80.1548],
  'புதூர்': [13.1232, 80.1472],
  'அண்ணா சாலை': [13.0604, 80.2496],
  'தி நகர்': [13.0418, 80.2341],
  'கிண்டி': [13.0067, 80.2024],
  'வேளச்சேரி': [12.9815, 80.218],
  'அடையாறு': [13.0012, 80.2565],
  // Delhi NCR
  'delhi': [28.6139, 77.2090],
  'new delhi': [28.6139, 77.2090],
  'दिल्ली': [28.6139, 77.2090],
  'chandni chowk': [28.6506, 77.2303],
  'चांदनी चौक': [28.6506, 77.2303],
  'connaught place': [28.6315, 77.2167],
  'कनॉट प्लेस': [28.6315, 77.2167],
  'karol bagh': [28.6514, 77.1907],
  // Karnataka / Bengaluru
  'bengaluru': [12.9716, 77.5946],
  'bangalore': [12.9716, 77.5946],
  'ಬೆಂಗಳೂರು': [12.9716, 77.5946],
  'koramangala': [12.9352, 77.6245],
  'ಕೋರಮಂಗಲ': [12.9352, 77.6245],
  'indiranagar': [12.9784, 77.6408],
  'ಇಂದಿರಾನಗರ': [12.9784, 77.6408],
  'whitefield': [12.9698, 77.7499],
  'hsr layout': [12.9121, 77.6446],
  // Maharashtra / Mumbai & Pune
  'mumbai': [19.0760, 72.8777],
  'मुंबई': [19.0760, 72.8777],
  'pune': [18.5204, 73.8567],
  'पुणे': [18.5204, 73.8567],
  'dadar': [19.0178, 72.8478],
  'andheri': [19.1136, 72.8697],
  // Telangana / Hyderabad
  'hyderabad': [17.3850, 78.4867],
  'హైదరాబాద్': [17.3850, 78.4867],
  'అంబత్తూరు': [13.1143, 80.1548],
  'banjara hills': [17.4156, 78.4350],
  // West Bengal / Kolkata
  'kolkata': [22.5726, 88.3639],
  'calcutta': [22.5726, 88.3639],
  'কলকাতা': [22.5726, 88.3639],
  'chowrasta': [22.4988, 88.3150],
  'চৌরাস্তা': [22.4988, 88.3150],
  'চৌরাস্তার': [22.4988, 88.3150],
  'howrah': [22.5958, 88.2636],
  'default': [13.0604, 80.2496], // Central Chennai corridor
};

export interface GeocodedLocationResult {
  lat: number;
  lng: number;
  source: 'GEOCODED_EXACT' | 'GEOCODED_LOCALITY' | 'GAZETTEER_FALLBACK' | 'USER_CONFIRMED' | 'UNRESOLVED';
  zoom: number;
  displayName?: string;
  type?: string;
}

// In-memory geocode cache and in-flight query deduplication
const geocodeCache = new Map<string, GeocodedLocationResult>();
const inFlightQueries = new Map<string, Promise<GeocodedLocationResult | null>>();

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

// Result-type-aware zoom level calculation
function computeResultZoom(osmType?: string, osmClass?: string): number {
  const t = (osmType || '').toLowerCase();
  const c = (osmClass || '').toLowerCase();
  if (
    c === 'building' ||
    c === 'highway' ||
    c === 'amenity' ||
    ['residential', 'service', 'living_street', 'house', 'secondary', 'primary', 'tertiary'].includes(t)
  ) {
    return 17; // Street/building precision
  }
  if (['neighbourhood', 'suburb', 'quarter', 'hamlet', 'residential'].includes(t)) {
    return 15; // Neighbourhood precision
  }
  if (['locality', 'village', 'town'].includes(t) || c === 'boundary' || c === 'place') {
    return 14; // Locality precision
  }
  if (['city', 'state', 'county', 'country', 'administrative'].includes(t)) {
    return 12; // City level
  }
  return 15;
}

// Layered Geocoding Resolver:
// 1. Exact/native-language Nominatim query
// 2. Normalized location query + city context
// 3. Locality/suburb fallback
// 4. Civic gazetteer fallback
export const resolveLocationCoordinates = async (
  locationText?: string | null,
  landmarkText?: string | null,
  streetText?: string | null,
  areaText?: string | null,
  localityText?: string | null
): Promise<GeocodedLocationResult | null> => {
  if (!locationText || !locationText.trim()) return null;
  const raw = locationText.trim();
  const cacheKey = `${raw}|${landmarkText || ''}|${streetText || ''}|${localityText || ''}`.toLowerCase();

  // Return cached result immediately
  if (geocodeCache.has(cacheKey)) {
    return geocodeCache.get(cacheKey)!;
  }

  // Deduplicate in-flight promises
  if (inFlightQueries.has(cacheKey)) {
    return inFlightQueries.get(cacheKey)!;
  }

  const resolverPromise = (async (): Promise<GeocodedLocationResult | null> => {
    // In unit test environment, bypass external HTTP
    const isTestEnv =
      import.meta.env.MODE === 'test' ||
      (typeof globalThis !== 'undefined' && Boolean((globalThis as any).process?.env?.NODE_ENV === 'test'));
    if (isTestEnv) {
      const gaz = getApproxCoordinates(raw);
      if (gaz) {
        return {
          lat: gaz[0],
          lng: gaz[1],
          source: 'GAZETTEER_FALLBACK',
          zoom: 14,
          displayName: raw,
        };
      }
      return null;
    }

    // Build layered query candidates
    const queries: Array<{ q: string; isLocalityFallback: boolean }> = [];

    // Layer 1: Exact native-language structured query (street + area + locality)
    if (streetText && (areaText || localityText)) {
      queries.push({
        q: [streetText, areaText, localityText].filter(Boolean).join(', '),
        isLocalityFallback: false,
      });
    }
    if (landmarkText && landmarkText.trim()) {
      queries.push({ q: `${raw}, ${landmarkText.trim()}`, isLocalityFallback: false });
    }
    queries.push({ q: raw, isLocalityFallback: false });

    // Layer 2: Normalized contextual queries (city context)
    const lower = raw.toLowerCase();
    if (
      !lower.includes('chennai') &&
      !lower.includes('bengaluru') &&
      !lower.includes('delhi') &&
      !lower.includes('mumbai') &&
      !lower.includes('pune') &&
      !lower.includes('kolkata') &&
      !lower.includes('hyderabad')
    ) {
      queries.push({ q: `${raw}, India`, isLocalityFallback: false });
    }

    // Layer 3: Locality / Suburb Fallback
    if (localityText && localityText.trim() && localityText !== raw) {
      queries.push({ q: `${localityText.trim()}, India`, isLocalityFallback: true });
    }
    if (areaText && areaText.trim() && areaText !== raw) {
      queries.push({ q: `${areaText.trim()}, India`, isLocalityFallback: true });
    }

    // Dynamic Nominatim Request with 3500ms timeout
    for (const cand of queries) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3500);
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(cand.q)}&limit=1&addressdetails=1`;
        const res = await fetch(url, {
          signal: controller.signal,
          headers: { 'Accept-Language': '*' },
        });
        clearTimeout(timeoutId);

        if (res.ok) {
          const results = await res.json();
          if (Array.isArray(results) && results.length > 0) {
            const first = results[0];
            const lat = parseFloat(first.lat);
            const lon = parseFloat(first.lon);
            if (!isNaN(lat) && !isNaN(lon)) {
              const zoom = computeResultZoom(first.type, first.class);
              const source: GeocodedLocationResult['source'] = cand.isLocalityFallback
                ? 'GEOCODED_LOCALITY'
                : zoom >= 16
                ? 'GEOCODED_EXACT'
                : 'GEOCODED_LOCALITY';

              const result: GeocodedLocationResult = {
                lat,
                lng: lon,
                source,
                zoom,
                displayName: first.display_name,
                type: first.type,
              };
              geocodeCache.set(cacheKey, result);
              return result;
            }
          }
        }
      } catch {
        // Graceful network timeout / CORS fallback to next layer
      }
    }

    // Layer 4: Civic Gazetteer Fallback
    const gazetteer = getApproxCoordinates(raw) || (localityText ? getApproxCoordinates(localityText) : null);
    if (gazetteer) {
      const result: GeocodedLocationResult = {
        lat: gazetteer[0],
        lng: gazetteer[1],
        source: 'GAZETTEER_FALLBACK',
        zoom: 14,
        displayName: raw,
      };
      geocodeCache.set(cacheKey, result);
      return result;
    }

    // Unresolved: do NOT place arbitrary pin
    return null;
  })();

  inFlightQueries.set(cacheKey, resolverPromise);
  try {
    return await resolverPromise;
  } finally {
    inFlightQueries.delete(cacheKey);
  }
};

export const CivicMap: React.FC<CivicMapProps> = ({
  center,
  zoom = 14,
  markers,
  mode = 'case_tracking',
  interactive = true,
  onLocationSelect,
  locationName,
  street,
  area,
  locality,
  landmark,
  latitude,
  longitude,
  allowManualPin = true,
  className = '',
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const activeMarkerRef = useRef<L.Marker | null>(null);
  const [selectedCoords, setSelectedCoords] = useState<[number, number] | null>(null);
  const [locationSource, setLocationSource] = useState<string | null>(null);
  const [isLocationConfirmed, setIsLocationConfirmed] = useState(false);
  const [selectedSignal, setSelectedSignal] = useState<MapMarkerItem | null>(null);

  // Read CARTO API key ONLY from environment (never hard-coded)
  const cartoApiKey = (import.meta.env.VITE_CARTO_API_KEY as string | undefined)?.trim();
  const isKeyConfigured = Boolean(cartoApiKey && cartoApiKey.length > 0);

  // Derive initial position
  const initialPos =
    (latitude != null && longitude != null ? [latitude, longitude] as [number, number] : null) ||
    center ||
    getApproxCoordinates(locationName) ||
    KNOWN_CIVIC_COORDINATES.default;

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

  // Pan to location and place/update active pinpoint dynamically for ANY location
  useEffect(() => {
    let isCancelled = false;

    // If reset or location cleared
    if (!locationName && (latitude == null || longitude == null)) {
      if (activeMarkerRef.current && mapInstanceRef.current) {
        mapInstanceRef.current.removeLayer(activeMarkerRef.current);
        activeMarkerRef.current = null;
      }
      setSelectedCoords(null);
      setLocationSource(null);
      return;
    }

    const updatePin = (coords: [number, number], label: string, src: string) => {
      if (!mapInstanceRef.current) return;
      if (activeMarkerRef.current) {
        activeMarkerRef.current.setLatLng(coords);
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
        activeMarkerRef.current = L.marker(coords, {
          icon: activeIcon,
          draggable: true,
        }).addTo(mapInstanceRef.current);

        activeMarkerRef.current.on('dragend', (dragEvent: any) => {
          const pos = dragEvent.target.getLatLng();
          setSelectedCoords([pos.lat, pos.lng]);
          setLocationSource('USER_CONFIRMED');
          setIsLocationConfirmed(false);
          if (onLocationSelect) {
            onLocationSelect(pos.lat, pos.lng, label, 'USER_CONFIRMED');
          }
        });
      }
    };

    const timer = setTimeout(async () => {
      if (!mapInstanceRef.current) return;

      // 1. If explicit coordinates are already provided from canonical state
      if (latitude != null && longitude != null) {
        const coords: [number, number] = [latitude, longitude];
        if (isCancelled || !mapInstanceRef.current) return;
        mapInstanceRef.current.setView(coords, Math.max(zoom, 15), { animate: true });
        setSelectedCoords(coords);
        setLocationSource('GEOCODED_EXACT');
        updatePin(coords, locationName || 'Pinned Location', 'GEOCODED_EXACT');
        return;
      }

      if (!locationName) return;

      // 2. Resolve via layered resolver (exact -> normalized -> locality -> gazetteer)
      const resolved = await resolveLocationCoordinates(locationName, landmark, street, area, locality);
      if (isCancelled || !resolved || !mapInstanceRef.current) return;

      const coords: [number, number] = [resolved.lat, resolved.lng];
      mapInstanceRef.current.setView(coords, resolved.zoom, { animate: true });
      setSelectedCoords(coords);
      setLocationSource(resolved.source);

      if (onLocationSelect) {
        onLocationSelect(resolved.lat, resolved.lng, resolved.displayName || locationName, resolved.source);
      }

      updatePin(coords, resolved.displayName || locationName, resolved.source);
    }, 250); // 250ms debounce to prevent public Nominatim request storms

    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [locationName, landmark, street, area, locality, latitude, longitude, zoom, onLocationSelect]);

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
            <span className="location-name-text">LOCATION: {locationName}</span>
            {landmark && <span className="location-landmark-text">({landmark})</span>}
            {locationSource && (
              <span className="location-source-badge">
                {locationSource.replace(/_/g, ' ')}
              </span>
            )}
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
