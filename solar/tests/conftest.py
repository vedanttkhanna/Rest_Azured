from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pvlib
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"solar"))
from solar.config import load_config


@pytest.fixture
def config(): return load_config()


@pytest.fixture
def job(): return json.loads((ROOT/"contracts/fixtures/job_A.json").read_text())


@pytest.fixture
def segmentation(): return json.loads((ROOT/"contracts/fixtures/seg_B.json").read_text())


@pytest.fixture(scope="session")
def weather():
    times=pd.date_range("2023-01-01",periods=8760,freq="h",tz="UTC")
    location=pvlib.location.Location(28.604,77.294)
    data=location.get_clearsky(times,model="ineichen")
    data[["ghi","dni","dhi"]]*=0.75
    data["temp_air"]=25.0
    data["wind_speed"]=1.0
    return data
