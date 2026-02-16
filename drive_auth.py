#!/usr/bin/env python3
"""Google Drive authentication and download script."""

import os
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = os.path.expanduser('~/.claude/.google/client_secret.json')
TOKEN_FILE = os.path.expanduser('~/.claude/.google/token.pickle')

def get_credentials():
    """Get valid credentials, prompting for auth if needed."""
    creds = None

    # Load existing token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"ERROR: Credentials file not found at {CREDENTIALS_FILE}")
                print("\nTo set up Google Drive access:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project and enable Google Drive API")
                print("3. Create OAuth 2.0 credentials (Desktop app)")
                print(f"4. Download JSON and save to {CREDENTIALS_FILE}")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)

    return creds

def get_drive_service():
    """Get authenticated Drive service."""
    creds = get_credentials()
    if not creds:
        return None
    return build('drive', 'v3', credentials=creds)

def list_folder(service, folder_id):
    """List files in a folder."""
    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType, size)",
        pageSize=100
    ).execute()
    return results.get('files', [])

def download_file(service, file_id, output_path):
    """Download a file from Drive."""
    request = service.files().get_media(fileId=file_id)
    with open(output_path, 'wb') as f:
        f.write(request.execute())
    print(f"Downloaded: {output_path}")

if __name__ == "__main__":
    service = get_drive_service()
    if service:
        print("Successfully authenticated with Google Drive!")

        # Test with แพร่ folder
        folder_id = "1wD2ICNJHLhW0UaisZpW8ie49RC8Ba50v"
        print(f"\nListing files in folder {folder_id}:")
        files = list_folder(service, folder_id)
        for f in files[:10]:
            print(f"  - {f['name']} ({f.get('size', 'N/A')} bytes)")
