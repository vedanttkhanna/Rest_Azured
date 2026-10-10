"""P2 Lambda entry points. P3 owns orchestration and deployment."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from solar.config import load_config
from solar.fetch import fetch_job
from solar.providers import google_key
from solar.report import simulate
from solar.storage import Store
from solar.weather import read_weather


def _run(event,operation):
    config=load_config(event.get("config"))
    bucket=os.environ.get("JOBS_BUCKET")
    if bucket:
        with tempfile.TemporaryDirectory(prefix="solar-") as tmp:
            return operation(Store(tmp,bucket),config)
    return operation(Store(os.environ.get("SOLAR_OUTPUT_DIR","data/solar")),config)


def fetch_handler(event,context=None):
    return _run(event,lambda store,config:fetch_job(event,store,config,google_key()))


def simulate_handler(event,context=None):
    def work(store,config):
        a=event["A"]
        b=event["B"]
        if isinstance(a,str): a=json.loads(store.materialize(a).read_text())
        if isinstance(b,str): b=json.loads(store.materialize(b).read_text())
        weather=read_weather(store.materialize(event["weather_uri"])) if event.get("weather_uri") else None
        return simulate(a,b,store,config,weather=weather,
                        weather_metadata=event.get("weather_metadata"),neighbors=event.get("neighbors"))
    return _run(event,work)
