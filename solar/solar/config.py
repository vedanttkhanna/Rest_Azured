from __future__ import annotations
import copy
import math
from pathlib import Path
import yaml


def load_config(overrides=None):
    config = yaml.safe_load(Path(__file__).with_name("config.yaml").read_text(encoding="utf-8"))
    def merge(dst, src):
        for key, value in src.items():
            if key not in dst:
                raise ValueError(f"Unknown configuration key: {key}")
            if isinstance(dst[key], dict):
                if not isinstance(value, dict):
                    raise ValueError(f"Expected mapping for {key}")
                merge(dst[key], value)
            else:
                dst[key] = copy.deepcopy(value)
    if overrides:
        merge(config, overrides)
    def finite(obj):
        if isinstance(obj, dict):
            for v in obj.values(): finite(v)
        elif isinstance(obj, list):
            for v in obj: finite(v)
        elif isinstance(obj, (int, float)) and not math.isfinite(obj):
            raise ValueError("Configuration numbers must be finite")
    finite(config)
    for section, keys in {"geo": ["grid_resolution_m", "window_m", "max_grid_cells"],
                          "layout": ["panel_length_m", "panel_width_m", "panel_wp", "packing_offsets"],
                          "weather": ["grid_degrees", "timeout_s"],
                          "shading": ["max_distance_m"],
                          "energy": ["dc_ac_ratio"]}.items():
        for key in keys:
            if config[section][key] <= 0: raise ValueError(f"{section}.{key} must be positive")
    if config["geo"]["metric_crs"] != "EPSG:32643": raise ValueError("Delhi simulation requires EPSG:32643")
    if not isinstance(config["layout"]["packing_offsets"], int): raise ValueError("packing_offsets must be an integer")
    if not isinstance(config["finance"]["lifetime_years"], int): raise ValueError("lifetime_years must be an integer")
    if not 0 <= config["layout"]["azimuth_deg"] < 360: raise ValueError("Invalid panel azimuth")
    if config["heights"]["panel_mount_height_m"] < 0: raise ValueError("Invalid panel mounting height")
    if any(v < 0 for v in config["heights"]["obstacle_m"].values()): raise ValueError("Obstacle heights must be nonnegative")
    if config["heights"]["floor_height_m"] <= 0 or config["heights"]["default_floors"] <= 0: raise ValueError("Invalid building height defaults")
    if not 1 <= config["shading"]["representative_day"] <= 28: raise ValueError("Representative day must occur in every month")
    if not 0 <= config["shading"]["min_elevation_deg"] < 90: raise ValueError("Invalid minimum solar elevation")
    if config["fetch"]["esri_scale"] not in (1,2) or config["fetch"]["imagery_size_px"] != 512: raise ValueError("Unsupported inference tile dimensions")
    if not 1 <= config["layout"]["spacing_step_minutes"] <= 60: raise ValueError("Invalid row spacing sample interval")
    hours = config["layout"]["solar_hours"]
    if len(hours) != 2 or not 0 <= hours[0] < hours[1] < 24: raise ValueError("Invalid solar-time window")
    e = config["energy"]
    if not 0 <= e["soiling_loss_pct"] <= e["total_system_loss_pct"] < 100:
        raise ValueError("Soiling must be included within total system losses (0..100)")
    if not 0 < e["inverter_efficiency"] <= 1: raise ValueError("Invalid inverter efficiency")
    if not 0 <= config["shading"]["max_annual_fraction"] <= 1: raise ValueError("Invalid shade threshold")
    if not 0 <= config["layout"]["tilt_deg"] < 90: raise ValueError("Invalid panel tilt")
    for key in ["edge_setback_m", "obstacle_buffer_m", "panel_gap_m"]:
        if config["layout"][key] < 0: raise ValueError(f"{key} must be nonnegative")
    f = config["finance"]
    for key in ["capex_inr_per_kw", "tariff_inr_per_kwh", "subsidy_first_kw", "subsidy_first_rate", "subsidy_next_kw", "subsidy_next_rate", "subsidy_cap_inr", "grid_co2_t_per_mwh"]:
        if f[key] < 0: raise ValueError(f"{key} must be nonnegative")
    if not 0 <= f["degradation_per_year"] < 1 or f["lifetime_years"] <= 0:
        raise ValueError("Invalid finance lifetime/degradation")
    return config
