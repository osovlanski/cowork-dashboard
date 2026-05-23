"""
workers/github_push.py — Push a file to GitHub via the Contents API.

Used by Railway workers instead of git CLI commands, since Railway
containers have no .git metadata and can't run git push.

Required env vars:
  GITHUB_TOKEN  — personal access token with repo write scope
  GITHUB_REPO   — owner/repo, e.g. "osovlanski/cowork-dashboard"
                  (defaults to "osovlanski/cowork-dashboard")
"""

import os
import json
import base64
import ssl
import urllib.request
import urllib.error

_SSL_CTX = ssl._create_unverified_context()
_GITHUB_API = 'https://api.github.com'


def push_file(repo_path: str, content: str, commit_message: str) -> bool:
    """
    Create or update a file in the GitHub repo.

    Args:
        repo_path: path relative to repo root, e.g. "productive/emails/audit.md"
        content:   full file content as a string
        commit_message: git commit message

    Returns True on success, False on failure.
    """
    token = os.environ.get('GITHUB_TOKEN', '')
    repo  = os.environ.get('GITHUB_REPO', 'osovlanski/cowork-dashboard')

    if not token:
        print('  Warning: GITHUB_TOKEN not set — skipping GitHub push')
        return False

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept':        'application/vnd.github+json',
        'Content-Type':  'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    api_url = f'{_GITHUB_API}/repos/{repo}/contents/{repo_path}'

    # Fetch current file SHA (needed for updates; absent for new files)
    current_sha = _get_file_sha(api_url, headers)

    encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
    payload = {
        'message': commit_message,
        'content': encoded_content,
    }
    if current_sha:
        payload['sha'] = current_sha

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method='PUT',
    )
    try:
        urllib.request.urlopen(req, timeout=20, context=_SSL_CTX)
        print(f'  ✓ GitHub push: {repo_path}')
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f'  Warning: GitHub push failed ({e.code}): {body}')
        return False
    except Exception as e:
        print(f'  Warning: GitHub push error: {e}')
        return False


def _get_file_sha(api_url: str, headers: dict) -> str | None:
    """Return the current file SHA, or None if the file doesn't exist yet."""
    req = urllib.request.Request(api_url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
            return data.get('sha')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # New file
        raise
    except Exception:
        return None
