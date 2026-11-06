import {
  LngLatBounds,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
  type GeoJSONSource,
  type MapMouseEvent,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import { heatFeatures } from '../lib/heatmap'
import { checkpointDots, placeDots, riskSegments, routeLines } from '../map/geo'
import { heatLayerId } from '../map/heat'
import { addHeatLayers, addRouteLayers, LAYER, removeHeatLayers, SOURCE } from '../map/layers'
import { mapErrorMessage } from '../map/errors'
import type { CheckpointFocus } from '../map/focus'
import { checkpointPopupContent } from '../map/popup'
import type { Coordinate, HeatmapResponse, ResolvedPlace, Route } from '../types/api'

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

interface Props {
  routes: readonly Route[]
  selectedId: string | null
  origin: ResolvedPlace | null
  destination: ResolvedPlace | null
  focus: CheckpointFocus | null
  /** The forecast grid, loaded once, and the slider hour that picks which level to show. */
  heatmap: HeatmapResponse | null
  hour: number
  /** Where the truck is at that hour on the selected route. */
  truck: Coordinate | null
  onSelectRoute: (id: string) => void
  /** A checkpoint dot was clicked (index) or its popup was closed (null). */
  onSelectCheckpoint: (index: number | null) => void
}

function setData(map: MapLibreMap, source: string, data: Parameters<GeoJSONSource['setData']>[0]) {
  ;(map.getSource(source) as GeoJSONSource).setData(data)
}

export default function MapView({
  routes,
  selectedId,
  origin,
  destination,
  focus,
  heatmap,
  hour,
  truck,
  onSelectRoute,
  onSelectCheckpoint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const popupRef = useRef<{ popup: Popup; onClose: () => void } | null>(null)
  const truckRef = useRef<Marker | null>(null)
  // How many heat layers exist, and which hour's is showing.
  const heatLayers = useRef({ count: 0, shown: null as number | null })
  const [ready, setReady] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  const selectedRoute = routes.find((route) => route.id === selectedId)

  // The click handlers are registered once; this keeps them calling the latest callbacks.
  const callbacks = useRef({ onSelectRoute, onSelectCheckpoint })
  useEffect(() => {
    callbacks.current = { onSelectRoute, onSelectCheckpoint }
  }, [onSelectRoute, onSelectCheckpoint])

  // Create the map once and add the (empty) sources and layers.
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

    // A refused key or a style that never loads leaves a blank map: say so, the results still work.
    let styleLoaded = false
    map.on('error', (event) => {
      const message = mapErrorMessage(event.error, styleLoaded)
      if (message) setProblem(message)
    })

    map.on('load', () => {
      styleLoaded = true
      addRouteLayers(map)

      map.on('click', LAYER.checkpoints, (event: MapMouseEvent) => {
        const index = map.queryRenderedFeatures(event.point, { layers: [LAYER.checkpoints] })[0]?.properties?.index
        if (typeof index === 'number') callbacks.current.onSelectCheckpoint(index)
      })
      map.on('click', LAYER.routeHit, (event: MapMouseEvent) => {
        // A click on a checkpoint dot is not a click on the route underneath it.
        if (map.queryRenderedFeatures(event.point, { layers: [LAYER.checkpoints] }).length > 0) return
        // Features come back topmost first, and the selected route is drawn on top.
        const id = map.queryRenderedFeatures(event.point, { layers: [LAYER.routeHit] })[0]?.properties?.id
        if (typeof id === 'string') callbacks.current.onSelectRoute(id)
      })
      for (const layer of [LAYER.checkpoints, LAYER.routeHit]) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }

      setReady(true)
    })

    return () => {
      mapRef.current = null
      popupRef.current = null
      truckRef.current = null
      setReady(false)
      map.remove()
    }
  }, [])

  // Redraw when the routes, the selection or the end points change.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    setData(map, SOURCE.routes, routeLines(routes, selectedId))
    setData(map, SOURCE.risk, riskSegments(selectedRoute))
    setData(map, SOURCE.checkpoints, checkpointDots(selectedRoute))
  }, [ready, routes, selectedId, selectedRoute])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    setData(map, SOURCE.places, placeDots(origin, destination))
  }, [ready, origin, destination])

  // Load the whole 48-hour grid into the map once, with one layer per hour.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    removeHeatLayers(map, heatLayers.current.count)
    heatLayers.current = { count: 0, shown: null }
    if (heatmap === null) {
      setData(map, SOURCE.heat, { type: 'FeatureCollection', features: [] })
      return
    }
    setData(map, SOURCE.heat, heatFeatures(heatmap) as Parameters<typeof setData>[2])
    const meanLat = heatmap.points.reduce((sum, [, lat]) => sum + lat, 0) / Math.max(1, heatmap.points.length)
    addHeatLayers(map, heatmap.hours, heatmap.spacing_deg, meanLat)
    heatLayers.current = { count: heatmap.hours, shown: null }
  }, [ready, heatmap])

  // Moving the slider shows one hour's layer and hides the last one: no data is sent or fetched,
  // and the map does not rebuild any tiles.
  useEffect(() => {
    const map = mapRef.current
    const state = heatLayers.current
    if (!ready || !map || state.count === 0 || hour >= state.count) return
    if (state.shown !== null) map.setPaintProperty(heatLayerId(state.shown), 'circle-opacity', 0)
    map.setPaintProperty(heatLayerId(hour), 'circle-opacity', 1)
    state.shown = hour
  }, [ready, heatmap, hour])

  // The truck is an HTML marker, not a map layer. It moves on every slider step, and updating a
  // GeoJSON source sends the data to the map's worker and rebuilds its tiles each time (measured:
  // the largest part of a step on a slow CPU). Moving a marker only changes a CSS transform.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    if (!truck) {
      truckRef.current?.remove()
      truckRef.current = null
      return
    }
    if (!truckRef.current) {
      const element = document.createElement('div')
      element.className = 'truck-marker'
      element.setAttribute('role', 'img')
      element.setAttribute('aria-label', 'Truck position at the chosen hour')
      truckRef.current = new Marker({ element }).setLngLat(truck).addTo(map)
    } else {
      truckRef.current.setLngLat(truck)
    }
  }, [ready, truck])

  // Zoom to the routes when a new analysis arrives (not when the selection changes).
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || routes.length === 0) return
    const bounds = new LngLatBounds()
    for (const route of routes) for (const point of route.geometry) bounds.extend(point)
    map.fitBounds(bounds, { padding: 64, maxZoom: 12, duration: 700 })
  }, [ready, routes])

  // Show the popup and the ring for the focused checkpoint.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return

    if (popupRef.current) {
      // Removing a popup fires 'close'; detach first so replacing it is not read as "the user closed it".
      popupRef.current.popup.off('close', popupRef.current.onClose)
      popupRef.current.popup.remove()
      popupRef.current = null
    }

    const checkpoint = focus && selectedRoute?.checkpoints.find((c) => c.index === focus.index)
    map.setFilter(LAYER.checkpointActive, ['==', ['get', 'index'], checkpoint ? checkpoint.index : -1])
    if (!focus || !selectedRoute || !checkpoint) return

    const isLast = checkpoint === selectedRoute.checkpoints[selectedRoute.checkpoints.length - 1]
    const onClose = () => callbacks.current.onSelectCheckpoint(null)
    const popup = new Popup({ closeOnClick: false, maxWidth: '300px', offset: 14 })
      .setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(checkpointPopupContent(checkpoint, isLast))
      .addTo(map)
    popup.on('close', onClose)
    popupRef.current = { popup, onClose }

    if (focus.fly) {
      map.easeTo({ center: [checkpoint.lon, checkpoint.lat], zoom: Math.max(map.getZoom(), 8), duration: 600 })
    }
  }, [ready, focus, selectedRoute])

  if (!MAP_KEY) {
    return (
      <div className="map-missing-key" role="alert">
        To show the map, set <code>VITE_TOMTOM_MAP_KEY</code> in <code>frontend/.env.local</code>.
      </div>
    )
  }

  return (
    <>
      <div ref={containerRef} className="map" />
      {problem && (
        <p className="map-problem" role="alert">
          {problem}
        </p>
      )}
    </>
  )
}
