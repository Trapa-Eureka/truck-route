import MapView from './components/MapView'

export default function App() {
  return (
    <div className="app">
      <aside className="panel">
        <h1>Spotter</h1>
        <p>Weather-aware truck routing</p>
      </aside>
      <main className="map-area">
        <MapView />
      </main>
    </div>
  )
}
