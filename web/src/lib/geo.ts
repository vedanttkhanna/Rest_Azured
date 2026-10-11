import { config } from "../config";
export type Bounds = [number, number, number, number];
export function inServiceArea(lat: number, lng: number): boolean {
  const box = config.serviceArea;
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= box.minLat &&
    lat <= box.maxLat &&
    lng >= box.minLng &&
    lng <= box.maxLng
  );
}
export function imageCoordinates(
  bounds: Bounds,
): [[number, number], [number, number], [number, number], [number, number]] {
  const [west, south, east, north] = bounds;
  return [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
  ];
}
