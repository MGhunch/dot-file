"""
Dot File - Power Automate Integration
Calls PA Filing flow to move files in SharePoint
"""

import requests
import os

PA_FILING_URL = os.environ.get('PA_FILING_URL')


def call_filing(source_site_url, source_path, source_files, dest_site_url, dest_path,
                create_folder=True, save_email=False, email_filename='', email_content=''):
    """
    Call PA Filing flow to move files from source to destination
    
    Returns: { success: bool, destFolderUrl: str, sourceFiles: list, emailSaved: str, error: str }
    """
    
    if not PA_FILING_URL:
        print('ERROR: PA_FILING_URL not configured')
        return {'success': False, 'error': 'PA_FILING_URL not configured'}
    
    payload = {
        'sourceSiteUrl': source_site_url,
        'sourcePath': source_path,
        'sourceFiles': source_files,
        'destSiteUrl': dest_site_url,
        'destPath': dest_path,
        'createFolder': create_folder,
        'saveEmail': save_email,
        'emailFilename': email_filename,
        'emailContent': email_content
    }
    
    print(f'Calling PA Filing:')
    print(f'  Source: {source_site_url}{source_path}')
    print(f'  Files: {source_files}')
    print(f'  Dest: {dest_site_url}{dest_path}')  # dest_path now includes /Shared Documents/
    print(f'  Create folder: {create_folder}')
    print(f'  Save email: {save_email}')
    
    try:
        response = requests.post(
            PA_FILING_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=120  # 2 minute timeout for file operations
        )
        
        print(f'PA response status: {response.status_code}')
        
        if response.status_code == 200:
            result = response.json()
            print(f'PA response: {result}')
            return result
        else:
            error_text = response.text[:500]
            print(f'PA error: {response.status_code} - {error_text}')
            return {
                'success': False,
                'error': f'PA returned {response.status_code}: {error_text}'
            }
            
    except requests.exceptions.Timeout:
        print('PA request timed out')
        return {'success': False, 'error': 'PA Filing request timed out'}
    except Exception as e:
        print(f'PA request failed: {e}')
        return {'success': False, 'error': str(e)}
