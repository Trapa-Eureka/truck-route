import { Component, type ReactNode } from 'react'

/**
 * Keeps a map that cannot start from taking the whole page with it. Two things throw here: a
 * browser without WebGL (the map library refuses to start), and a map chunk that cannot be loaded
 * (a dropped connection, or a tab left open across a new release, asking for a file that is gone).
 * Without a boundary React would unmount everything, the form and the results included; with it,
 * only the map area says what is wrong and the routes, numbers and checkpoint list keep working.
 */
export default class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown) {
    console.error('The map could not be shown:', error)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <p className="map-problem" role="alert">
        The map could not be shown. Reload the page; if it stays empty, this browser may not support the map (WebGL). The
        routes, the numbers and the checkpoint list on the left still work.
      </p>
    )
  }
}
