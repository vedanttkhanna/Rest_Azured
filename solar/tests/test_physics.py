from __future__ import annotations
import numpy as np
import pytest
from shapely.geometry import box
from solar.config import load_config
from solar.geo import Grid
from solar.shading import ray_shadow
from solar.layout import row_pitch, pack_panels
from solar.finance import calculate_finance
from solar.energy import irradiance, simulate_energy, summarize_energy
from solar.weather import validate_weather


@pytest.mark.parametrize("azimuth,position,receiver",[
    (90,(10,10),(10,5)),(270,(10,10),(10,15)),(0,(10,10),(15,10)),(180,(10,10),(5,10))])
def test_shadow_cardinal_directions(azimuth,position,receiver):
    h=np.zeros((25,25)); h[position]=3
    rows,cols=np.array([receiver[0]]),np.array([receiver[1]])
    assert ray_shadow(h,rows,cols,30,azimuth,1,20)[0]
    assert not ray_shadow(h,rows,cols,60,azimuth,1,20)[0]


def test_cube_analytic_shadow_length():
    h=np.zeros((80,80)); h[20:32,40:52]=3
    rows=np.full(30,25); cols=np.arange(10,40)
    shaded=ray_shadow(h,rows,cols,45,90,0.25,10)
    # A 3 m cube at 45 degrees casts 3 m; strict > excludes the endpoint.
    assert shaded.sum()==11
    assert np.all(cols[shaded]>40-3/0.25)


def test_no_shadow_wrap_at_edge():
    h=np.zeros((10,10)); h[:,0]=100
    assert not ray_shadow(h,np.array([5]),np.array([9]),20,90,1,50)[0]


def test_row_spacing_and_packing(config):
    pitch=row_pitch(28.6,77.2,25,180,config)
    depth=config["layout"]["panel_length_m"]*np.cos(np.radians(25))
    assert pitch>depth
    usable=box(0,0,12,20).difference(box(4,5,7,10))
    panels,_=pack_panels(usable,28.6,77.2,25,180,config)
    assert panels and all(usable.covers(p) for p in panels)
    for i,p in enumerate(panels):
        assert all(p.intersection(q).area<1e-8 for q in panels[i+1:])


@pytest.mark.parametrize("kw,expected",[(0,0),(1,30000),(2,60000),(2.5,69000),(3,78000),(10,78000)])
def test_subsidy_tiers(kw,expected,config):
    result,_=calculate_finance(kw,kw*1500,config)
    assert result["subsidy_inr"]==expected
    if kw==0: assert result["payback_years"] is None


def test_finance_no_subsidy_and_zero_savings(config):
    config["finance"]["subsidy_eligible"]=False
    result,_=calculate_finance(3,0,config)
    assert result["subsidy_inr"]==0 and result["payback_years"] is None


def test_beam_only_shading(weather,config):
    poa,groups,weights=irradiance(weather,28.6,77.2,25,180,config)
    clear,baseline=simulate_energy(weather,poa,groups,np.zeros(288),10,config)
    shade,_=simulate_energy(weather,poa,groups,np.ones(288),10,config)
    assert np.allclose(clear,baseline)
    assert 0<shade.sum()<clear.sum()
    report=summarize_energy(weather,clear,baseline,5.4,config)
    assert abs(report["annual_kwh"]-sum(report["monthly_kwh"]))<0.01
    assert report["shade_loss_pct"]==0


def test_weather_requires_complete_ordered_finite_year(weather):
    with pytest.raises(ValueError): validate_weather(weather.iloc[:-1])
    bad=weather.copy(); bad.iloc[0,0]=np.nan
    with pytest.raises(ValueError): validate_weather(bad)
    with pytest.raises(ValueError): validate_weather(weather.iloc[::-1])


@pytest.mark.parametrize("overrides",[{"energy":{"total_system_loss_pct":4}},
    {"geo":{"grid_resolution_m":0}},{"finance":{"tariff_inr_per_kwh":-1}},
    {"layout":{"tilt_deg":90}},{"unknown":1}])
def test_config_rejects_invalid(overrides):
    with pytest.raises(ValueError): load_config(overrides)
