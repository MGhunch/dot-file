"""
Dot File - Airtable Operations
Lookup client SharePoint URLs, project folders, update records
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


def get_client_sharepoint(client_code):
    """
    Look up SharePoint URL for a client code
    Returns: { sharepoint_url: str, client_name: str } or None
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
        sharepoint_url = fields.get('Sharepoint URL')
        
        if not sharepoint_url:
            print(f'No SharePoint URL configured for: {client_code}')
            return None
        
        return {
            'sharepoint_url': sharepoint_url,
            'client_name': fields.get('Clients', client_code)
        }
        
    except Exception as e:
        print(f'Error looking up client SharePoint: {e}')
        return None


def get_project_folder(job_number):
    """
    Look up project folder name, current round, and existing Files URL
    Returns: { folder_name: str, round: int, record_id: str, files_url: str } or None
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
            print(f'No project found for: {job_number}')
            return None
        
        record = records[0]
        fields = record.get('fields', {})
        
        # Build folder name: "SKY 045 - Project Name" or just "SKY 045"
        project_name = fields.get('Project Name', '')
        if project_name:
            folder_name = f"{job_number} - {project_name}"
        else:
            folder_name = job_number
        
        return {
            'folder_name': folder_name,
            'round': fields.get('Round', 0) or 0,
            'record_id': record['id'],
            'files_url': fields.get('Files Url', '')  # Return existing Files URL if set
        }
        
    except Exception as e:
        print(f'Error looking up project: {e}')
        return None


def update_project_filing(record_id, round_number=None, files_url=None, destination=None):
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
        
        if files_url:
            fields['Files Url'] = files_url
        
        if destination:
            fields['Last Filed To'] = destination
        
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
