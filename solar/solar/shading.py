from __future__ import annotations
import numpy as np
import pandas as pd
import pvlib
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling, transform_bounds


def ray_shadow(height, rows, cols, elevation_deg, azimuth_deg, resolution, max_distance, origin_offset=0):
    """Vectorized rays toward the sun. North is decreasing raster row.

    Samples use their actual quantized horizontal distance; no wrapping at edges.
    Only receiver cells are traced, not every cell in the context raster.
    """
    shaded = np.zeros(len(rows), dtype=bool)
    if elevation_deg <= 0: return shaded
    origin = height[rows, cols] + origin_offset
    az, elev = np.radians([azimuth_deg, elevation_deg])
    previous = None
    for step in range(1, int(np.ceil(max_distance/resolution))+1):
        dr, dc = int(round(-np.cos(az)*step)), int(round(np.sin(az)*step))
        if (dr, dc) == previous or (dr==0 and dc==0): continue
        previous = (dr, dc)
        distance = np.hypot(dr, dc)*resolution
        if distance > max_distance: continue
        rr, cc = rows+dr, cols+dc
        valid = (rr>=0)&(rr<height.shape[0])&(cc>=0)&(cc<height.shape[1])&~shaded
        idx = np.flatnonzero(valid)
        shaded[idx] |= height[rr[idx], cc[idx]] > origin[idx] + distance*np.tan(elev) + 1e-6
        if shaded.all(): break
    return shaded


def representative_shadows(height, grid, receivers, lat, lng, config, minute=30):
    rows, cols = np.nonzero(receivers)
    year = config["energy"]["year"]
    day = config["shading"]["representative_day"]
    times = pd.DatetimeIndex([pd.Timestamp(year=year, month=m, day=day, hour=h, minute=minute,
                              tz=config["geo"]["timezone"]) for m in range(1,13) for h in range(24)])
    sun = pvlib.solarposition.get_solarposition(times, lat, lng)
    masks = np.zeros((288, len(rows)), dtype=bool)
    cfg = config["shading"]
    for i, (elev, az) in enumerate(zip(sun.apparent_elevation, sun.azimuth)):
        if elev <= cfg["min_elevation_deg"]: continue
        masks[i] = ray_shadow(height, rows, cols, elev, az-grid.convergence, grid.resolution,
                                  cfg["max_distance_m"], config["heights"]["panel_mount_height_m"])
    return rows, cols, masks


def weighted_shade(grid, rows, cols, masks, beam_weights):
    values = np.zeros(len(rows), dtype=float)
    if np.sum(beam_weights)>0:
        values = np.einsum("i,ij->j", beam_weights, masks, optimize=True)/np.sum(beam_weights)
    out = np.zeros(grid.shape, dtype="float32")
    out[rows, cols] = values
    return out


def heatmap_png(path, grid, fractions, roof_mask):
    """Reproject to an axis-aligned EPSG:3857 image for MapLibre image overlays."""
    bounds = transform_bounds(grid.crs, "EPSG:3857", *grid.bounds, densify_pts=21)
    dst_transform = from_bounds(*bounds, grid.width, grid.height)
    value = np.zeros(grid.shape, dtype="float32")
    alpha = np.zeros(grid.shape, dtype="uint8")
    reproject(fractions, value, src_transform=grid.transform, src_crs=grid.crs,
              dst_transform=dst_transform, dst_crs="EPSG:3857", resampling=Resampling.bilinear)
    reproject(roof_mask.astype("uint8"), alpha, src_transform=grid.transform, src_crs=grid.crs,
              dst_transform=dst_transform, dst_crs="EPSG:3857", resampling=Resampling.nearest)
    rgba = np.zeros((*grid.shape, 4), dtype="uint8")
    rgba[:,:,0] = np.clip(value*255, 0, 255)
    rgba[:,:,1] = np.clip((1-value)*210, 0, 255)
    rgba[:,:,2] = 40
    rgba[:,:,3] = alpha*190
    Image.fromarray(rgba).save(path)
    return list(transform_bounds("EPSG:3857", "EPSG:4326", *bounds))
