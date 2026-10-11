from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

from web.local.server import Jobs, make_geocoder, make_handler
from solar.config import load_config
from solar.storage import Store


class PipelineDouble:
    def __init__(self, root):
        self.config = load_config()
        self.store = Store(root)
        self.seen = []
        self.fail = False

    def fetch(self, job):
        self.seen.append(("fetch", job["lat"], job["lng"]))
        return {**job, "image_bounds": [job["lng"] - .001, job["lat"] - .001, job["lng"] + .001, job["lat"] + .001]}

    def segment(self, job):
        self.seen.append(("segment", job["lat"], job["lng"]))
        return {"features": [] if self.fail else [{"properties": {"kind": "roof"}}]}

    def simulate(self, job, segmentation):
        self.seen.append(("simulate", job["lat"], job["lng"]))
        return {"job_id": job["job_id"], "system": {"kw_dc": job["lng"], "panel_count": 1},
                "energy": {"annual_kwh": job["lat"]}, "finance": {"payback_years": None}}


class QueueDouble:
    def submit(self, *_args):
        pass


@pytest.fixture
def jobs(tmp_path):
    settings = {"max_batch": 25, "max_request_bytes": 65536, "model_version": "test"}
    result = Jobs(PipelineDouble(tmp_path), settings)
    result.executor.shutdown()
    result.executor = QueueDouble()
    return result


def test_each_rooftop_keeps_its_location_through_all_stages_and_restart(jobs):
    locations = [{"lat": 28.59, "lng": 77.04}, {"lat": 28.72, "lng": 77.13}]
    ids = [jobs.create(jobs.resolve(location)) for location in locations]
    for jid in ids:
        jobs.run(jid)
    for jid, location in zip(ids, locations):
        result = jobs.get(jid)
        assert result["status"] == "done"
        assert (result["lat"], result["lng"]) == (location["lat"], location["lng"])
        assert result["report"]["job_id"] == jid
        assert result["heatmap_png_url"] == f"/api/assets/{jid}/shade.png"
        assert result["kw_dc"] == location["lng"]
        for stage in ("fetch", "segment", "simulate"):
            assert (stage, location["lat"], location["lng"]) in jobs.pipeline.seen
    interrupted = jobs.create(jobs.resolve(locations[0]))
    restarted = Jobs(jobs.pipeline, jobs.settings)
    restarted.executor.shutdown()
    assert restarted.get(ids[0])["status"] == "done"
    assert restarted.get(interrupted)["status"] == "failed"
    assert "report" not in restarted.summaries()[0]


def test_no_roof_is_a_failure_without_a_sample_report(jobs):
    jobs.pipeline.fail = True
    jid = jobs.create(jobs.resolve({"lat": 28.6, "lng": 77.2}))
    jobs.run(jid)
    assert jobs.get(jid)["status"] == "failed"
    assert "No roof" in jobs.get(jid)["error"]
    assert "report" not in jobs.get(jid)
    assert not any(stage == "simulate" for stage, *_ in jobs.pipeline.seen)


@pytest.mark.parametrize("value", [{"lat": 19, "lng": 72}, {"lat": True, "lng": 77.2}, {"lat": float("nan"), "lng": 77.2}, {"lat": 28.6}, [], {"address": ""}])
def test_invalid_locations_never_create_jobs(jobs, value):
    with pytest.raises((ValueError, TypeError)):
        jobs.resolve(value)
    assert jobs.summaries() == []


def test_address_geocoder_is_optional_and_still_checks_service_bounds(jobs):
    with pytest.raises(ValueError, match="AWS credentials"):
        jobs.resolve("Dwarka, Delhi")
    jobs.geocoder = lambda _: {"lat": 28.59, "lng": 77.04, "label": "Resolved address"}
    assert jobs.resolve("Dwarka")["lat"] == 28.59
    jobs.geocoder = lambda _: {"lat": 19, "lng": 72}
    with pytest.raises(ValueError):
        jobs.resolve("Mumbai")


def test_http_batch_validation_roles_assets_and_untrusted_origin(jobs):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(jobs))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert requests.get(url + "/health").json()["mode"] == "local"
        assert requests.post(url + "/jobs", json={"lat": 28.6, "lng": 77.2}, headers={"Origin": "https://untrusted.test"}).status_code == 403
        assert requests.post(url + "/jobs/batch", json={"addresses": [{"lat": 28.6, "lng": 77.2}]}).status_code == 403
        invalid = requests.post(url + "/jobs/batch", json={"addresses": [{"lat": 28.6, "lng": 77.2}, {"lat": 19, "lng": 72}]}, headers={"X-Local-Role": "Installer"})
        assert invalid.status_code == 400
        assert invalid.json()["invalid"][0]["index"] == 1
        assert jobs.summaries() == []
        created = requests.post(url + "/jobs/batch", json={"addresses": [{"lat": 28.59, "lng": 77.04}, {"lat": 28.72, "lng": 77.13}]}, headers={"X-Local-Role": "Installer"})
        assert created.status_code == 201
        ids = created.json()["job_ids"]
        assert len(set(ids)) == 2
        assert requests.get(url + f"/jobs/{ids[1]}").json()["lng"] == 77.13
        path = jobs.root / "jobs" / ids[0] / "shade.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"sample-image")
        assert requests.get(url + f"/assets/{ids[0]}/shade.png").content == b"sample-image"
        assert requests.get(url + "/assets/index.json").status_code == 404
        assert requests.get(url + "/jobs/missing").status_code == 404
        assert requests.post(url + "/jobs", data="{invalid").status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


class SessionDouble:
    def __init__(self, credentials=None, error=None):
        self.credentials, self.error, self.clients = credentials, error, []

    def get_credentials(self):
        if self.error:
            raise self.error
        return self.credentials

    def client(self, name):
        self.clients.append(name)
        return object()


def test_unusable_aws_credentials_disable_address_lookup_instead_of_crashing(capsys):
    # e.g. `aws login` credentials without botocore[crt], or an expired session
    session = SessionDouble(error=RuntimeError("login credential provider requires botocore[crt]"))
    assert make_geocoder(session) is None
    assert "Address lookup disabled" in capsys.readouterr().out
    assert session.clients == []


def test_no_aws_credentials_means_no_address_lookup():
    assert make_geocoder(SessionDouble(credentials=None)) is None


def test_aws_credentials_enable_places_geocoder():
    session = SessionDouble(credentials=object())
    assert callable(make_geocoder(session))
    assert session.clients == ["geo-places"]
