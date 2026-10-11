from __future__ import annotations
import io
import json
import math
import numpy as np
import rasterio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling, transform_bounds
from .geo import check_location, make_grid, metric
from .providers import GoogleSolar, ProviderError, fetch_footprints, select_footprint, export_open_buildings
from .storage import job_id


def image_grid(lat,lng,config):
    c=config["fetch"]
    size=c["imagery_size_px"]
    if size!=512: raise ValueError("P1 requires 512x512 imagery")
    spacing=2*math.pi*6378137/(256*2**c["esri_zoom"])/c["esri_scale"]
    x,y=Transformer.from_crs(4326,3857,always_xy=True).transform(lng,lat)
    half=size*spacing/2
    bounds=(x-half,y-half,x+half,y+half)
    return from_bounds(*bounds,size,size),bounds,list(transform_bounds(3857,4326,*bounds)),spacing*math.cos(math.radians(lat))


def esri_image(lat,lng,config,session=None):
    c=config["fetch"]
    size,scale,z=c["imagery_size_px"],c["esri_scale"],c["esri_zoom"]
    n=2**z
    gx=(lng+180)/360*n*256
    gy=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n*256
    half=size/scale/2
    x0,y0,x1,y1=gx-half,gy-half,gx+half,gy+half
    tx0,ty0,tx1,ty1=map(math.floor,(x0/256,y0/256,x1/256,y1/256))
    canvas=Image.new("RGB",((tx1-tx0+1)*256,(ty1-ty0+1)*256))
    session=session or requests.Session()
    for ty in range(ty0,ty1+1):
        for tx in range(tx0,tx1+1):
            try:
                r=session.get(c["esri_url"].format(z=z,y=ty,x=tx),timeout=c["timeout_s"])
                r.raise_for_status()
                tile=Image.open(io.BytesIO(r.content)).convert("RGB")
            except (requests.RequestException,OSError): raise ProviderError("Esri imagery") from None
            if tile.size!=(256,256): raise ProviderError("Esri imagery dimensions")
            canvas.paste(tile,((tx-tx0)*256,(ty-ty0)*256))
    # Fractional EXTENT transform keeps the image center and declared bounds aligned.
    return np.asarray(canvas.transform((size,size),Image.Transform.EXTENT,
                  (x0-tx0*256,y0-ty0*256,x1-tx0*256,y1-ty0*256),Image.Resampling.BICUBIC))


def normalize_rgb(source,transform,size=512):
    out=np.zeros((3,size,size),dtype="uint8")
    with rasterio.open(source) as src:
        if not src.crs or src.count<3: raise ValueError("RGB input requires georeferencing and three bands")
        valid=np.zeros((size,size),dtype="uint8")
        reproject(src.dataset_mask(),valid,src_transform=src.transform,src_crs=src.crs,
                  dst_transform=transform,dst_crs="EPSG:3857",resampling=Resampling.nearest)
        if not valid.all(): raise ValueError("RGB source does not fully cover the centered inference tile")
        for band in range(3):
            reproject(rasterio.band(src,band+1),out[band],src_transform=src.transform,src_crs=src.crs,
                      dst_transform=transform,dst_crs="EPSG:3857",resampling=Resampling.bilinear)
    return out.transpose(1,2,0)


def fetch_job(event,store,config,key=None):
    jid=job_id(event["job_id"])
    lat,lng=check_location(event["lat"],event["lng"],config)
    prefix=f"jobs/{jid}/"
    transform,mbounds,bounds,gsd=image_grid(lat,lng,config)
    warnings=[]
    provider=event.get("provider","auto")
    if provider not in ("auto","esri","google_solar","upload"): raise ValueError("Unknown imagery provider")
    dsm=None
    metadata={"output_gsd_m":gsd,"imagery_projection":"EPSG:3857"}
    image=None
    if provider in ("auto","google_solar") and key:
        google=GoogleSolar(key,config)
        try:
            layers=google.layers(lat,lng)
            rgb=google.download(layers["rgbUrl"],store.path(prefix+"source_rgb.tif"))
            image=normalize_rgb(rgb,transform)
            dsm_path=google.download(layers["dsmUrl"],store.path(prefix+"dsm.tif"))
            dsm=store.publish(prefix+"dsm.tif",dsm_path,"image/tiff")
            for name,field in [("mask","maskUrl"),("annual_flux","annualFluxUrl")]:
                if layers.get(field):
                    p=google.download(layers[field],store.path(prefix+name+".tif"))
                    store.publish(prefix+name+".tif",p,"image/tiff")
            provider="google_solar"
            metadata.update({k:layers[k] for k in ("imageryDate","imageryQuality","imageryProcessedDate") if k in layers})
            metadata["source_pixel_size_m"]=config["fetch"]["google_pixel_size_m"]
        except ProviderError as exc:
            if provider=="google_solar" or exc.status!=404: raise
            warnings.append("Google Solar has no coverage at this location; Esri fallback used")
    elif provider=="google_solar": raise ValueError("Google Solar credentials are not configured")
    if provider=="upload":
        image=normalize_rgb(store.materialize(event["image_s3_uri"]),transform)
        if event.get("dsm_s3_uri"):
            dsm=store.publish(prefix+"dsm.tif",store.materialize(event["dsm_s3_uri"]),"image/tiff")
    if image is None:
        image=esri_image(lat,lng,config)
        provider="esri"
        metadata["source_pixel_size_m"]=gsd*config["fetch"]["esri_scale"]
        if not key: warnings.append("Google Solar coverage not checked: credentials not configured")
    dest=store.path(prefix+"rgb.tif")
    with rasterio.open(dest,"w",driver="GTiff",width=512,height=512,count=3,dtype="uint8",
                       crs="EPSG:3857",transform=transform,compress="deflate") as dst:
        dst.write(image.transpose(2,0,1))
    image_uri=store.publish(prefix+"rgb.tif",dest,"image/tiff")
    # Fetch a context window larger than the P1 tile for neighboring-building shadows.
    tile_outline={"type":"Polygon","coordinates":[[[bounds[0],bounds[1]],[bounds[2],bounds[1]],
                    [bounds[2],bounds[3]],[bounds[0],bounds[3]],[bounds[0],bounds[1]]]]}
    grid=make_grid({"lat":lat,"lng":lng},config,[metric(tile_outline)])
    context_bounds=list(transform_bounds(grid.crs,4326,*grid.bounds))
    if "neighbors" in event:
        neighbors=event["neighbors"]
    else:
        try: neighbors=fetch_footprints(context_bounds,store.path(prefix+"neighbors.geojson"),config)
        except ProviderError:
            neighbors={"type":"FeatureCollection","features":[]}
            warnings.append("Footprint provider failed; target footprint and surrounding shading may be incomplete")
    store.put_json(prefix+"neighbors.geojson",neighbors)
    footprint=event.get("footprint") or select_footprint(neighbors,lat,lng,config["fetch"]["footprint_nearest_m"])
    if footprint is None: warnings.append("No target footprint found; P1 may merge attached roofs")
    height_uri=None
    if event.get("building_heights_uri"):
        p=store.materialize(event["building_heights_uri"])
        height_uri=store.publish(prefix+"building_heights.tif",p,"image/tiff")
    elif event.get("earth_engine_project"):
        p=export_open_buildings(context_bounds,store.path(prefix+"building_heights.tif"),config,event["earth_engine_project"])
        height_uri=store.publish(prefix+"building_heights.tif",p,"image/tiff")
    job={"job_id":jid,"lat":lat,"lng":lng,"address":event.get("address",""),
         "image_s3_uri":image_uri,"image_bounds":bounds,"gsd_m":round(gsd,6),
         "dsm_s3_uri":dsm,"footprint":footprint,"imagery_source":provider}
    # Sidecars avoid changing contract A: simulate finds these at deterministic keys.
    store.put_json(prefix+"fetch_metadata.json",{**metadata,"warnings":warnings,"building_heights_uri":height_uri})
    store.put_json(prefix+"job_A.json",job)
    return job
