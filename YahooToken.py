import webbrowser
from requests_oauthlib import OAuth2Session
from constants import yKey, ySec

# Your app credentials
client_id = yKey  # Replace with your Consumer Key
client_secret = ySec  # Replace with your Consumer Secret
redirect_uri = 'https://www.fanoraza.com/'  # This is your redirect URL (you can use localhost for testing)

# OAuth 2.0 endpoints
authorization_base_url = 'https://api.login.yahoo.com/oauth2/request_auth'
token_url = 'https://api.login.yahoo.com/oauth2/get_token'

# Create OAuth2 session
oauth = OAuth2Session(client_id, redirect_uri=redirect_uri)

# Get authorization URL
authorization_url, state = oauth.authorization_url(authorization_base_url)

# Open browser for user to authorize the app
print(f"Please go to {authorization_url} and authorize access.")
webbrowser.open(authorization_url)

# After authorization, you'll be redirected to a page (use localhost as the redirect URI for testing)
redirect_response = input('Paste the full redirect URL here: ')

# Fetch the access token
oauth.fetch_token(token_url, authorization_response=redirect_response, client_secret=client_secret)

# You now have the access token to make API calls
print(f"Access Token: {oauth.token['access_token']}")

class YahooTokenManager:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expiry = 0

    def is_token_expired(self):
        return time.time() >= self.token_expiry

    def get_access_token(self):
        if not self.access_token or self.is_token_expired():
            self.refresh_access_token()
        return self.access_token

    def refresh_access_token(self):
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": "oob",
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        response = requests.post(TOKEN_URL, data=payload)
        response.raise_for_status()
        token_data = response.json()

        self.access_token = token_data["access_token"]
        self.token_expiry = time.time() + token_data["expires_in"]
        print("Access token refreshed!")

# Usage
# manager = YahooTokenManager(client_id, client_secret, REFRESH_TOKEN)
# token = manager.get_access_token()
# headers = {"Authorization": f"Bearer {token}"}