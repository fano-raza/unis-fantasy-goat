"""Google Sheets auth + spreadsheet-name lookup for the retired GDoc pipeline.

Split out of constants.py / shared/runtime_config.py (2026-10-07) so the
live app (dashboard_site, discord bot, stat_updater) no longer needs a
Google service-account credential just to import constants.py -- only
legacy/gdoc/*.py (GDoc_Week.py, GDoc_AllTime.py, GDoc_updater.py), which
nothing in production imports anymore, needs this module.
"""

import os

import gspread as gs

DEFAULT_GSPREAD_SERVICE_ACCOUNT = (
    "/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/"
    "gspread/fantasy-goat-306ebfffe1c2.json"
)
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    DEFAULT_GSPREAD_SERVICE_ACCOUNT,
)

gc = gs.service_account(GOOGLE_SERVICE_ACCOUNT_JSON_PATH)

## Spreadsheet Names ##
gDocNames = {
    2019: "ULTRA 18/19 Rankings",
    2020: "19/20 Rankings (The Numbers)",
    2021: "20/21 Rankings (The Numbers)",
    2022: "21/22 Rankings (The Numbers)",
    2023: "ULTRA 22/23 Rankings",
    2024: "23/24 Rankings (The Numbers)",
    2025: "24/25 Rankings (The Numbers)",
    2026: "25/26 Rankings (The Numbers)",
}
