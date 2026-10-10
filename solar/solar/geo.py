from __future__ import annotations
from dataclasses import dataclass
import math
import json
import numpy as np
from pyproj import Transformer, Proj
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from shapely.geometry import shape, mapping, Polygon
from shapely.ops import transform, unary_union

TO_METRIC = Transformer.from_crs(4326, 32643, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(32643, 4326, always_xy=True).transform


def metric(geometry):
    p = shape(geometry)
    if p.geom_type not in ("Polygon", "MultiPolygon") or p.is_empty or not p.is_valid:
        raise ValueError("Expected valid nonempty polygon geometry")
    if not all(math.isfinite(x) for x in p.bounds): raise ValueError("Nonfinite geometry")
    west,south,east,north = p.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("Geometry must use WGS84 longitude/latitude")
    return transform(TO_METRIC, p)


def geojson(poly):
    return json.loads(json.dumps(mapping(transform(TO_WGS84, poly))))


@dataclass
class Grid:
    transform: object
    height: int
    width: int
    resolution: float
    crs: str = "EPSG:32643"
    convergence: float = 0.0

    @property
    def shape(self): return self.height, self.width

    @property
    def bounds(self):
        t = self.transform
        return (t.c, t.f - self.height * self.resolution,
                t.c + self.width * self.resolution, t.f)

    def mask(self, polygons):
        polygons = [p for p in polygons if not p.is_empty]
        if not polygons: return np.zeros(self.shape, dtype=bool)
        return rasterize([(p, 1) for p in polygons], out_shape=self.shape,
                         transform=self.transform, dtype="uint8").astype(bool)

    def polygonize(self, mask):
        return unary_union([shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask,
                            transform=self.transform) if v == 1])


def make_grid(job, config, roofs=()):
    x, y = TO_METRIC(job["lng"], job["lat"])
    g = config["geo"]
    half = g["window_m"] / 2
    bounds = [x-half, y-half, x+half, y+half]
    for roof in roofs:
        b = roof.bounds
        # Include the complete target roof and a finite ray-marching margin.
        margin = config["shading"]["max_distance_m"]
        bounds = [min(bounds[0], b[0]-margin), min(bounds[1], b[1]-margin),
                  max(bounds[2], b[2]+margin), max(bounds[3], b[3]+margin)]
    res = g["grid_resolution_m"]
    left, bottom = math.floor(bounds[0]/res)*res, math.floor(bounds[1]/res)*res
    width, height = math.ceil((bounds[2]-left)/res), math.ceil((bounds[3]-bottom)/res)
    if width*height > g["max_grid_cells"]: raise ValueError("Assessment exceeds grid cell limit")
    return Grid(from_origin(left, bottom+height*res, res, res), height, width, res,
                convergence=Proj("EPSG:32643").get_factors(job["lng"],job["lat"]).meridian_convergence)


def check_location(lat, lng, config):
    if isinstance(lat, bool) or isinstance(lng, bool): raise ValueError("Invalid location")
    lat, lng = float(lat), float(lng)
    west, south, east, north = config["geo"]["delhi_bounds"]
    if not (math.isfinite(lat) and math.isfinite(lng) and south <= lat <= north and west <= lng <= east):
        raise ValueError("Location must be within the configured Delhi/NCR bounds")
    return lat, lng
