"""
SharePoint operations via Microsoft Graph API
Handles authentication, folder operations, file moves
"""

import requests
import os
from datetime import datetime, timedelta

# Auth credentials from environment
TENANT_ID = os.environ.get('MS_TENANT_ID')
CLIENT_ID = os.environ.get('MS_CLIENT_ID')
CLIENT_SECRET = os.environ.get('MS_CLIENT_SECRET')

# Hunch SharePoint site for Incoming folder
HUNCH_SITE_ID = os.environ.get('HUNCH_SITE_ID')
INCOMING_FOLDER_PATH = '/Shared Documents/-- Incoming'

# Token cache
_token_cache = {
    'access_token': None,
    'expires_at': None
}


def get_access_token():
    """Get Graph API access token (cached)"""
    now = datetime.now()
    
    # Return cached token if still valid
    if _token_cache['access_token'] and _token_cache['expires_at']:
        if now < _token_cache['expires_at'] - timedelta(minutes=5):
            return _token_cache['access_token']
    
    # Request new token
    url = f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    response = requests.post(url, data=data)
    response.raise_for_status()
    result = response.json()
    
    # Cache token
    _token_cache['access_token'] = result['access_token']
    _token_cache['expires_at'] = now + timedelta(seconds=result['expires_in'])
    
    print(f'Got new Graph API token, expires in {result["expires_in"]}s')
    
    return _token_cache['access_token']


def graph_request(method, endpoint, **kwargs):
    """Make authenticated Graph API request"""
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    url = f'https://graph.microsoft.com/v1.0{endpoint}'
    response = requests.request(method, url, headers=headers, **kwargs)
    
    return response


def find_job_folder(site_id, job_number):
    """
    Find folder matching job number prefix (e.g., 'SKY 045' matches 'SKY 045 - Banner Campaign')
    Returns folder info dict or None
    """
    # List folders in Shared Documents
    endpoint = f'/sites/{site_id}/drive/root:/Shared Documents:/children'
    response = graph_request('GET', endpoint)
    
    if response.status_code != 200:
        print(f'Error listing folders: {response.status_code} {response.text}')
        return None
    
    folders = response.json().get('value', [])
    
    # Find folder starting with job number
    job_prefix = job_number.strip()
    matches = []
    
    for folder in folders:
        if folder.get('folder') and folder['name'].startswith(job_prefix):
            matches.append(folder)
    
    if not matches:
        print(f'No folder found matching: {job_prefix}')
        return None
    
    if len(matches) > 1:
        print(f'Warning: Multiple folders match {job_number}, using first: {matches[0]["name"]}')
    
    return {
        'id': matches[0]['id'],
        'name': matches[0]['name'],
        'webUrl': matches[0].get('webUrl', '')
    }


def get_subfolders(site_id, folder_id):
    """Get list of subfolders in a folder"""
    endpoint = f'/sites/{site_id}/drive/items/{folder_id}/children'
    response = graph_request('GET', endpoint)
    
    if response.status_code != 200:
        print(f'Error getting subfolders: {response.status_code}')
        return []
    
    items = response.json().get('value', [])
    return [item for item in items if item.get('folder')]


def get_next_round_number(site_id, job_folder_id):
    """
    Find highest existing Round number and return next
    e.g., if 'Round 2' exists, return 3
    """
    subfolders = get_subfolders(site_id, job_folder_id)
    
    max_round = 0
    for folder in subfolders:
        name = folder.get('name', '')
        # Match '-- Round X' or 'Round X'
        if 'Round' in name:
            try:
                # Extract number after 'Round'
                parts = name.split('Round')
                if len(parts) > 1:
                    num_str = parts[1].strip().split()[0]  # Get first word after Round
                    num = int(num_str)
                    max_round = max(max_round, num)
            except (ValueError, IndexError):
                continue
    
    next_round = max_round + 1
    print(f'Existing max round: {max_round}, next round: {next_round}')
    return next_round


def ensure_subfolder(site_id, parent_folder_id, folder_name):
    """
    Ensure subfolder exists, create if not. Returns folder ID.
    Adds '--' prefix if not present for our managed folders.
    """
    # Ensure -- prefix for managed folders
    if folder_name in ['Briefs', 'Feedback', 'Other'] and not folder_name.startswith('--'):
        folder_name = f'-- {folder_name}'
    
    # Check if folder already exists
    subfolders = get_subfolders(site_id, parent_folder_id)
    for folder in subfolders:
        if folder['name'] == folder_name:
            print(f'Folder exists: {folder_name}')
            return folder['id']
    
    # Create folder
    print(f'Creating folder: {folder_name}')
    endpoint = f'/sites/{site_id}/drive/items/{parent_folder_id}/children'
    data = {
        'name': folder_name,
        'folder': {},
        '@microsoft.graph.conflictBehavior': 'fail'
    }
    
    response = graph_request('POST', endpoint, json=data)
    
    if response.status_code in [200, 201]:
        return response.json()['id']
    
    # If conflict (already exists), try to find it
    if response.status_code == 409:
        print(f'Folder conflict, searching again: {folder_name}')
        subfolders = get_subfolders(site_id, parent_folder_id)
        for folder in subfolders:
            if folder['name'] == folder_name:
                return folder['id']
    
    raise Exception(f'Failed to create folder {folder_name}: {response.status_code} {response.text}')


def get_incoming_files(filenames):
    """
    Get file IDs from the Incoming folder on Hunch site
    Returns dict mapping filename to file info
    """
    endpoint = f'/sites/{HUNCH_SITE_ID}/drive/root:{INCOMING_FOLDER_PATH}:/children'
    response = graph_request('GET', endpoint)
    
    if response.status_code != 200:
        print(f'Error listing Incoming folder: {response.status_code} {response.text}')
        return {}
    
    items = response.json().get('value', [])
    
    file_map = {}
    for item in items:
        if item['name'] in filenames:
            file_map[item['name']] = {
                'id': item['id'],
                'name': item['name'],
                'size': item.get('size', 0)
            }
    
    print(f'Found {len(file_map)}/{len(filenames)} files in Incoming')
    return file_map


def move_file(source_site_id, file_id, dest_site_id, dest_folder_id, new_name=None):
    """
    Move a file to destination folder (potentially cross-site)
    """
    # If same site, use move
    if source_site_id == dest_site_id:
        endpoint = f'/sites/{source_site_id}/drive/items/{file_id}'
        data = {
            'parentReference': {
                'id': dest_folder_id
            }
        }
        if new_name:
            data['name'] = new_name
        
        response = graph_request('PATCH', endpoint, json=data)
        success = response.status_code in [200, 201]
        if not success:
            print(f'Move failed: {response.status_code} {response.text}')
        return success
    
    # Cross-site: copy then delete
    else:
        # Get destination drive ID
        dest_drive_endpoint = f'/sites/{dest_site_id}/drive'
        drive_response = graph_request('GET', dest_drive_endpoint)
        if drive_response.status_code != 200:
            print(f'Failed to get dest drive: {drive_response.status_code}')
            return False
        dest_drive_id = drive_response.json()['id']
        
        # Copy file
        endpoint = f'/sites/{source_site_id}/drive/items/{file_id}/copy'
        data = {
            'parentReference': {
                'driveId': dest_drive_id,
                'id': dest_folder_id
            }
        }
        if new_name:
            data['name'] = new_name
        
        response = graph_request('POST', endpoint, json=data)
        
        if response.status_code == 202:  # Accepted (async copy)
            # Delete original after copy initiated
            delete_endpoint = f'/sites/{source_site_id}/drive/items/{file_id}'
            delete_response = graph_request('DELETE', delete_endpoint)
            print(f'Copy initiated, delete status: {delete_response.status_code}')
            return True
        
        print(f'Copy failed: {response.status_code} {response.text}')
        return False


def move_files_from_incoming(dest_site_id, dest_folder_id, filenames):
    """
    Move files from Hunch Incoming folder to destination
    Returns list of successfully moved filenames
    """
    file_map = get_incoming_files(filenames)
    moved = []
    
    for filename in filenames:
        if filename in file_map:
            print(f'Moving: {filename}')
            success = move_file(
                source_site_id=HUNCH_SITE_ID,
                file_id=file_map[filename]['id'],
                dest_site_id=dest_site_id,
                dest_folder_id=dest_folder_id
            )
            if success:
                moved.append(filename)
            else:
                print(f'Failed to move: {filename}')
        else:
            print(f'File not found in Incoming: {filename}')
    
    return moved


def save_email_as_eml(site_id, folder_id, filename, sender_name, sender_email, 
                       recipients, subject, html_content, received_datetime):
    """
    Create and upload .eml file to SharePoint
    """
    # Build RFC822-style .eml content
    recipient_str = ', '.join(recipients) if recipients else ''
    
    # Format date for email header
    try:
        dt = datetime.fromisoformat(received_datetime.replace('Z', '+00:00'))
        email_date = dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    except:
        email_date = received_datetime
    
    eml_content = f"""MIME-Version: 1.0
Date: {email_date}
From: {sender_name} <{sender_email}>
To: {recipient_str}
Subject: {subject}
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: quoted-printable

{html_content}
"""
    
    # Upload to SharePoint
    endpoint = f'/sites/{site_id}/drive/items/{folder_id}:/{filename}:/content'
    
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'text/plain'
    }
    
    url = f'https://graph.microsoft.com/v1.0{endpoint}'
    response = requests.put(url, headers=headers, data=eml_content.encode('utf-8'))
    
    success = response.status_code in [200, 201]
    if not success:
        print(f'Failed to save email: {response.status_code} {response.text}')
    
    return success


def get_folder_url(site_id, folder_id):
    """Get web URL for a folder"""
    endpoint = f'/sites/{site_id}/drive/items/{folder_id}'
    response = graph_request('GET', endpoint)
    
    if response.status_code == 200:
        return response.json().get('webUrl', '')
    
    return ''


def list_incoming_folder():
    """Debug helper - list all files in Incoming folder"""
    endpoint = f'/sites/{HUNCH_SITE_ID}/drive/root:{INCOMING_FOLDER_PATH}:/children'
    response = graph_request('GET', endpoint)
    
    if response.status_code != 200:
        return {'error': f'{response.status_code} {response.text}'}
    
    items = response.json().get('value', [])
    return [{'name': item['name'], 'size': item.get('size', 0)} for item in items]
