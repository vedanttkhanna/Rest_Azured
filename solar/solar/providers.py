from __future__ import annotations
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import requests
from shapely.geometry import Point, mapping, shape
from .geo import metric, TO_METRIC


class ProviderError(RuntimeError):
    def __init__(self,provider,status=None):
        self.status=status
        super().__init__(f"{provider} request failed"+(f" (HTTP {status})" if status else ""))


def google_key():
    if os.environ.get("GOOGLE_SOLAR_API_KEY"): return os.environ["GOOGLE_SOLAR_API_KEY"]
    if os.environ.get("GOOGLE_SOLAR_SSM_PARAMETER"):
        import boto3
        return boto3.client("ssm").get_parameter(Name=os.environ["GOOGLE_SOLAR_SSM_PARAMETER"],
                                                 WithDecryption=True)["Parameter"]["Value"]
    return None


class GoogleSolar:
    def __init__(self,key,config,session=None):
        self.key=key
        self.config=config["fetch"]
        self.session=session or requests.Session()

    def get(self,url,params):
        # Never include signed URLs, credentials, or upstream exception text in errors.
        host=urlparse(url)
        if host.scheme!="https" or host.hostname!="solar.googleapis.com":
            raise ValueError("Unexpected Google Solar download host")
        try:
            response=self.session.get(url,params={**params,"key":self.key},timeout=self.config["timeout_s"])
        except requests.RequestException:
            raise ProviderError("Google Solar") from None
        if response.status_code!=200: raise ProviderError("Google Solar",response.status_code)
        return response

    def insights(self,lat,lng):
        return self.get("https://solar.googleapis.com/v1/buildingInsights:findClosest",
                    {"location.latitude":lat,"location.longitude":lng,
                     "requiredQuality":self.config["google_quality"]}).json()

    def layers(self,lat,lng):
        return self.get("https://solar.googleapis.com/v1/dataLayers:get",
                    {"location.latitude":lat,"location.longitude":lng,
                     "radiusMeters":self.config["google_radius_m"],
                     "view":"IMAGERY_AND_ANNUAL_FLUX_LAYERS",
                     "requiredQuality":self.config["google_quality"],
                     "pixelSizeMeters":self.config["google_pixel_size_m"]}).json()

    def download(self,url,path):
        path.write_bytes(self.get(url,{}).content)
        return path


def fetch_footprints(bounds,path,config):
    """Publish only complete downloads; failed attempts cannot poison the cache."""
    path=Path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix=".geojson",delete=False) as handle:
            temporary=Path(handle.name)
        subprocess.run([sys.executable,"-X","utf8","-c","from overturemaps.cli import cli; cli()","download",
                        "--bbox="+",".join(map(str,bounds)),"-f","geojson","-t","building","-o",str(temporary)],
                       check=True,capture_output=True,timeout=config["fetch"]["footprint_timeout_s"])
        neighbors=json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(neighbors,dict) or neighbors.get("type")!="FeatureCollection" or not isinstance(neighbors.get("features"),list):
            raise ValueError("Invalid footprint collection")
        temporary.replace(path)
        return neighbors
    except (subprocess.SubprocessError,OSError,ValueError):
        raise ProviderError("Overture footprints") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def select_footprint(neighbors,lat,lng,max_distance):
    point=Point(*TO_METRIC(lng,lat))
    candidates=[]
    for feature in neighbors.get("features",[]):
        geometry=feature.get("geometry")
        if not geometry: continue
        try: poly=metric(geometry)
        except ValueError: continue
        for part in getattr(poly,"geoms",[poly]):
            if part.distance(point)<=max_distance:
                candidates.append((0 if part.covers(point) else 1,part.distance(point),part.area,part))
    if not candidates: return None
    from .geo import geojson
    return geojson(min(candidates,key=lambda p:p[:3])[3])


def export_open_buildings(bounds,path,config,project):
    """Optional authenticated Earth Engine adapter; never calls interactive auth.

    Service credentials must be configured by deployment. Package earthengine-api
    separately when enabling this optional path.
    """
    try: import ee
    except ImportError: raise RuntimeError("Install requirements-earthengine.txt to enable Open Buildings heights") from None
    ee.Initialize(project=project)
    year=config["fetch"]["open_buildings_year"]
    region=ee.Geometry.Rectangle(bounds,proj="EPSG:4326",geodesic=False)
    image=(ee.ImageCollection("GOOGLE/Research/open-buildings-temporal/v1")
           .filterBounds(region).filterDate(f"{year}-01-01",f"{year+1}-01-01")
           .select("building_height").mosaic())
    url=image.getDownloadURL({"region":region,"scale":4,"crs":"EPSG:32643","format":"GEO_TIFF"})
    try:
        response=requests.get(url,timeout=config["fetch"]["timeout_s"])
        response.raise_for_status()
    except requests.RequestException: raise ProviderError("Open Buildings heights") from None
    path.write_bytes(response.content)
    return path
