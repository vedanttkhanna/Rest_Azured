from __future__ import annotations
import copy
import json
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
import rasterio
from jsonschema import Draft202012Validator
from solar.config import load_config
from solar.geo import make_grid, metric, geojson, TO_METRIC
from solar.heights import build_heights
from solar.layout import row_pitch, pack_panels, orientations
from solar.report import simulate, validate_inputs
from solar.storage import Store, job_id
from solar.weather import get_weather, validate_weather
import handlers


def test_weather_cache_roundtrip_without_network(tmp_path,weather,monkeypatch,config):
    meta={"inputs":{"location":{"irradiance_time_offset":0.5},"meteo_data":{"radiation_db":"PVGIS-ERA5"}}}
    getter=Mock(return_value=(weather,meta))
    monkeypatch.setattr("solar.weather.pvlib.iotools.get_pvgis_tmy",getter)
    first,m1=get_weather(28.6,77.3,config,tmp_path)
    second,m2=get_weather(28.601,77.299,config,tmp_path)
    assert getter.call_count==1
    assert np.allclose(first.ghi,second.ghi)
    assert second.attrs["irradiance_time_offset_hours"]==0.5
    assert m2["source"]=="PVGIS-ERA5"


def test_s3_store_sidecar_roundtrip_and_input_scope(tmp_path):
    from botocore.stub import Stubber
    import boto3
    client=boto3.client("s3",region_name="ap-south-1",aws_access_key_id="test",aws_secret_access_key="test")
    with Stubber(client) as stub:
        stub.add_response("put_object",{}, {"Bucket":"jobs-test","Key":"jobs/j/sidecar.json","Body":b"{}","ContentType":"application/json"})
        store=Store(tmp_path,"jobs-test",client)
        assert store.put_bytes("jobs/j/sidecar.json",b"{}","application/json")=="s3://jobs-test/jobs/j/sidecar.json"
        with pytest.raises(ValueError,match="configured jobs bucket"): store.materialize("s3://another-bucket/private")
        with pytest.raises(ValueError,match="S3 input"): store.materialize("local.json")
        stub.assert_no_pending_responses()


def test_simulate_handler_uses_local_fixture_weather(tmp_path,job,segmentation,weather,monkeypatch):
    monkeypatch.delenv("JOBS_BUCKET",raising=False)
    monkeypatch.setenv("SOLAR_OUTPUT_DIR",str(tmp_path/"output"))
    path=tmp_path/"weather.csv"; weather.to_csv(path)
    report=handlers.simulate_handler({"A":job,"B":segmentation,"weather_uri":str(path),
            "weather_metadata":{"source":"synthetic_test_weather"},"config":{"layout":{"edge_setback_m":100}}})
    assert report["status"]=="done" and report["system"]["panel_count"]==0
    assert report["finance"]["payback_years"] is None


def test_complete_dsm_report(tmp_path,job,segmentation,weather,config):
    roofs,obs=validate_inputs(job,segmentation,config)
    grid=make_grid(job,config,[r["polygon"] for r in roofs])
    path=tmp_path/"dsm.tif"
    with rasterio.open(path,"w",driver="GTiff",height=grid.height,width=grid.width,count=1,
                       dtype="float32",crs=grid.crs,transform=grid.transform) as dst:
        dst.write(np.full(grid.shape,100,dtype="float32"),1)
    a={**job,"dsm_s3_uri":str(path),"imagery_source":"google_solar"}
    report=simulate(a,segmentation,Store(tmp_path/"result"),config,weather,{"source":"synthetic_test_weather"})
    assert report["data_sources"]["heights"]=="google_solar_dsm"
    assert report["system"]["panel_count"]>0
    assert report["energy"]["shade_loss_pct"]<0.01


def test_open_buildings_raster_supplies_roof_height(tmp_path,job,segmentation,config):
    roofs,obs=validate_inputs(job,segmentation,config)
    grid=make_grid(job,config,[r["polygon"] for r in roofs])
    path=tmp_path/"heights.tif"
    with rasterio.open(path,"w",driver="GTiff",height=grid.height,width=grid.width,count=1,
                       dtype="float32",crs=grid.crs,transform=grid.transform) as dst:
        dst.write(np.full(grid.shape,18,dtype="float32"),1)
    h,source,_=build_heights(grid,roofs,obs,{"features":[]},config,building_heights_path=path)
    assert source=="open_buildings_2.5d_with_defaults"
    assert np.isclose(h.max(),19)


def test_dsm_missing_target_coverage_rejected(tmp_path,job,segmentation,config):
    roofs,obs=validate_inputs(job,segmentation,config)
    grid=make_grid(job,config,[r["polygon"] for r in roofs])
    path=tmp_path/"dsm.tif"
    with rasterio.open(path,"w",driver="GTiff",height=grid.height,width=grid.width,count=1,
                       dtype="float32",crs=grid.crs,transform=grid.transform,nodata=-9999) as dst:
        dst.write(np.full(grid.shape,-9999,dtype="float32"),1)
    with pytest.raises(ValueError,match="entire target roof"):
        build_heights(grid,roofs,obs,{"features":[]},config,dsm_path=path)


def test_pitched_roof_orientation_and_flush_spacing(config):
    from shapely.geometry import box
    roof=box(0,0,20,20)
    assert orientations(roof,{"roof_type":"pitched","tilt_deg":30,"azimuth_deg":135},config)==[(30,135)]
    with pytest.raises(ValueError,match="Pitched roof"):
        orientations(roof,{"roof_type":"pitched","tilt_deg":None,"azimuth_deg":None},config)
    pitch=row_pitch(28.6,77.2,30,135,config,pitched=True)
    assert np.isclose(pitch,config["layout"]["panel_length_m"]*np.cos(np.radians(30))+config["layout"]["panel_gap_m"])
    panels,_=pack_panels(roof,28.6,77.2,30,135,config,pitched=True)
    assert panels and all(roof.covers(p) for p in panels)


def test_grid_limits_and_invalid_location(job,config):
    config["geo"]["max_grid_cells"]=10
    with pytest.raises(ValueError,match="grid cell limit"): make_grid(job,config)
    from solar.geo import check_location
    with pytest.raises(ValueError): check_location(float("nan"),77.3,config)
    with pytest.raises(ValueError): check_location(20,77.3,config)


@pytest.mark.parametrize("value",["../escape","/absolute","a/b","",None])
def test_job_id_path_safety(value):
    with pytest.raises(ValueError): job_id(value)


def test_duplicate_features_rejected(job,segmentation,config):
    bad=copy.deepcopy(segmentation)
    bad["features"].append(bad["features"][0])
    with pytest.raises(ValueError,match="Duplicate"): validate_inputs(job,bad,config)
