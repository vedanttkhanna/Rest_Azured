import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  ImageSource,
  Map as MapInstance,
} from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { FeatureCollection } from "geojson";
import { Layers, MapPin, RotateCcw } from "lucide-react";
import type { Report, Segmentation } from "../api/types";
import { imageCoordinates, type Bounds } from "../lib/geo";
import { sampleLocation, sampleSegmentation } from "../mocks/fixtures";

// MapLibre 6 ships a separate ESM worker. Give Vite its asset explicitly so
// dependency pre-bundling and production chunking preserve the worker URL.
maplibregl.setWorkerUrl(mapWorkerUrl);

export interface Point {
  lat: number;
  lng: number;
}
interface Props {
  report?: Report;
  heatmapUrl?: string | null;
  segmentation?: Segmentation;
  imageUrl?: string;
  imageBounds?: Bounds;
  sample?: boolean;
  selectable?: boolean;
  point?: Point;
  onSelect?: (point: Point) => void;
}
function reportViewBounds(report: Report): Bounds {
  if (!report.panels.features.length) return report.heatmap_bounds;
  const bounds: Bounds = [Infinity, Infinity, -Infinity, -Infinity];
  for (const feature of report.panels.features)
    for (const ring of feature.geometry.coordinates)
      for (const [lng, lat] of ring) {
        bounds[0] = Math.min(bounds[0], lng);
        bounds[1] = Math.min(bounds[1], lat);
        bounds[2] = Math.max(bounds[2], lng);
        bounds[3] = Math.max(bounds[3], lat);
      }
  return bounds;
}
export function MapView({
  report,
  heatmapUrl,
  segmentation,
  imageUrl,
  imageBounds,
  sample = false,
  selectable = false,
  point,
  onSelect,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapInstance | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [panels, setPanels] = useState(true);
  const [shade, setShade] = useState(true);
  const [outlines, setOutlines] = useState(Boolean(segmentation));
  const reportRef = useRef(report);
  reportRef.current = report;
  const identity = report?.job_id;
  useEffect(() => {
    if (!container.current) return;
    setError("");
    setReady(false);
    let map: MapInstance;
    try {
      map = new maplibregl.Map({
        container: container.current,
        center: [
          point?.lng ?? sampleLocation.lng,
          point?.lat ?? sampleLocation.lat,
        ],
        zoom: selectable ? 18 : 18.5,
        maxZoom: 21,
        attributionControl: false,
        canvasContextAttributes: { preserveDrawingBuffer: true },
        style: {
          version: 8,
          sources: {
            satellite: {
              type: "raster",
              tiles: [
                "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
              ],
              tileSize: 256,
              maxzoom: 19,
              attribution:
                "Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community",
            },
          },
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#293d35" },
            },
            {
              id: "satellite",
              type: "raster",
              source: "satellite",
              paint: { "raster-saturation": -0.2 },
            },
          ],
        },
      });
    } catch {
      setError(
        "Interactive maps need WebGL. You can enter coordinates in the form, and the report numbers remain available.",
      );
      return;
    }
    mapRef.current = map;
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-left",
    );
    if (selectable) {
      map.getCanvas().style.cursor = "crosshair";
      map.on("click", (event) =>
        selectRef.current?.({ lat: event.lngLat.lat, lng: event.lngLat.lng }),
      );
    }
    map.on("load", () => {
      if (sample || (imageUrl && imageBounds)) {
        map.addSource("fixture-image", {
          type: "image",
          url: sample ? "/demo/rooftop.png" : imageUrl!,
          coordinates: imageCoordinates(sample ? sampleLocation.image_bounds as Bounds : imageBounds!),
        });
        map.addLayer({
          id: "fixture-image",
          type: "raster",
          source: "fixture-image",
          paint: { "raster-fade-duration": 0 },
        });
      }
      if (sample || segmentation) {
        map.addSource("fixture-outlines", {
          type: "geojson",
          data: (sample ? sampleSegmentation : segmentation) as FeatureCollection,
        });
        map.addLayer({
          id: "fixture-roof",
          type: "line",
          source: "fixture-outlines",
          filter: ["==", ["get", "kind"], "roof"],
          layout: { visibility: "none" },
          paint: { "line-color": "#f5cf57", "line-width": 3 },
        });
        map.addLayer({
          id: "fixture-obstacles",
          type: "fill",
          source: "fixture-outlines",
          filter: ["==", ["get", "kind"], "obstacle"],
          layout: { visibility: "none" },
          paint: { "fill-color": "#ed8a62", "fill-opacity": 0.7 },
        });
      }
      const currentReport = reportRef.current;
      if (currentReport) {
        const bounds = currentReport.heatmap_bounds as Bounds;
        if (heatmapUrl) {
          map.addSource("shade", {
            type: "image",
            url: heatmapUrl,
            coordinates: imageCoordinates(bounds),
          });
          map.addLayer({
            id: "shade",
            type: "raster",
            source: "shade",
            paint: { "raster-opacity": 0.65, "raster-fade-duration": 0 },
          });
        }
        map.addSource("panels", {
          type: "geojson",
          data: currentReport.panels as FeatureCollection,
        });
        map.addLayer({
          id: "panels-fill",
          type: "fill",
          source: "panels",
          paint: { "fill-color": "#5288b5", "fill-opacity": 0.87 },
        });
        map.addLayer({
          id: "panels-line",
          type: "line",
          source: "panels",
          paint: { "line-color": "#d7efff", "line-width": 1.2 },
        });
        const viewBounds = reportViewBounds(currentReport);
        map.fitBounds(
          [
            [viewBounds[0], viewBounds[1]],
            [viewBounds[2], viewBounds[3]],
          ],
          { padding: 55, maxZoom: 21, duration: 0 },
        );
      }
      // Report sources are added after the initial map load. Wait for their
      // worker/image data to render before declaring the map ready.
      map.once("idle", () => setReady(true));
    });
    map.on("error", (event) => {
      if (event.error.message.includes("shade"))
        setError(
          "The shade image could not load. Use Refresh map to request a fresh link.",
        );
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      markerRef.current?.remove();
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
    // The map is retained while fresh report values and signed URLs are updated below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity, sample, selectable]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (point) {
      // Typing coordinates must move the viewport as well as the marker.
      // Keep nearby map clicks stable; fly only when the new roof is offscreen.
      if (!map.getBounds().contains([point.lng, point.lat]))
        map.easeTo({ center: [point.lng, point.lat], zoom: 18, duration: 300 });
      if (!markerRef.current) {
        markerRef.current = new maplibregl.Marker({
          color: "#f5cf57",
          draggable: selectable,
        })
          .setLngLat([point.lng, point.lat])
          .addTo(map);
        markerRef.current.on("dragend", () => {
          const loc = markerRef.current!.getLngLat();
          selectRef.current?.({ lat: loc.lat, lng: loc.lng });
        });
      } else markerRef.current.setLngLat([point.lng, point.lat]);
    }
  }, [point, ready, selectable]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (report)
      (map.getSource("panels") as GeoJSONSource | undefined)?.setData(
        report.panels as FeatureCollection,
      );
    if (report && heatmapUrl) {
      const source = map.getSource("shade") as ImageSource | undefined;
      if (source)
        source.updateImage({
          url: heatmapUrl,
          coordinates: imageCoordinates(report.heatmap_bounds as Bounds),
        });
      else {
        map.addSource("shade", {
          type: "image",
          url: heatmapUrl,
          coordinates: imageCoordinates(report.heatmap_bounds as Bounds),
        });
        map.addLayer(
          {
            id: "shade",
            type: "raster",
            source: "shade",
            layout: { visibility: shade ? "visible" : "none" },
            paint: { "raster-opacity": 0.65, "raster-fade-duration": 0 },
          },
          "panels-fill",
        );
      }
    }
  }, [report, heatmapUrl, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const [layer, visible] of [
      ["panels-fill", panels],
      ["panels-line", panels],
      ["shade", shade],
      ["fixture-roof", outlines],
      ["fixture-obstacles", outlines],
    ] as const) {
      if (map.getLayer(layer))
        map.setLayoutProperty(
          layer,
          "visibility",
          visible ? "visible" : "none",
        );
    }
  }, [ready, panels, shade, outlines]);
  const recenter = () => {
    if (point)
      mapRef.current?.flyTo({ center: [point.lng, point.lat], zoom: 18 });
    else if (report) {
      const b = reportViewBounds(report);
      mapRef.current?.fitBounds(
        [
          [b[0], b[1]],
          [b[2], b[3]],
        ],
        { padding: 55, maxZoom: 21 },
      );
    }
  };
  return (
    <div className={`map-view ${selectable ? "selectable" : ""}`}>
      <div
        ref={container}
        className="map-canvas"
        aria-busy={!ready && !error}
        aria-label={
          selectable
            ? "Satellite rooftop selector. Click to place a pin, or enter coordinates below."
            : "Satellite map with solar panel layout and shading"
        }
        role="region"
      />
      {error && (
        <div className="map-error" role="status">
          {error}
        </div>
      )}
      <div className="map-label">
        <MapPin size={13} />
        {selectable
          ? "Click directly on your rooftop"
          : sample
            ? "Mayur Vihar · sample building"
            : "Your rooftop assessment"}
      </div>
      <button
        onClick={recenter}
        className="map-recenter"
        aria-label="Recenter map"
      >
        <RotateCcw size={15} />
      </button>
      {report && (
        <div className="map-layers">
          <span>
            <Layers size={14} /> Layers
          </span>
          <label>
            <input
              type="checkbox"
              checked={panels}
              onChange={(event) => setPanels(event.target.checked)}
            />
            <i className="legend-panel" /> Panels
          </label>
          <label>
            <input
              type="checkbox"
              checked={shade}
              disabled={!heatmapUrl}
              onChange={(event) => setShade(event.target.checked)}
            />
            <i className="legend-shade" /> Shade
          </label>
          {(sample || segmentation) && (
            <label>
              <input
                type="checkbox"
                checked={outlines}
                onChange={(event) => setOutlines(event.target.checked)}
              />{" "}
              {sample ? "Sample outlines" : "Roof & obstacles"}
            </label>
          )}
        </div>
      )}
      {report && shade && heatmapUrl && (
        <div className="shade-legend">
          <span>Less shade</span>
          <i />
          <span>More shade</span>
        </div>
      )}
    </div>
  );
}
