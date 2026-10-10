from __future__ import annotations
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from .geo import metric


def read_raster(path, grid):
    out = np.full(grid.shape, np.nan, dtype="float32")
    with rasterio.open(path) as src:
        if not src.crs: raise ValueError("Height raster must have a CRS")
        reproject(rasterio.band(src, 1), out, src_transform=src.transform,
                  src_crs=src.crs, src_nodata=src.nodata, dst_transform=grid.transform,
                  dst_crs=grid.crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return out


def build_heights(grid, roofs, obstacles, neighbors, config, dsm_path=None, building_heights_path=None, dsm_source="supplied_dsm"):
    """DSM is absolute elevation; synthetic heights are relative to flat terrain.

    Never add estimated obstacles to a DSM: it already contains surface objects.
    Open Buildings is a building-height raster, not a DSM, and only supplies
    footprint heights. Raster nodata is not interpreted as ground level.
    """
    warnings = []
    roof_mask = grid.mask([r["polygon"] for r in roofs])
    if dsm_path:
        h = read_raster(dsm_path, grid)
        if not np.isfinite(h[roof_mask]).all(): raise ValueError("DSM does not cover the entire target roof")
        valid = np.isfinite(h)
        if not valid.all():
            warnings.append("DSM has missing context cells; shadows outside observed coverage are unknown")
        # Missing context must not cast fictitious shadows.
        h[~valid] = -1e6
        return h, dsm_source, warnings
    h = np.zeros(grid.shape, dtype="float32")
    cfg = config["heights"]
    fallback = cfg["floor_height_m"] * cfg["default_floors"]
    heights = read_raster(building_heights_path, grid) if building_heights_path else None
    used_default = False
    entries = []
    for f in neighbors.get("features", []):
        p = metric(f["geometry"])
        prop = f.get("properties", {})
        entries.append((p, prop))
    # Target is written last to avoid neighboring footprint overlaps replacing it.
    for r in roofs:
        matches = [(p.intersection(r["polygon"]).area, props) for p, props in entries]
        props = max(matches, key=lambda x: x[0])[1] if matches and max(v[0] for v in matches)>0 else {}
        entries.append((r["polygon"], props))
    for poly, prop in entries:
        mask = grid.mask([poly])
        value = prop.get("height_m", prop.get("height"))
        if value is None and heights is not None:
            values = heights[mask]
            values = values[np.isfinite(values) & (values>0)]
            if values.size: value = float(np.median(values))
        if value is None and prop.get("num_floors") is not None:
            value = float(prop["num_floors"]) * cfg["floor_height_m"]
        if value is None:
            value = fallback
            used_default = True
        if not np.isfinite(float(value)) or float(value) <= 0: raise ValueError("Building height must be positive")
        h[mask] = float(value)
    roof_levels = {r["id"]: float(np.median(h[grid.mask([r["polygon"]])])) for r in roofs}
    for obs in obstacles:
        mask = grid.mask([obs["polygon"]])
        height = obs["properties"].get("height_m")
        if height is None: height = cfg["obstacle_m"][obs["properties"]["class"]]
        h[mask] = np.maximum(h[mask], roof_levels[obs["properties"]["roof_id"]] + height)
    if used_default: warnings.append("Unknown building heights use the configured floor-height default")
    if not neighbors.get("features"):
        warnings.append("No neighboring building geometry supplied; surrounding-building shading is not assessed")
    warnings.append("Synthetic surface assumes level terrain and estimated rooftop obstacle heights")
    source = "open_buildings_2.5d_with_defaults" if heights is not None else "footprint_heights_with_defaults"
    return h, source, warnings
