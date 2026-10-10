from __future__ import annotations
import numpy as np
import pandas as pd
import pvlib
from .weather import validate_weather


def irradiance(weather, lat, lng, tilt, azimuth, config):
    validate_weather(weather)
    solar_times = weather.index + pd.Timedelta(hours=weather.attrs.get("irradiance_time_offset_hours",0))
    sun = pvlib.solarposition.get_solarposition(solar_times, lat, lng)
    sun.index = weather.index
    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azimuth, sun.apparent_zenith, sun.azimuth,
        weather.dni, weather.ghi, weather.dhi,
        dni_extra=pvlib.irradiance.get_extra_radiation(weather.index),
        albedo=config["energy"]["albedo"], model="haydavies")
    poa = poa.fillna(0).clip(lower=0)
    poa.loc[sun.apparent_elevation<=0, :] = 0
    local = solar_times.tz_convert(config["geo"]["timezone"])
    groups = (local.month.to_numpy()-1)*24 + local.hour.to_numpy()
    weights = np.bincount(groups, weights=poa.poa_direct.to_numpy(), minlength=288)
    return poa, groups, weights


def ac_power(poa_global, weather, kw_dc, config):
    cfg = config["energy"]
    temp = pvlib.temperature.sapm_cell(poa_global, weather.temp_air.to_numpy(),
           weather.wind_speed.to_numpy(), a=cfg["sapm_a"], b=cfg["sapm_b"], deltaT=cfg["sapm_delta_t"])
    dc = pvlib.pvsystem.pvwatts_dc(poa_global, temp, kw_dc*1000, cfg["gamma_pdc"])
    # Soiling is a visible component of this total, not an extra 5% deduction.
    dc = np.maximum(0, dc)*(1-cfg["total_system_loss_pct"]/100)
    inverter_dc_limit = kw_dc*1000/cfg["dc_ac_ratio"]/cfg["inverter_efficiency"]
    return np.maximum(0, pvlib.inverter.pvwatts(dc, pdc0=inverter_dc_limit,
                                              eta_inv_nom=cfg["inverter_efficiency"]))


def simulate_energy(weather, poa, groups, panel_shade, panel_count, config):
    kw = panel_count*config["layout"]["panel_wp"]/1000
    if not panel_count:
        return np.zeros(8760), np.zeros(8760)
    beam = poa.poa_direct.to_numpy()
    diffuse = poa.poa_diffuse.to_numpy()
    fraction = np.clip(np.asarray(panel_shade)[groups],0,1)
    shaded = ac_power(beam*(1-fraction)+diffuse, weather, kw, config)/1000
    unshaded = ac_power(beam+diffuse, weather, kw, config)/1000
    return shaded, unshaded


def summarize_energy(weather, shaded, unshaded, kw, config):
    months = weather.index.tz_convert(config["geo"]["timezone"]).month
    monthly = [round(float(np.sum(shaded[months==m])), 2) for m in range(1,13)]
    annual = round(sum(monthly), 2)
    baseline = float(np.sum(unshaded))
    return {"annual_kwh": annual, "monthly_kwh": monthly,
            "specific_yield_kwh_per_kwp": round(annual/kw, 2) if kw else 0.0,
            "shade_loss_pct": round(max(0, 100*(1-float(np.sum(shaded))/baseline)), 3) if baseline else 0.0}
