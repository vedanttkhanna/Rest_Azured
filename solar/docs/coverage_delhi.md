# Google Solar coverage: pending live credentials

As of this implementation, **no live Google coverage request has been made**. No API-key location was supplied. Missing credentials are not evidence that Delhi lacks coverage. There are no fabricated 404s or coverage claims in this document.

The adapter supports `buildingInsights:findClosest`, data layers, RGB/DSM normalization and caching of mask/annual-flux layers. Tests exercise success, coverage 404, authentication/quota/server errors and credential-safe failures with mocked responses. They do not establish real coverage.

Run from the repository root after P3 configures SSM access:

```powershell
$env:GOOGLE_SOLAR_SSM_PARAMETER = '/solarrooftop/google_api_key'
$env:AWS_DEFAULT_REGION = 'ap-south-1'
solar/.venv312/Scripts/python.exe solar/validation/check_coverage.py --limit 10
```

Use only the parameter name in commands and logs. For local testing the adapter also accepts `GOOGLE_SOLAR_API_KEY` from the process environment. It never writes the key or signed provider URLs into reports. Provider errors contain a provider name and HTTP status only.

The first ten rows of `validation/locations.csv` are public candidate locations spanning Mayur Vihar, Dwarka, Rohini, Vasant Kunj, Vasant Vihar, Lajpat Nagar and Defence Colony. These are sampling locations, not surveyed roofs. The script records `covered`, `not_covered` (404 only), or `request_failed` and returned imagery dates/quality in `data/solar/coverage_delhi.json`.

Current API pricing, billing eligibility and exact data rights must be checked by the deployment owner before production use; this implementation does not rely on the old brief's free-tier numbers. See the [Google data layers reference](https://developers.google.com/maps/documentation/solar/reference/rest/v1/dataLayers/get).
