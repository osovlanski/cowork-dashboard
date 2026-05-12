"""
setup_gmail_auth.py — Run this ONCE locally to get your Gmail refresh token.

Usage:
  1. Create a Google Cloud project at https://console.cloud.google.com
  2. Enable the Gmail API
  3. Create OAuth 2.0 credentials (type: Desktop app)
  4. Download credentials.json to this directory
  5. Run: python workers/setup_gmail_auth.py
  6. A browser window opens → log in → grant access
  7. Copy the printed GMAIL_REFRESH_TOKEN into Railway env vars
"""

import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')

def main():
    if not os.path.exists(CREDS_FILE):
        print("ERROR: credentials.json not found.")
        print("Download it from Google Cloud Console → APIs & Services → Credentials")
        print(f"Place it at: {CREDS_FILE}")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n" + "="*60)
    print("✅ Authentication successful! Add these to Railway env vars:")
    print("="*60)

    with open(CREDS_FILE) as f:
        client_info = json.load(f)['installed']

    print(f"\nGMAIL_CLIENT_ID     = {client_info['client_id']}")
    print(f"GMAIL_CLIENT_SECRET = {client_info['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN = {creds.refresh_token}")
    print("\n" + "="*60)
    print("Keep these SECRET — never commit them to git.")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()
