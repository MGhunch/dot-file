"""
Dot File - Attachment Filing Service
Receives requests from Traffic, classifies content, calls PA Filing.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime

import classifier
import airtable
import power_automate

app = Flask(__name__)
CORS(app)

# Hunch SharePoint (where Incoming folder lives)
HUNCH_SITE_URL = os.environ.get('HUNCH_SITE_URL', 'https://hunch.sharepoint.com/sites/Hunch614')
INCOMING_PATH = '/Shared Documents/-- Incoming'


@app.route('/')
def health():
    return jsonify({'status': 'ok', 'service': 'dot-file'})


@app.route('/file', methods=['POST'])
def file_attachments():
    """
    Main endpoint - receives filing request from Traffic
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
        
        print(f'=== DOT FILE ===')
        print(f'Job: {job_number} | Client: {client_code}')
        print(f'From: {sender_email}')
        print(f'Attachments: {attachment_names}')
        
        if not job_number or not client_code:
            return jsonify({'success': False, 'error': 'Missing jobNumber or clientCode'}), 400
        
        # 1. Get client SharePoint URL from Airtable
        client_info = airtable.get_client_sharepoint(client_code)
        if not client_info:
            return jsonify({'success': False, 'error': f'No SharePoint URL for {client_code}'}), 404
        
        print(f'Dest site: {client_info["sharepoint_url"]}')
        
        # 2. Get job folder name from Airtable
        project_info = airtable.get_project_folder(job_number)
        if not project_info:
            # Fallback: use job number as folder prefix
            job_folder_name = job_number
            print(f'No project found, using job number as folder: {job_folder_name}')
        else:
            job_folder_name = project_info.get('folder_name', job_number)
            print(f'Job folder: {job_folder_name}')
        
        # 3. Classify where files should go
        classification = classifier.classify_filing(
            sender_email=sender_email,
            all_recipients=all_recipients,
            subject_line=subject_line,
            email_content=email_content,
            attachment_names=attachment_names
        )
        
        print(f'Classification: {classification}')
        
        destination_folder = classification['folder']
        is_outgoing = classification.get('is_outgoing', False)
        
        # 4. Handle Round logic if outgoing
        round_number = None
        if is_outgoing:
            # Get current round from Airtable and increment
            current_round = project_info.get('round', 0) if project_info else 0
            round_number = current_round + 1
            destination_folder = f"-- Round {round_number}"
            print(f'Outgoing work - Round {round_number}')
        else:
            # Add -- prefix if not present
            if not destination_folder.startswith('--'):
                destination_folder = f"-- {destination_folder}"
        
        # 5. Build full destination path
        dest_path = f"/Shared Documents/{job_folder_name}/{destination_folder}"
        print(f'Destination path: {dest_path}')
        
        # 6. Build .eml filename if we have email content
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
        
        # 7. Call PA Filing
        pa_result = power_automate.call_filing(
            source_site_url=HUNCH_SITE_URL,
            source_path=INCOMING_PATH,
            source_files=attachment_names if has_attachments else [],
            dest_site_url=client_info['sharepoint_url'],
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
        
        # 8. Update Airtable
        if project_record_id:
            airtable.update_project_filing(
                record_id=project_record_id,
                round_number=round_number,
                folder_url=pa_result.get('destFolderUrl', ''),
                destination=destination_folder
            )
        
        # 9. Build response
        files_moved = pa_result.get('sourceFiles', [])
        if pa_result.get('emailSaved'):
            files_moved.append(pa_result['emailSaved'])
        
        return jsonify({
            'success': True,
            'filed': True,
            'jobNumber': job_number,
            'destination': destination_folder,
            'destPath': dest_path,
            'filesMoved': files_moved,
            'roundNumber': round_number,
            'classification': classification
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
