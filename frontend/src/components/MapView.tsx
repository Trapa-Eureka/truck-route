import {
  LngLatBounds,
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSource,
  type LineLayerSpecification,
  type MapMouseEvent,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import type { ResolvedPlace, Route } from '../types/api'

// MapLibre finds its worker with new URL('./maplibre-gl-worker.mjs', import.meta.url). In a
// production bundle that points at /assets/maplibre-gl-worker.mjs, which the build never emits
// (404, "Worker failed to load"). Importing it with ?url makes Vite emit it and gives the real URL.
setWorkerUrl(workerUrl)

// Map-only TomTom key (domain-whitelisted). The routing/geocoding key stays on the server.
const MAP_KEY = import.meta.env.VITE_TOMTOM_MAP_KEY as string | undefined

const STYLE_URL = `https://api.tomtom.com/style/1/style/*?map=basic_main&key=${MAP_KEY ?? ''}`

// Continental United States.
const INITIAL_CENTER: [number, number] = [-98, 39]
const INITIAL_ZOOM = 3.5

const ROUTES_SOURCE = 'routes'
const PLACES_SOURCE = 'places'
const SELECTED_COLOR = '#1a5fd0'
const OTHER_COLOR = '#8a949e'

interface Props {
  routes: readonly Route[]
  selectedId: string | null
  origin: ResolvedPlace | null
  destination: ResolvedPlace | null
  onSelectRoute: (id: string) => void
}

function routeFeatures(routes: readonly Route[], selectedId: string | null) {
  return {
    type: 'FeatureCollection' as const,
    features: routes.map((route) => ({
      type: 'Feature' as const,
      properties: { id: route.id, selected: route.id === selectedId },
      geometry: { type: 'LineString' as const, coordinates: route.geometry },
    })),
  }
}

function placeFeatures(origin: ResolvedPlace | null, destination: ResolvedPlace | null) {
  const places = [
    origin && { kind: 'origin', place: origin },
    destination && { kind: 'destination', place: destination },
  ].filter((entry) => entry !== null)
  return {
    type: 'FeatureCollection' as const,
    features: places.map(({ kind, place }) => ({
      type: 'Feature' as const,
      properties: { kind },
      geometry: { type: 'Point' as const, coordinates: [place.lon, place.lat] },
    })),
  }
}

export default function MapView({ routes, selectedId, origin, destination, onSelectRoute }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const [ready, setReady] = useState(false)

  // The click handler is registered once; this keeps it calling the latest callback.
  const onSelectRef = useRef(onSelectRoute)
  useEffect(() => {
    onSelectRef.current = onSelectRoute
  }, [onSelectRoute])

  // Create the map once and add the (empty) route and place layers.
  useEffect(() => {
    if (!MAP_KEY || !containerRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    mapRef.current = map

    map.on('load', () => {
      map.addSource(ROUTES_SOURCE, { type: 'geojson', data: routeFeatures([], null) })
      map.addSource(PLACES_SOURCE, { type: 'geojson', data: placeFeatures(null, null) })

      // The selected route is drawn last, so it sits on top of the gray ones.
      const lineLayout: LineLayerSpecification['layout'] = {
        'line-join': 'round',
        'line-cap': 'round',
        'line-sort-key': ['case', ['get', 'selected'], 1, 0],
      }

      // Wide invisible line: makes thin gray routes easy to click.
      map.addLayer(
        {
          id: 'routes-hit',
          type: 'line',
          source: ROUTES_SOURCE,
          layout: lineLayout,
          paint: { 'line-width': 18, 'line-opacity': 0 },
        },
      )
      map.addLayer(
        {
          id: 'routes-casing',
          type: 'line',
          source: ROUTES_SOURCE,
          layout: lineLayout,
          paint: { 'line-color': '#ffffff', 'line-width': ['case', ['get', 'selected'], 11, 7], 'line-opacity': 0.95 },
        },
      )
      map.addLayer(
        {
          id: 'routes-line',
          type: 'line',
          source: ROUTES_SOURCE,
          layout: lineLayout,
          paint: {
            'line-color': ['case', ['get', 'selected'], SELECTED_COLOR, OTHER_COLOR],
            'line-width': ['case', ['get', 'selected'], 7, 4],
          },
        },
      )
      map.addLayer({
        id: 'places',
        type: 'circle',
        source: PLACES_SOURCE,
        paint: {
          'circle-radius': 8,
          'circle-color': ['match', ['get', 'kind'], 'origin', '#1f8f4d', '#c23b2b'],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 3,
        },
      })

      map.on('click', 'routes-hit', (event: MapMouseEvent) => {
        // Features come back topmost first, and the selected route is drawn on top.
        const hits = map.queryRenderedFeatures(event.point, { layers: ['routes-hit'] })
        const id = hits[0]?.properties?.id
        if (typeof id === 'string') onSelectRef.current(id)
      })
      map.on('mouseenter', 'routes-hit', () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', 'routes-hit', () => (map.getCanvas().style.cursor = ''))

      setReady(true)
    })

    return () => {
      mapRef.current = null
      setReady(false)
      map.remove()
    }
  }, [])

  // Redraw when the routes, the selection or the end points change.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    ;(map.getSource(ROUTES_SOURCE) as GeoJSONSource).setData(routeFeatures(routes, selectedId))
  }, [ready, routes, selectedId])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    ;(map.getSource(PLACES_SOURCE) as GeoJSONSource).setData(placeFeatures(origin, destination))
  }, [ready, origin, destination])

  // Zoom to the routes when a new analysis arrives (not when the selection changes).
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || routes.length === 0) return
    const bounds = new LngLatBounds()
    for (const route of routes) for (const point of route.geometry) bounds.extend(point)
    map.fitBounds(bounds, { padding: 64, maxZoom: 12, duration: 700 })
  }, [ready, routes])

  if (!MAP_KEY) {
    return (
      <div className="map-missing-key" role="alert">
        To show the map, set <code>VITE_TOMTOM_MAP_KEY</code> in <code>frontend/.env.local</code>.
      </div>
    )
  }

  return <div ref={containerRef} className="map" />
}
