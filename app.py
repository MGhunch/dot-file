"""
Dot File - Attachment Filing Service
Receives requests from Traffic, classifies content, calls PA Filing.

UPDATED: Files Url approach
- Every project must have Files Url in Airtable
- No more path construction - just use what Airtable remembers
- Friendly error if no job bag set up
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
from datetime import datetime

import airtable
import power_automate

app = Flask(__name__)
CORS(app)

# Hunch SharePoint (where Incoming folder lives)
HUNCH_SITE_URL = os.environ.get('HUNCH_SITE_URL', 'https://hunch.sharepoint.com/sites/Hunch614')
INCOMING_PATH = '/Shared Documents/-- Incoming'


@app.route('/')
def health():
    return jsonify({'status': 'ok', 'service': 'dot-file', 'version': '2.0'})


@app.route('/file', methods=['POST'])
def file_attachments():
    """
    Main endpoint - receives filing request from Traffic
    
    FILES URL APPROACH:
    1. Look up project in Airtable
    2. Get Files Url (required - no construction)
    3. Classify where files should go (subfolder)
    4. Call PA Filing
    """
    try:
        data = request.get_json()
        
        # Extract fields from Traffic payload
        job_number = data.get('jobNumber')
        client_code = data.get('clientCode')
        sender_name = data.get('senderName', 'Unknown')
        sender_email = data.get('senderEmail', '')
        subject_line = data.get('subjectLine', '')
        email_content = data.get('emailContent', '')
        attachment_names = data.get('attachmentNames', [])
        has_attachments = data.get('hasAttachments', False)
        received_datetime = data.get('receivedDateTime', '')
        project_record_id = data.get('projectRecordId')
        all_recipients = data.get('allRecipients', [])
        
        # Fix: attachmentNames might arrive as a JSON string instead of a list
        if isinstance(attachment_names, str):
            try:
                attachment_names = json.loads(attachment_names)
            except json.JSONDecodeError:
                # If it's a single filename string, wrap it in a list
                attachment_names = [attachment_names] if attachment_names else []
        
        print(f'=== DOT FILE v2.0 ===')
        print(f'Job: {job_number} | Client: {client_code}')
        print(f'From: {sender_email}')
        print(f'Attachments: {attachment_names}')
        
        if not job_number:
            return jsonify({
                'success': False, 
                'error': 'Missing jobNumber',
                'filed': False
            }), 400
        
        # 1. Get project info from Airtable (including Files Url)
        project_info = airtable.get_project_folder(job_number)
        
        if not project_info:
            return jsonify({
                'success': False, 
                'error': f'No project found for {job_number}',
                'filed': False
            }), 404
        
        # 2. Get Files Url - this is REQUIRED
        files_url = project_info.get('files_url')
        
        if not files_url:
            return jsonify({
                'success': False,
                'error': f'No job bag for {job_number}. Reply TRIAGE to set one up.',
                'errorType': 'no_job_bag',
                'filed': False
            }), 400
        
        # Get other project info
        if not project_record_id:
            project_record_id = project_info.get('record_id')
        
        print(f'Files Url: {files_url}')
        
        # 3. Parse Files Url to get site and path
        # Format: https://hunch.sharepoint.com/sites/Labour/Shared Documents/LAB 055 - Election 26
        try:
            # Split into site URL and path
            if '/Shared Documents/' in files_url:
                parts = files_url.split('/Shared Documents/')
                dest_site_url = parts[0]  # https://hunch.sharepoint.com/sites/Labour
                job_folder_path = parts[1]  # LAB 055 - Election 26
            else:
                raise ValueError(f'Invalid Files Url format: {files_url}')
        except Exception as e:
            print(f'Error parsing Files Url: {e}')
            return jsonify({
                'success': False,
                'error': f'Invalid Files Url format for {job_number}',
                'filed': False
            }), 400
        
        print(f'Dest site: {dest_site_url}')
        print(f'Job folder: {job_folder_path}')
        
        # 4. Determine destination folder from route or folderType
        route = data.get('route', '')
        folder_type = data.get('folderType', '')  # Direct override from Ask Dot
        
        # Route to folder mapping
        ROUTE_TO_FOLDER = {
            'triage': 'briefs',
            'new-job': 'briefs',
            'work-to-client': 'round',
            'feedback': 'feedback',
            'file': 'other',
            'update': 'other',
        }
        
        # folderType override takes priority, then route mapping, then default
        if folder_type:
            resolved_folder = folder_type
        else:
            resolved_folder = ROUTE_TO_FOLDER.get(route, 'other')
        
        print(f'Route: {route} | FolderType: {folder_type} | Resolved: {resolved_folder}')
        
        # 5. Handle Round logic if work-to-client
        round_number = None
        if resolved_folder == 'round':
            # Get current round from Airtable and increment
            current_round = project_info.get('round', 0) or 0
            round_number = current_round + 1
            destination_folder = f"-- Round {round_number}"
            print(f'Outgoing work - Round {round_number}')
        else:
            # Map folder type to actual folder name
            FOLDER_NAMES = {
                'briefs': '-- Briefs',
                'feedback': '-- Feedback',
                'other': '-- Other',
            }
            destination_folder = FOLDER_NAMES.get(resolved_folder, '-- Other')
        
        # 6. Build full destination path (include /Shared Documents/ for SharePoint API)
        dest_path = f"/Shared Documents/{job_folder_path}/{destination_folder}"
        folder_url = f"{files_url}/{destination_folder}"
        
        print(f'Destination path: {dest_path}')
        print(f'Folder URL: {folder_url}')
        
        # 7. Build .eml filename if we have email content
        eml_filename = ''
        eml_content = ''
        if email_content:
            eml_filename = create_eml_filename(sender_name, received_datetime)
            eml_content = create_eml_content(
                sender_name=sender_name,
                sender_email=sender_email,
                recipients=all_recipients,
                subject=subject_line,
                html_content=email_content,
                received_datetime=received_datetime
            )
        
        # 8. Call PA Filing
        pa_result = power_automate.call_filing(
            source_site_url=HUNCH_SITE_URL,
            source_path=INCOMING_PATH,
            source_files=attachment_names if has_attachments else [],
            dest_site_url=dest_site_url,
            dest_path=dest_path,
            create_folder=True,
            save_email=bool(email_content),
            email_filename=eml_filename,
            email_content=eml_content
        )
        
        print(f'PA result: {pa_result}')
        
        if not pa_result.get('success'):
            return jsonify({
                'success': False,
                'error': pa_result.get('error', 'PA Filing failed'),
                'filed': False
            }), 500
        
        # 9. Update Airtable with round number if applicable
        if project_record_id and round_number:
            airtable.update_project_filing(
                record_id=project_record_id,
                round_number=round_number,
                destination=destination_folder
            )
        
        # 10. Build response
        files_moved = pa_result.get('sourceFiles', [])
        if pa_result.get('emailSaved'):
            files_moved.append(pa_result['emailSaved'])
        
        return jsonify({
            'success': True,
            'filed': True,
            'jobNumber': job_number,
            'destination': destination_folder,
            'destPath': dest_path,
            'folderUrl': folder_url,
            'filesUrl': files_url,
            'filesMoved': files_moved,
            'roundNumber': round_number,
            'route': route,
            'folderType': resolved_folder
        })
        
    except Exception as e:
        print(f'Error in /file: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'filed': False}), 500


def create_eml_filename(sender_name, received_datetime):
    """Create filename like 'Email from Sarah - 18 Jan 2026.eml'"""
    try:
        dt = datetime.fromisoformat(received_datetime.replace('Z', '+00:00'))
        date_str = dt.strftime('%d %b %Y')
    except:
        date_str = datetime.now().strftime('%d %b %Y')
    
    # Get first name, clean up
    clean_name = sender_name.split()[0] if sender_name else 'Unknown'
    clean_name = ''.join(c for c in clean_name if c.isalnum() or c in ' -_')
    
    return f"Email from {clean_name} - {date_str}.eml"


def create_eml_content(sender_name, sender_email, recipients, subject, html_content, received_datetime):
    """Create .eml file content"""
    recipient_str = ', '.join(recipients) if recipients else ''
    
    try:
        dt = datetime.fromisoformat(received_datetime.replace('Z', '+00:00'))
        email_date = dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    except:
        email_date = received_datetime
    
    return f"""MIME-Version: 1.0
Date: {email_date}
From: {sender_name} <{sender_email}>
To: {recipient_str}
Subject: {subject}
Content-Type: text/html; charset="utf-8"

{html_content}
"""


if __name__ == '__main__':
    app.run(debug=True, port=5001)
