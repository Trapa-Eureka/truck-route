import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'

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

export default function MapView() {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!MAP_KEY || !containerRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')

    return () => map.remove()
  }, [])

  if (!MAP_KEY) {
    return (
      <div className="map-missing-key" role="alert">
        To show the map, set <code>VITE_TOMTOM_MAP_KEY</code> in <code>frontend/.env.local</code>.
      </div>
    )
  }

  return <div ref={containerRef} className="map" />
}
