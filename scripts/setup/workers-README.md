# Gmail OAuth Setup

This directory contains the Gmail OAuth2 authentication setup for the Cowork Dashboard project.

## Quick Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Download Google credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the Gmail API
   - Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
   - Choose "Desktop application" as application type
   - Download the JSON file and save it as `credentials.json` in this directory

3. **Run the authentication setup:**
   ```bash
   python setup_gmail_auth.py
   ```

4. **Follow the prompts** to complete OAuth flow and get your refresh token

## Files

- `setup_gmail_auth.py` - Main authentication setup script
- `credentials.json` - OAuth2 client credentials (download from Google Cloud Console)
- `token.json` - Generated access/refresh tokens (created by setup script)
- `requirements.txt` - Python dependencies

## Environment Variables

After setup, add this to your `.env` file:
```
GMAIL_REFRESH_TOKEN=your_refresh_token_here
```

The setup script will display the refresh token after successful authentication.