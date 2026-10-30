from __future__ import annotations
import copy
import json
import time
import numpy as np
import pytest
import rasterio
from PIL import Image
from shapely.geometry import shape
from solar.geo import metric, make_grid
from solar.heights import build_heights
from solar.report import simulate, validate_inputs
from solar.storage import Store


def test_full_fixture_report(tmp_path,job,segmentation,weather,config):
    start=time.perf_counter()
    report=simulate(job,segmentation,Store(tmp_path),config,weather,{"source":"synthetic_test_weather"})
    elapsed=time.perf_counter()-start
    assert elapsed<60
    assert report["system"]["panel_count"]==len(report["panels"]["features"])>0
    assert 0<report["building"]["usable_area_m2"]<report["building"]["roof_area_m2"]
    assert report["energy"]["annual_kwh"]>0
    roof=metric(segmentation["features"][0]["geometry"])
    for p in report["panels"]["features"]:
        assert roof.buffer(-config["layout"]["edge_setback_m"]+1e-6).covers(metric(p["geometry"]))
    image=Image.open(report["heatmap_png_s3_uri"])
    assert image.mode=="RGBA" and np.array(image)[:,:,3].min()==0
    assert any("neighboring" in w for w in report["assumptions"]["warnings"])
    assert (tmp_path/f"jobs/{job['job_id']}/report_C.json").exists()
    print(f"fixture simulation: {elapsed:.2f}s; {report['system']['panel_count']} panels")


def test_zero_panel_report(tmp_path,job,segmentation,weather,config):
    config["layout"]["edge_setback_m"]=100
    report=simulate(job,segmentation,Store(tmp_path),config,weather,{"source":"synthetic_test_weather"})
    assert report["system"]["panel_count"]==0
    assert report["energy"]["annual_kwh"]==0
    assert report["finance"]["payback_years"] is None


def test_invalid_upstream(job,segmentation,config):
    bad=copy.deepcopy(segmentation); bad["job_id"]="different"
    with pytest.raises(ValueError,match="IDs differ"): validate_inputs(job,bad,config)
    bad["job_id"]=job["job_id"]; bad["features"]=[]
    with pytest.raises(ValueError,match="No roof"): validate_inputs(job,bad,config)


def test_dsm_path_does_not_double_add_obstacles(tmp_path,job,segmentation,config):
    roofs,obs=validate_inputs(job,segmentation,config)
    grid=make_grid(job,config,[r["polygon"] for r in roofs])
    path=tmp_path/"dsm.tif"
    data=np.full(grid.shape,100,dtype="float32")
    with rasterio.open(path,"w",driver="GTiff",height=grid.height,width=grid.width,count=1,
                       dtype="float32",crs=grid.crs,transform=grid.transform) as dst: dst.write(data,1)
    h,source,warnings=build_heights(grid,roofs,obs,{"features":[]},config,dsm_path=path)
    assert np.all(h==100) and source=="supplied_dsm"


def test_height_defaults_and_obstacle_roof_reference(job,segmentation,config):
    roofs,obs=validate_inputs(job,segmentation,config)
    grid=make_grid(job,config,[r["polygon"] for r in roofs])
    h,source,warnings=build_heights(grid,roofs,obs,{"features":[]},config)
    assert np.isclose(h.max(),13.8)
    assert source=="footprint_heights_with_defaults"


def test_orientation_choice_prefers_energy_over_panel_count(tmp_path,job,segmentation,weather,config,monkeypatch):
    import solar.report as report_module
    real_pack=report_module.pack_panels
    monkeypatch.setattr(report_module,"orientations",lambda *a,**k:[(25.0,180.0),(25.0,90.0)])

    def pack(usable,lat,lng,tilt,azimuth,*args):
        # The east-facing candidate gets one extra panel on the same footprint.
        panels,pitch=real_pack(usable,lat,lng,tilt,180.0,*args)
        return (panels+panels[:1] if azimuth==90.0 else panels),pitch
    monkeypatch.setattr(report_module,"pack_panels",pack)
    report=simulate(job,segmentation,Store(tmp_path),config,weather,{"source":"synthetic_test_weather"})
    assert report["system"]["azimuth_deg"]==180.0


def test_store_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError): Store(tmp_path).path("../../secret")
