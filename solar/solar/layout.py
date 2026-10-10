from __future__ import annotations
import math
import numpy as np
import pandas as pd
import pvlib
from shapely.affinity import rotate
from shapely.geometry import box
from shapely.ops import unary_union
from shapely.prepared import prep


def row_pitch(lat, lng, tilt, azimuth, config, pitched=False):
    c = config["layout"]
    length = c["panel_length_m"]
    depth = length*math.cos(math.radians(tilt))
    if pitched: return depth+c["panel_gap_m"]
    day = pd.Timestamp(year=config["energy"]["year"], month=c["winter_month"], day=c["winter_day"], tz="UTC")
    hours = np.arange(c["solar_hours"][0],c["solar_hours"][1]+1e-8,c["spacing_step_minutes"]/60)
    noon = day+pd.Timedelta(hours=12-lng/15)
    eot = float(pvlib.solarposition.get_solarposition(pd.DatetimeIndex([noon]),lat,lng).equation_of_time.iloc[0])
    times = pd.DatetimeIndex([day+pd.Timedelta(hours=float(h)-lng/15-eot/60) for h in hours])
    sun = pvlib.solarposition.get_solarposition(times,lat,lng)
    if (sun.apparent_elevation<=0).any(): raise ValueError("Winter spacing hours must be in daylight")
    projection = np.maximum(0,np.cos(np.radians(sun.azimuth.to_numpy()-azimuth)))
    gap = length*math.sin(math.radians(tilt))*np.max(projection/np.tan(np.radians(sun.apparent_elevation)))
    return float(depth+gap+c["panel_gap_m"])


def orientations(roof, properties, config, convergence=0):
    c = config["layout"]
    if properties["roof_type"]=="pitched":
        tilt, azi = properties.get("tilt_deg"), properties.get("azimuth_deg")
        if tilt is None or azi is None or not 0<=tilt<90:
            raise ValueError("Pitched roof requires a tilt below 90 degrees and an azimuth")
        return [(float(tilt),float(azi))]
    coords = list(roof.minimum_rotated_rectangle.exterior.coords)
    edges = [(math.hypot(b[0]-a[0],b[1]-a[1]), math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])))
             for a,b in zip(coords,coords[1:])]
    angle = max(edges)[1]
    azi = (180-angle+convergence)%360
    if azi<90 or azi>270: azi=(azi+180)%360
    candidates = [(c["tilt_deg"],c["azimuth_deg"])]
    if abs(azi-c["azimuth_deg"])>1: candidates.append((c["tilt_deg"],azi))
    return candidates


def usable_polygon(roof, obstacles, grid, shade, config):
    c = config["layout"]
    usable = roof.buffer(-c["edge_setback_m"])
    exclusions = [o.buffer(c["obstacle_buffer_m"]) for o in obstacles]
    high = (shade>config["shading"]["max_annual_fraction"]) & grid.mask([roof])
    if high.any(): exclusions.append(grid.polygonize(high))
    if exclusions: usable = usable.difference(unary_union(exclusions))
    return usable


def pack_panels(usable, lat, lng, tilt, azimuth, config, pitched=False, convergence=0):
    if usable.is_empty: return [],0.0
    c = config["layout"]
    origin = usable.centroid
    angle = 180-azimuth+convergence
    aligned = rotate(usable,-angle,origin=origin)
    width = c["panel_width_m"]
    depth = c["panel_length_m"]*math.cos(math.radians(tilt))
    pitch = row_pitch(lat,lng,tilt,azimuth,config,pitched)
    step = width+c["panel_gap_m"]
    x0,y0,x1,y1 = aligned.bounds
    prepared = prep(aligned)
    best = []
    offsets = int(c["packing_offsets"])
    for ox in range(offsets):
        for oy in range(offsets):
            panels = []
            for y in np.arange(y0+oy*pitch/offsets,y1-depth+1e-8,pitch):
                for x in np.arange(x0+ox*step/offsets,x1-width+1e-8,step):
                    rect = box(x,y,x+width,y+depth)
                    if prepared.covers(rect): panels.append(rect)
            if len(panels)>len(best): best=panels
    return [rotate(p,angle,origin=origin) for p in best],pitch
