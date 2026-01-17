"""
Dot File - Airtable Operations
Lookup SharePoint site info, update project records
"""

import requests
import os
from datetime import datetime

AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID', 'app8CI7NAZqhQ4G1Y')

HEADERS = {
    'Authorization': f'Bearer {AIRTABLE_API_KEY}',
    'Content-Type': 'application/json'
}


def get_airtable_url(table):
    return f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}'


def get_sharepoint_site(client_code):
    """
    Look up SharePoint site ID for a client code
    Returns: { site_id: str, site_url: str } or None
    """
    try:
        url = get_airtable_url('Clients')
        params = {
            'filterByFormula': f"{{Client code}} = '{client_code}'",
            'maxRecords': 1
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            print(f'No client found for code: {client_code}')
            return None
        
        fields = records[0].get('fields', {})
        site_id = fields.get('Sharepoint ID')
        site_url = fields.get('Sharepoint URL', '')
        
        if not site_id:
            print(f'No SharePoint ID configured for: {client_code}')
            return None
        
        return {
            'site_id': site_id,
            'site_url': site_url,
            'client_name': fields.get('Clients', client_code)
        }
        
    except Exception as e:
        print(f'Error looking up SharePoint site: {e}')
        return None


def get_project_by_job_number(job_number):
    """
    Look up project record by job number
    Returns record ID and fields or None
    """
    try:
        url = get_airtable_url('Projects')
        params = {
            'filterByFormula': f"{{Job Number}} = '{job_number}'",
            'maxRecords': 1
        }
        
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            return None
        
        return {
            'id': records[0]['id'],
            'fields': records[0].get('fields', {})
        }
        
    except Exception as e:
        print(f'Error looking up project: {e}')
        return None


def update_project_filing(record_id, round_number=None, folder_url=None):
    """
    Update project record with filing info
    """
    if not record_id:
        print('No record ID provided for update')
        return False
    
    try:
        url = get_airtable_url('Projects')
        
        fields = {
            'Files Updated': datetime.now().isoformat()
        }
        
        if round_number is not None:
            fields['Round'] = round_number
        
        if folder_url:
            fields['Latest Folder URL'] = folder_url
        
        response = requests.patch(
            f'{url}/{record_id}',
            headers=HEADERS,
            json={'fields': fields}
        )
        
        response.raise_for_status()
        print(f'Updated Airtable record {record_id}')
        return True
        
    except Exception as e:
        print(f'Error updating project: {e}')
        return False


def log_filing_activity(job_number, destination, files_moved, success=True):
    """
    Log filing activity to Updates table
    """
    try:
        url = get_airtable_url('Updates')
        
        files_list = ', '.join(files_moved) if files_moved else 'No files'
        status = 'Filed' if success else 'Filing failed'
        
        # Build update message
        file_count = len(files_moved) if files_moved else 0
        update_text = f'{status}: {file_count} file(s) → {destination}'
        
        response = requests.post(
            url,
            headers=HEADERS,
            json={
                'fields': {
                    'Job Number': job_number,
                    'Update': update_text,
                    'Source': 'Dot File',
                    'Details': files_list[:1000]  # Truncate if very long
                }
            }
        )
        
        if response.status_code in [200, 201]:
            print(f'Logged filing activity for {job_number}')
            return True
        else:
            print(f'Failed to log activity: {response.status_code}')
            return False
        
    except Exception as e:
        print(f'Error logging activity: {e}')
        return False


def get_all_sharepoint_mappings():
    """
    Debug helper - get all client SharePoint mappings
    """
    try:
        url = get_airtable_url('Clients')
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        
        mappings = []
        for record in response.json().get('records', []):
            fields = record.get('fields', {})
            code = fields.get('Client code')
            site_id = fields.get('Sharepoint ID')
            if code:
                mappings.append({
                    'code': code,
                    'name': fields.get('Clients', ''),
                    'site_id': site_id or 'NOT SET',
                    'site_url': fields.get('Sharepoint URL', '')
                })
        
        return mappings
        
    except Exception as e:
        print(f'Error getting mappings: {e}')
        return []
