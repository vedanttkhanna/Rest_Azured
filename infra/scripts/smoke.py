"""End-to-end smoke test against the deployed stacks (needs AWS credentials for the account).

Creates two throw-away Cognito users (Homeowner, Installer), signs in with ADMIN_USER_PASSWORD_AUTH, exercises
every route, waits for one job to finish, and deletes the users again.

  python infra/scripts/smoke.py                       # coordinates of the fixture building
  python infra/scripts/smoke.py --address "Pocket A, Mayur Vihar Phase 1, Delhi"   # also tests geocoding
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.request

import boto3

REGION = "ap-south-1"
FIXTURE_POINT = {"lat": 28.6039825, "lng": 77.2935395}


def outputs(cf, stack):
    return {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]}


def request(method, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw.decode(errors="replace")}


class Smoke:
    def __init__(self):
        cf = boto3.client("cloudformation", region_name=REGION)
        core, api = outputs(cf, "SolarCore"), outputs(cf, "SolarApi")
        self.url, self.pool, self.client_id = api["ApiUrl"], core["UserPoolId"], core["UserPoolClientId"]
        self.idp = boto3.client("cognito-idp", region_name=REGION)
        self.users, self.failures = [], 0

    def check(self, name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        self.failures += not ok

    def user(self, label, groups):
        email = f"smoke-{label}-{secrets.token_hex(3)}@example.com"
        password = secrets.token_urlsafe(12) + "aA1"
        self.idp.admin_create_user(UserPoolId=self.pool, Username=email, MessageAction="SUPPRESS",
                                   UserAttributes=[{"Name": "email", "Value": email},
                                                   {"Name": "email_verified", "Value": "true"}])
        self.users.append(email)
        self.idp.admin_set_user_password(UserPoolId=self.pool, Username=email, Password=password, Permanent=True)
        for g in groups:
            self.idp.admin_add_user_to_group(UserPoolId=self.pool, Username=email, GroupName=g)
        auth = self.idp.admin_initiate_auth(UserPoolId=self.pool, ClientId=self.client_id,
                                            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                                            AuthParameters={"USERNAME": email, "PASSWORD": password})
        return auth["AuthenticationResult"]["AccessToken"]

    def cleanup(self):
        for email in self.users:
            self.idp.admin_delete_user(UserPoolId=self.pool, Username=email)

    def wait(self, token, job_id, timeout_s):
        seen, deadline, body = [], time.time() + timeout_s, {}
        while time.time() < deadline:
            _, body = request("GET", f"{self.url}/jobs/{job_id}", token)
            if not seen or seen[-1] != body.get("status"):
                seen.append(body.get("status"))
            if body.get("status") in ("done", "failed"):
                break
            time.sleep(3)
        return seen, body

    def run(self, address, timeout_s):
        home = self.user("homeowner", ["Homeowner"])
        installer = self.user("installer", ["Installer"])

        status, _ = request("GET", f"{self.url}/jobs")
        self.check("no token -> 401", status == 401, str(status))

        payload = {"address": address} if address else FIXTURE_POINT
        t0 = time.time()
        status, body = request("POST", f"{self.url}/jobs", home, payload)
        self.check("POST /jobs -> 201", status == 201, json.dumps(body))
        if status == 201:
            seen, job = self.wait(home, body["job_id"], timeout_s)
            self.check("job reaches done", job.get("status") == "done",
                       f"{' -> '.join(map(str, seen))} in {time.time() - t0:.0f}s {job.get('error', '')}")
            report = job.get("report") or {}
            self.check("report has system + energy", "system" in report and "energy" in report)
            if job.get("heatmap_png_url"):
                with urllib.request.urlopen(job["heatmap_png_url"], timeout=20) as r:
                    self.check("presigned heatmap downloads", r.status == 200 and r.headers["Content-Type"] == "image/png")
            status, other = request("GET", f"{self.url}/jobs/{body['job_id']}", installer)
            self.check("other user's job -> 404", status == 404, str(status))
            status, listing = request("GET", f"{self.url}/jobs", home)
            self.check("GET /jobs lists it", status == 200 and any(j["job_id"] == body["job_id"]
                                                                   for j in listing.get("jobs", [])))

        status, body = request("POST", f"{self.url}/jobs", home, {"lat": 19.07, "lng": 72.87})
        self.check("outside Delhi -> 400", status == 400, body.get("error", ""))
        status, body = request("POST", f"{self.url}/jobs/batch", home, {"addresses": [FIXTURE_POINT]})
        self.check("Homeowner batch -> 403 (Cedar)", status == 403, body.get("error", ""))
        status, body = request("POST", f"{self.url}/jobs/batch", installer,
                               {"addresses": [FIXTURE_POINT, {"lat": 28.5921, "lng": 77.046}]})
        self.check("Installer batch -> 201", status == 201 and len(body.get("job_ids", [])) == 2, json.dumps(body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", help="use an address instead of fixture coordinates (tests Location Service)")
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait for the job")
    ap.add_argument("--keep-users", action="store_true")
    args = ap.parse_args()
    smoke = Smoke()
    try:
        smoke.run(args.address, args.timeout)
    finally:
        if not args.keep_users:
            smoke.cleanup()
    print("ALL PASSED" if smoke.failures == 0 else f"{smoke.failures} FAILED")
    sys.exit(1 if smoke.failures else 0)


if __name__ == "__main__":
    main()
