import webbrowser
from requests_oauthlib import OAuth2Session
from constants import yKey, ySec, yRefTok, yLeagueIDs, yGameIDs
import time
import requests
import json

# Constants
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
BASE_API_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
CLIENT_ID = yKey
CLIENT_SECRET = ySec
REDIRECT_URI = "https://yourdomain.com/oauth/callback"
REFRESH_TOKEN = yRefTok
league_keys = {year: f"{yGameIDs.get(year)}.l.{yLeagueIDs.get(year)}" for year in yLeagueIDs}

# Token storage (you can use a file or database in a real-world app)
token_data = {
    "access_token": None,
    "expires_at": 0
}

def refresh_access_token():
    """Refreshes the access token using the refresh token."""
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    response = requests.post(TOKEN_URL, data=payload)
    if response.status_code == 200:
        token_response = response.json()
        token_data["access_token"] = token_response["access_token"]
        token_data["expires_at"] = time.time() + token_response["expires_in"] - 60  # Buffer of 60 seconds
        print("Access token refreshed successfully.")
    else:
        raise Exception(f"Failed to refresh token: {response.status_code} - {response.text}")

def get_access_token():
    """Returns a valid access token, refreshing it if necessary."""
    if token_data["access_token"] is None or time.time() >= token_data["expires_at"]:
        refresh_access_token()
    return token_data["access_token"]

def make_yahoo_api_request(endpoint, params=None):
    """Makes a request to the Yahoo Fantasy API with automatic token management."""
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    url = f"{BASE_API_URL}/{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        # return json.dumps(response.json(), indent = 1)
        return response.json()
    else:
        raise Exception(f"API request failed: {response.status_code} - {response.text}")

def construct_endpoint(league_key, resource, params=None):
    """
    Constructs an endpoint URL dynamically.

    :param league_key: The league key for Yahoo Fantasy (e.g., '428.l.138772').
    :param resource: The API resource to access (e.g., 'teams', 'players').
    :param params: Dictionary of query parameters.
    :return: A formatted endpoint string.
    """
    base_resource = f"league/{league_key}/{resource}"
    if params:
        query_string = ";".join(f"{key}={value}" for key, value in params.items())
        return f"{base_resource};{query_string}?format=json"
    return f"{base_resource}?format=json"

# Example Usage
if __name__ == "__main__":
    year = 2025

    try:
        # Build endpoint for league teams stats for week 1
        endpoint_team = construct_endpoint(
            league_keys[year],
            resource="teams",
            params={"type": "week", "week": 1}
        )

        for startPoint in range(0,25,25):
            # Build endpoint for league players
            endpoint_player = construct_endpoint(
                league_keys[year],
                resource="players",
                #sort = OR (overall rank), AR (actual rank)
                params={"sort": "OR", "start":  startPoint, "count": 2}
            )

            response = make_yahoo_api_request(endpoint_player)
            print(response['fantasy_content']['league'][1]['players'].values())
            format_response = json.dumps(response,indent=2)
            print(format_response)
    except Exception as e:
        print(f"Error: {e}")