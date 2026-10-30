from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pvlib

COLUMNS = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]


def validate_weather(data):
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is None:
        raise ValueError("Weather timestamps must be timezone-aware")
    if len(data) != 8760 or not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError("Weather must contain one ordered, non-leap hourly year (8760 samples)")
    if not np.all(np.diff(data.index.asi8)==3600*10**9):
        raise ValueError("Weather must have contiguous hourly timestamps")
    if any(c not in data for c in COLUMNS): raise ValueError("Weather lacks required irradiance/temperature/wind columns")
    if not np.isfinite(data[COLUMNS].to_numpy()).all(): raise ValueError("Weather contains missing/nonfinite values")
    if (data[["ghi", "dni", "dhi", "wind_speed"]]<0).any().any(): raise ValueError("Negative irradiance or wind")
    if len(set(data.index.month))!=12: raise ValueError("Weather must cover all months")
    return data


def get_weather(lat, lng, config, cache, store=None):
    cfg = config["weather"]
    cell = cfg["grid_degrees"]
    lat, lng = round(round(lat/cell)*cell, 5), round(round(lng/cell)*cell, 5)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    signature = json.dumps([lat,lng,cfg,config["energy"]["year"]], sort_keys=True)
    key = "weather/"+hashlib.sha256(signature.encode()).hexdigest()[:24]+".json"
    dest = cache/Path(key).name
    if not dest.exists() and store:
        content = store.get_optional(key)
        if content is not None: dest.write_bytes(content)
    if dest.exists():
        payload = json.loads(dest.read_text(encoding="utf-8"))
        data = pd.read_json(io.StringIO(payload["frame"]), orient="table")
        metadata = payload["metadata"]
        data.attrs["irradiance_time_offset_hours"] = metadata.get("pvgis",{}).get("inputs",{}).get("location",{}).get("irradiance_time_offset",0)
        metadata["source"] = metadata.get("pvgis",{}).get("inputs",{}).get("meteo_data",{}).get("radiation_db",metadata["source"])
        return validate_weather(data), metadata
    data, meta = pvlib.iotools.get_pvgis_tmy(lat, lng, url=cfg["api_url"],
                    timeout=cfg["timeout_s"], usehorizon=cfg["use_horizon"],
                    map_variables=True, coerce_year=config["energy"]["year"])
    validate_weather(data)
    data = data.copy()
    data.attrs["irradiance_time_offset_hours"] = meta.get("inputs",{}).get("location",{}).get("irradiance_time_offset",0)
    metadata = {"source": meta.get("inputs",{}).get("meteo_data",{}).get("radiation_db","PVGIS-TMY"), "latitude": lat, "longitude": lng,
                "use_horizon": cfg["use_horizon"], "pvgis": meta}
    # Provider metadata is retained so actual radiation database/years are auditable.
    content = json.dumps({"frame": data.to_json(orient="table", date_format="iso"),
                          "metadata": metadata}, default=str).encode()
    temp = dest.with_suffix(".tmp")
    temp.write_bytes(content)
    temp.replace(dest)
    if store: store.put_bytes(key, content, "application/json")
    return data, metadata


def read_weather(path):
    data = pd.read_csv(path, index_col=0, parse_dates=True)
    data.index = pd.to_datetime(data.index, utc=True)
    return validate_weather(data)
