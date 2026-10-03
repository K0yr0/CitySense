/**
 * MapCanvas on Android: Leaflet in a WebView with OpenStreetMap raster tiles (no API key).
 *
 * Why not react-native-maps here: in Expo Go, Google rejects the built-in Maps API key
 * ("Authorization failure" in logcat) and the Google map then draws nothing at all, not even
 * our own lines and pins. Leaflet needs no key and works in Expo Go.
 * Same declarative API as map-canvas.tsx; data is pushed into the page with injectJavaScript,
 * events come back through postMessage.
 */
import { useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

import type { LatLng, Region } from '@/lib/geo';

import type { EdgeInsets, MapCanvasProps } from './types';
import { NO_PADDING } from './types';

const DEFAULT_FIT_PADDING: EdgeInsets = { top: 60, bottom: 60, left: 40, right: 40 };

type Command =
  | { type: 'data'; polylines: unknown; circles: unknown; markers: unknown }
  | { type: 'options'; dark: boolean; interactive: boolean; padding: EdgeInsets }
  | { type: 'animate'; region: Region }
  | { type: 'fit'; coords: LatLng[]; padding: EdgeInsets };

type Event =
  | { type: 'ready' }
  | { type: 'press'; lat: number; lng: number }
  | { type: 'marker'; id: string }
  | { type: 'callout'; id: string }
  | { type: 'drag'; id: string; lat: number; lng: number }
  | { type: 'region'; region: Region };

function pageHtml(init: { region: Region; dark: boolean; interactive: boolean; padding: EdgeInsets }): string {
  return `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
html,body,#map{margin:0;padding:0;height:100%;width:100%;background:${init.dark ? '#1b1b1d' : '#f2efe9'}}
.leaflet-control-attribution{font-size:9px}
.dark .leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.9) contrast(.9)}
.leaflet-popup-content{margin:8px 12px;font:14px/1.3 sans-serif}
</style></head><body><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function () {
  var post = function (m) { window.ReactNativeWebView.postMessage(JSON.stringify(m)); };
  var init = ${JSON.stringify(init)};
  var map = L.map('map', { zoomControl: false, preferCanvas: true, zoomSnap: 0.25, attributionControl: true });
  map.attributionControl.setPrefix(false);
  var tiles = null;
  function setTiles(dark) {
    // OpenStreetMap's standard tiles (light demo use is fine under the tile usage policy, with
    // attribution). Dark mode inverts the tile colours with a CSS filter.
    if (!tiles) tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    document.body.classList.toggle('dark', !!dark);
  }
  function bounds(r) {
    return [[r.latitude - r.latitudeDelta / 2, r.longitude - r.longitudeDelta / 2],
            [r.latitude + r.latitudeDelta / 2, r.longitude + r.longitudeDelta / 2]];
  }
  function setInteractive(on) {
    ['dragging', 'touchZoom', 'doubleClickZoom', 'scrollWheelZoom', 'boxZoom', 'keyboard'].forEach(function (h) {
      if (map[h]) { if (on) map[h].enable(); else map[h].disable(); }
    });
    if (map.tap) { if (on) map.tap.enable(); else map.tap.disable(); }
  }
  function setPadding(p) {
    document.querySelectorAll('.leaflet-bottom').forEach(function (el) { el.style.bottom = p.bottom + 'px'; });
    document.querySelectorAll('.leaflet-top').forEach(function (el) { el.style.top = p.top + 'px'; });
  }
  var interactive = init.interactive;
  // The WebView may have no size yet when this runs (e.g. inside a ScrollView), which would fit the
  // region at zoom 0 (the whole world). Re-fit the initial region whenever the size changes,
  // until the user has touched the map.
  var touched = false;
  document.getElementById('map').addEventListener('touchstart', function () { touched = true; }, { passive: true });
  // The last placement (initial region, or a later "fit" command), re-applied until the user touches the map.
  var place = function () { map.fitBounds(bounds(init.region), { animate: false }); };
  function fitInitial() {
    if (touched) return;
    map.invalidateSize(false);
    if (map.getSize().x > 0 && map.getSize().y > 0) place();
  }
  map.setView([init.region.latitude, init.region.longitude], 14, { animate: false });
  fitInitial();
  window.addEventListener('resize', fitInitial);
  setTimeout(fitInitial, 100);
  setTimeout(fitInitial, 500);
  setTiles(init.dark); setInteractive(interactive); setPadding(init.padding);

  var lines = L.layerGroup().addTo(map), circles = L.layerGroup().addTo(map), markers = L.layerGroup().addTo(map);
  function pinIcon(color) {
    return L.divIcon({ className: '', iconSize: [28, 40], iconAnchor: [14, 40], popupAnchor: [0, -36],
      html: '<svg width="28" height="40" viewBox="0 0 28 40"><path d="M14 1C6.8 1 1 6.8 1 13.9 1 23.8 14 39 14 39s13-15.2 13-25.1C27 6.8 21.2 1 14 1z" fill="' + color +
        '" stroke="white" stroke-width="2"/><circle cx="14" cy="14" r="4.5" fill="white"/></svg>' });
  }
  function dotIcon(color) {
    return L.divIcon({ className: '', iconSize: [22, 22], iconAnchor: [11, 11],
      html: '<div style="width:14px;height:14px;border-radius:50%;background:' + color + ';border:4px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>' });
  }
  function ll(c) { return [c.latitude, c.longitude]; }
  function setData(d) {
    lines.clearLayers();
    (d.polylines || []).slice().sort(function (a, b) { return (a.zIndex || 1) - (b.zIndex || 1); }).forEach(function (p) {
      L.polyline(p.coords.map(ll), { color: p.color, weight: p.width, opacity: 1, lineCap: 'round', interactive: false,
        dashArray: p.dash ? p.dash.join(',') : null }).addTo(lines);
    });
    circles.clearLayers();
    (d.circles || []).forEach(function (c) {
      L.circle(ll(c.center), { radius: c.radius, color: c.strokeColor, weight: c.strokeWidth || 1, opacity: 1,
        fillColor: c.fillColor, fillOpacity: 1, interactive: false }).addTo(circles);
    });
    markers.clearLayers();
    (d.markers || []).forEach(function (m) {
      var dot = m.kind === 'dot';
      var mk = L.marker(ll(m.coord), { icon: dot ? dotIcon(m.color) : pinIcon(m.color), draggable: !!m.draggable && interactive,
        interactive: !dot && interactive, keyboard: false, zIndexOffset: (m.zIndex || (dot ? 200 : 10)) * 10 });
      if (m.title) {
        var el = document.createElement('div');
        var t = document.createElement('b'); t.textContent = m.title; el.appendChild(t);
        if (m.description) { var d = document.createElement('div'); d.textContent = m.description; el.appendChild(d); }
        el.onclick = function () { post({ type: 'callout', id: m.id }); };
        mk.bindPopup(el, { closeButton: false });
      }
      mk.on('click', function () { post({ type: 'marker', id: m.id }); });
      mk.on('dragend', function () { var p = mk.getLatLng(); post({ type: 'drag', id: m.id, lat: p.lat, lng: p.lng }); });
      mk.addTo(markers);
    });
  }
  map.on('click', function (e) { if (interactive) post({ type: 'press', lat: e.latlng.lat, lng: e.latlng.lng }); });
  map.on('moveend', function () {
    var b = map.getBounds(), c = map.getCenter();
    post({ type: 'region', region: { latitude: c.lat, longitude: c.lng,
      latitudeDelta: b.getNorth() - b.getSouth(), longitudeDelta: b.getEast() - b.getWest() } });
  });
  window.__mapCommand = function (cmd) {
    if (cmd.type === 'data') setData(cmd);
    else if (cmd.type === 'options') { setTiles(cmd.dark); interactive = cmd.interactive; setInteractive(cmd.interactive); setPadding(cmd.padding); }
    else if (cmd.type === 'animate') { touched = true; map.flyToBounds(bounds(cmd.region), { duration: 0.6 }); }
    else if (cmd.type === 'fit' && cmd.coords.length) {
      place = function () {
        map.fitBounds(L.latLngBounds(cmd.coords.map(ll)), { animate: false,
          paddingTopLeft: [cmd.padding.left, cmd.padding.top], paddingBottomRight: [cmd.padding.right, cmd.padding.bottom] });
      };
      touched = false;
      fitInitial();
    }
  };
  post({ type: 'ready' });
})();
</script></body></html>`;
}

export function MapCanvas({
  ref,
  style,
  initialRegion,
  interactive = true,
  dark = false,
  padding = NO_PADDING,
  polylines,
  circles,
  markers,
  onPress,
  onMarkerPress,
  onCalloutPress,
  onMarkerDragEnd,
  onRegionChangeComplete,
  onReady,
}: MapCanvasProps) {
  const webRef = useRef<WebView>(null);
  const [ready, setReady] = useState(false);
  // The page is built once; later changes travel as commands.
  const [html] = useState(() => pageHtml({ region: initialRegion, dark, interactive, padding }));

  const send = useCallback((cmd: Command) => {
    webRef.current?.injectJavaScript(`window.__mapCommand && window.__mapCommand(${JSON.stringify(cmd)}); true;`);
  }, []);

  useImperativeHandle(ref, () => ({
    animateTo: (region) => send({ type: 'animate', region }),
    fitTo: (coords, pad) => send({ type: 'fit', coords, padding: pad ?? DEFAULT_FIT_PADDING }),
  }));

  useEffect(() => {
    if (ready) send({ type: 'data', polylines: polylines ?? [], circles: circles ?? [], markers: markers ?? [] });
  }, [ready, send, polylines, circles, markers]);

  const { top, bottom, left, right } = padding;
  useEffect(() => {
    if (ready) send({ type: 'options', dark, interactive, padding: { top, bottom, left, right } });
  }, [ready, send, dark, interactive, top, bottom, left, right]);

  const onMessage = (e: WebViewMessageEvent) => {
    let ev: Event;
    try {
      ev = JSON.parse(e.nativeEvent.data) as Event;
    } catch {
      return;
    }
    switch (ev.type) {
      case 'ready':
        setReady(true);
        onReady?.();
        break;
      case 'press':
        onPress?.({ latitude: ev.lat, longitude: ev.lng });
        break;
      case 'marker':
        onMarkerPress?.(ev.id);
        break;
      case 'callout':
        onCalloutPress?.(ev.id);
        break;
      case 'drag':
        onMarkerDragEnd?.(ev.id, { latitude: ev.lat, longitude: ev.lng });
        break;
      case 'region':
        onRegionChangeComplete?.(ev.region);
        break;
    }
  };

  return (
    <View style={[styles.container, style]} pointerEvents={interactive ? 'auto' : 'none'}>
      <WebView
        ref={webRef}
        source={{ html, baseUrl: 'https://localhost/' }}
        originWhitelist={['*']}
        onMessage={onMessage}
        style={[styles.web, { backgroundColor: dark ? '#1b1b1d' : '#f2efe9' }]}
        javaScriptEnabled
        domStorageEnabled
        setSupportMultipleWindows={false}
        overScrollMode="never"
        nestedScrollEnabled
        scrollEnabled={false}
        androidLayerType="hardware"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { overflow: 'hidden' },
  web: { flex: 1 },
});
