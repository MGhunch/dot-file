"""
Dot File - Attachment Filing Service
Receives routed requests from Traffic via n8n, files attachments 
to correct SharePoint location, updates Airtable.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime

import sharepoint
import classifier
import airtable

app = Flask(__name__)
CORS(app)


@app.route('/')
def health():
    return jsonify({'status': 'ok', 'service': 'dot-file'})


@app.route('/file', methods=['POST'])
def file_attachments():
    """
    Main endpoint - receives filing request from n8n
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
        
        print(f'Filing request: {job_number} from {sender_email}')
        print(f'Attachments: {attachment_names}')
        
        if not job_number or not client_code:
            return jsonify({'error': 'Missing jobNumber or clientCode'}), 400
        
        # 1. Get SharePoint site info from Airtable
        site_info = airtable.get_sharepoint_site(client_code)
        if not site_info:
            return jsonify({'error': f'No SharePoint site found for {client_code}'}), 404
        
        print(f'SharePoint site: {site_info["site_id"]}')
        
        # 2. Find job folder in SharePoint
        job_folder = sharepoint.find_job_folder(site_info['site_id'], job_number)
        if not job_folder:
            return jsonify({'error': f'No folder found for {job_number}'}), 404
        
        print(f'Job folder: {job_folder["name"]}')
        
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
            round_number = sharepoint.get_next_round_number(site_info['site_id'], job_folder['id'])
            destination_folder = f"-- Round {round_number}"
            print(f'Outgoing work - creating {destination_folder}')
        
        # 5. Ensure destination subfolder exists
        dest_folder_id = sharepoint.ensure_subfolder(
            site_info['site_id'], 
            job_folder['id'], 
            destination_folder
        )
        
        print(f'Destination folder ID: {dest_folder_id}')
        
        # 6. Move files from Incoming to destination
        moved_files = []
        if has_attachments and attachment_names:
            moved_files = sharepoint.move_files_from_incoming(
                dest_site_id=site_info['site_id'],
                dest_folder_id=dest_folder_id,
                filenames=attachment_names
            )
            print(f'Moved files: {moved_files}')
        
        # 7. Save email as .eml
        if email_content:
            eml_filename = create_eml_filename(sender_name, received_datetime)
            success = sharepoint.save_email_as_eml(
                site_id=site_info['site_id'],
                folder_id=dest_folder_id,
                filename=eml_filename,
                sender_name=sender_name,
                sender_email=sender_email,
                recipients=all_recipients,
                subject=subject_line,
                html_content=email_content,
                received_datetime=received_datetime
            )
            if success:
                moved_files.append(eml_filename)
                print(f'Saved email as: {eml_filename}')
        
        # 8. Get folder URL
        folder_url = sharepoint.get_folder_url(site_info['site_id'], dest_folder_id)
        
        # 9. Update Airtable
        airtable_updated = False
        if project_record_id:
            airtable_updated = airtable.update_project_filing(
                record_id=project_record_id,
                round_number=round_number,
                folder_url=folder_url
            )
        
        # 10. Log activity
        airtable.log_filing_activity(
            job_number=job_number,
            destination=destination_folder,
            files_moved=moved_files,
            success=True
        )
        
        return jsonify({
            'success': True,
            'jobNumber': job_number,
            'destination': destination_folder,
            'folderUrl': folder_url,
            'filesMoved': moved_files,
            'roundNumber': round_number,
            'airtableUpdated': airtable_updated,
            'classification': classification
        })
        
    except Exception as e:
        print(f'Error in /file: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/test/classify', methods=['POST'])
def test_classify():
    """
    Test endpoint - just run classification without filing
    """
    try:
        data = request.get_json()
        
        classification = classifier.classify_filing(
            sender_email=data.get('senderEmail', ''),
            all_recipients=data.get('allRecipients', []),
            subject_line=data.get('subjectLine', ''),
            email_content=data.get('emailContent', ''),
            attachment_names=data.get('attachmentNames', [])
        )
        
        return jsonify(classification)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/test/folder', methods=['POST'])
def test_folder():
    """
    Test endpoint - check if we can find a job folder
    """
    try:
        data = request.get_json()
        job_number = data.get('jobNumber')
        client_code = data.get('clientCode')
        
        if not job_number or not client_code:
            return jsonify({'error': 'Missing jobNumber or clientCode'}), 400
        
        site_info = airtable.get_sharepoint_site(client_code)
        if not site_info:
            return jsonify({'error': f'No SharePoint site for {client_code}'}), 404
        
        job_folder = sharepoint.find_job_folder(site_info['site_id'], job_number)
        if not job_folder:
            return jsonify({'error': f'No folder found for {job_number}'}), 404
        
        subfolders = sharepoint.get_subfolders(site_info['site_id'], job_folder['id'])
        
        return jsonify({
            'siteId': site_info['site_id'],
            'jobFolder': job_folder,
            'subfolders': [f['name'] for f in subfolders]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def create_eml_filename(sender_name, received_datetime):
    """Create filename like 'Email from Sarah - 17 Jan 2026.eml'"""
    try:
        dt = datetime.fromisoformat(received_datetime.replace('Z', '+00:00'))
        date_str = dt.strftime('%d %b %Y')
    except:
        date_str = datetime.now().strftime('%d %b %Y')
    
    # Get first name, clean up
    clean_name = sender_name.split()[0] if sender_name else 'Unknown'
    # Remove any problematic characters for filenames
    clean_name = ''.join(c for c in clean_name if c.isalnum() or c in ' -_')
    
    return f"Email from {clean_name} - {date_str}.eml"


if __name__ == '__main__':
    app.run(debug=True, port=5001)
