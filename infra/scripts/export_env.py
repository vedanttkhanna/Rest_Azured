"""Write web/.env.production (git-ignored) from the deployed stack outputs and print the values for P4."""
from __future__ import annotations

from pathlib import Path

import boto3

import dotenv  # noqa: F401  (loads .env: AWS_PROFILE, region)

REGION = "ap-south-1"
REPO = Path(__file__).resolve().parents[2]


def outputs(cf, stack: str) -> dict[str, str]:
    desc = cf.describe_stacks(StackName=stack)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in desc.get("Outputs", [])}


def main() -> None:
    cf = boto3.client("cloudformation", region_name=REGION)
    core, api = outputs(cf, "SolarCore"), outputs(cf, "SolarApi")
    env = {
        "VITE_API_URL": api["ApiUrl"],
        "VITE_USER_POOL_ID": core["UserPoolId"],
        "VITE_USER_POOL_CLIENT_ID": core["UserPoolClientId"],
        "VITE_REGION": core["Region"],
        "VITE_USE_MOCKS": "false",
    }
    target = REPO / "web" / ".env.production"
    target.parent.mkdir(exist_ok=True)
    target.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    print(f"wrote {target.relative_to(REPO)}:")
    for k, v in env.items():
        print(f"  {k}={v}")


if __name__ == "__main__":
    main()
