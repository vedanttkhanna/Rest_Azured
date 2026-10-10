from __future__ import annotations
import json
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from solar.config import load_config
from solar.fetch import fetch_job, image_grid, normalize_rgb
from solar.providers import ProviderError, GoogleSolar, select_footprint
from solar.storage import Store


def test_esri_fetch_contract_and_georeferencing(tmp_path,job,config,monkeypatch):
    monkeypatch.setattr("solar.fetch.esri_image",lambda *a:np.full((512,512,3),100,dtype="uint8"))
    neighbors={"type":"FeatureCollection","features":[{"type":"Feature","geometry":job["footprint"],"properties":{}}]}
    result=fetch_job({"job_id":"fetch-test","lat":job["lat"],"lng":job["lng"],"provider":"esri","neighbors":neighbors},Store(tmp_path),config)
    assert result["imagery_source"]=="esri" and result["footprint"]
    with rasterio.open(result["image_s3_uri"]) as src:
        assert src.shape==(512,512) and src.crs.to_epsg()==3857
        from pyproj import Transformer
        lon,lat=Transformer.from_crs(src.crs,4326,always_xy=True).transform(*(src.transform*(256,256)))
        assert abs(lon-job["lng"])<1e-9 and abs(lat-job["lat"])<1e-9
    assert (tmp_path/"jobs/fetch-test/neighbors.geojson").exists()


def test_google_path_and_dsm(tmp_path,job,config,monkeypatch):
    transform,*_=image_grid(job["lat"],job["lng"],config)
    class Google:
        def __init__(self,*a): pass
        def layers(self,*a): return {"rgbUrl":"rgb","dsmUrl":"dsm","imageryQuality":"BASE"}
        def download(self,url,path):
            bands=3 if url=="rgb" else 1
            with rasterio.open(path,"w",driver="GTiff",height=512,width=512,count=bands,
                               crs="EPSG:3857",transform=transform,dtype="uint8") as dst:
                dst.write(np.full((bands,512,512),100,dtype="uint8"))
            return path
    monkeypatch.setattr("solar.fetch.GoogleSolar",Google)
    result=fetch_job({**job,"provider":"google_solar","neighbors":{"features":[]}},Store(tmp_path),config,key="test-secret")
    assert result["imagery_source"]=="google_solar" and result["dsm_s3_uri"]
    assert "test-secret" not in (tmp_path/f"jobs/{job['job_id']}/fetch_metadata.json").read_text()


@pytest.mark.parametrize("status,fallback",[(404,True),(403,False),(429,False),(500,False)])
def test_google_auto_only_falls_back_for_no_coverage(tmp_path,job,config,monkeypatch,status,fallback):
    class Google:
        def __init__(self,*a): pass
        def layers(self,*a): raise ProviderError("Google Solar",status)
    monkeypatch.setattr("solar.fetch.GoogleSolar",Google)
    monkeypatch.setattr("solar.fetch.esri_image",lambda *a:np.zeros((512,512,3),dtype="uint8"))
    event={**job,"provider":"auto","neighbors":{"features":[]}}
    if fallback:
        result=fetch_job(event,Store(tmp_path),config,key="test-secret")
        assert result["imagery_source"]=="esri"
    else:
        with pytest.raises(ProviderError): fetch_job(event,Store(tmp_path),config,key="test-secret")


def test_provider_error_does_not_leak_key(config):
    class Session:
        def get(self,*a,**kw):
            import requests
            raise requests.ConnectionError("URL contains VERY_SECRET")
    with pytest.raises(ProviderError) as exc:
        GoogleSolar("VERY_SECRET",config,Session()).insights(28.6,77.2)
    assert "VERY_SECRET" not in str(exc.value)


def test_select_footprint_does_not_select_distant_building(job):
    neighbors={"features":[{"geometry":job["footprint"]}]}
    assert select_footprint(neighbors,job["lat"],job["lng"],5)
    assert select_footprint(neighbors,28.7,77.1,5) is None


def test_upload_requires_complete_coverage(tmp_path,job,config):
    transform,*_=image_grid(job["lat"],job["lng"],config)
    p=tmp_path/"partial.tif"
    with rasterio.open(p,"w",driver="GTiff",height=10,width=10,count=3,dtype="uint8",crs="EPSG:3857",transform=transform) as dst:
        dst.write(np.ones((3,10,10),dtype="uint8"))
    with pytest.raises(ValueError,match="fully cover"): normalize_rgb(p,transform)


def test_installed_overture_entry_point_runs_without_network():
    import subprocess
    import sys
    from importlib.metadata import distribution
    entry = next(e for e in distribution("overturemaps").entry_points if e.name == "overturemaps")
    assert entry.value == "overturemaps.cli:cli"
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", "from overturemaps.cli import cli; cli()", "download", "--help"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "--bbox" in result.stdout


@pytest.mark.parametrize("failure",["timeout","malformed","wrong_shape"])
def test_footprint_failure_preserves_complete_cache(tmp_path,config,monkeypatch,failure):
    import subprocess
    from pathlib import Path
    from solar.providers import fetch_footprints
    destination=tmp_path/"neighbors.geojson"
    original='{"type":"FeatureCollection","features":[]}'
    destination.write_text(original)
    def download(args,**kwargs):
        output=Path(args[-1])
        output.write_text('{"features": [' if failure!="wrong_shape" else '[]')
        if failure=="timeout": raise subprocess.TimeoutExpired(args,1)
    monkeypatch.setattr("solar.providers.subprocess.run",download)
    with pytest.raises(ProviderError):
        fetch_footprints([77,28,78,29],destination,config)
    assert destination.read_text()==original
    assert list(tmp_path.iterdir())==[destination]


def test_complete_footprints_replace_cache(tmp_path,config,monkeypatch):
    from pathlib import Path
    from solar.providers import fetch_footprints
    destination=tmp_path/"neighbors.geojson"
    destination.write_text("old partial download")
    expected={"type":"FeatureCollection","features":[],"name":"दिल्ली"}
    def download(args,**kwargs):
        assert args[1:3]==["-X","utf8"]
        Path(args[-1]).write_text(json.dumps(expected,ensure_ascii=False),encoding="utf-8")
    monkeypatch.setattr("solar.providers.subprocess.run",download)
    assert fetch_footprints([77,28,78,29],destination,config)==expected
    assert json.loads(destination.read_text(encoding="utf-8"))==expected
    assert list(tmp_path.iterdir())==[destination]
