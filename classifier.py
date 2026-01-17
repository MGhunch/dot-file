"""
Dot File - Classification Logic
Uses Claude to determine where attachments should be filed
"""

import requests
import os
import json

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

SYSTEM_PROMPT = """You're a filing assistant for Hunch creative agency. Classify where email attachments should be filed.

## Folder Options
- **Briefs**: Initial briefs, scope documents, requirements, project kickoff materials
- **Feedback**: Client feedback, amends, comments, revision requests
- **Round X**: Outgoing deliverables from Hunch to client (versioned work)
- **Other**: Everything else (admin, invoices, misc)

## Rules

### Outgoing Work (→ Round X)
Classify as outgoing if 3+ of these signals:
- Sender is @hunch.co.nz
- Recipients include external (client) emails
- Filename contains job number (e.g., "SKY 045 - Banner v2.pdf")
- File type: .pdf, .docx, .pptx
- Email language: "here's the latest", "for your review", "updated version"

### Briefs
- Words: "brief", "scope", "requirements", "kickoff"
- Usually from client to Hunch

### Feedback
- Words: "feedback", "amends", "comments", "changes", "revision"
- Sender is client (not @hunch.co.nz)

### Other
- Doesn't fit above categories

## Response Format
Respond with ONLY valid JSON:
{
  "folder": "Briefs" | "Feedback" | "Other",
  "is_outgoing": true | false,
  "confidence": "high" | "medium" | "low",
  "reasoning": "Brief explanation"
}

If is_outgoing is true, folder will be ignored (system creates Round X).
"""


def classify_filing(sender_email, all_recipients, subject_line, email_content, attachment_names):
    """
    Use Claude to classify where files should be filed
    """
    
    if not ANTHROPIC_API_KEY:
        print('No Anthropic API key - using fallback')
        return fallback_classification(sender_email, subject_line, attachment_names)
    
    is_from_hunch = '@hunch.co.nz' in sender_email.lower()
    external_recipients = [r for r in all_recipients if '@hunch.co.nz' not in r.lower()]
    
    user_message = f"""Classify where these attachments should be filed:

**Sender**: {sender_email} {"(Hunch)" if is_from_hunch else "(Client)"}
**Recipients**: {', '.join(all_recipients)}
**External recipients**: {', '.join(external_recipients) if external_recipients else "None"}
**Subject**: {subject_line}
**Attachments**: {', '.join(attachment_names) if attachment_names else "None"}

**Email content**:
{email_content[:2000] if email_content else "No content"}
"""

    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 500,
                'system': SYSTEM_PROMPT,
                'messages': [{'role': 'user', 'content': user_message}]
            },
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        
        assistant_message = ''
        for block in result.get('content', []):
            if block.get('type') == 'text':
                assistant_message = block.get('text', '')
                break
        
        parsed = parse_json_response(assistant_message)
        
        if parsed:
            return parsed
        else:
            print(f'Failed to parse: {assistant_message}')
            return fallback_classification(sender_email, subject_line, attachment_names)
            
    except Exception as e:
        print(f'Claude error: {e}')
        return fallback_classification(sender_email, subject_line, attachment_names)


def parse_json_response(text):
    """Extract JSON from Claude's response"""
    if not text:
        return None
    
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    if '```json' in text:
        try:
            start = text.find('```json') + 7
            end = text.find('```', start)
            if end > start:
                return json.loads(text[start:end].strip())
        except:
            pass
    
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
    except:
        pass
    
    return None


def fallback_classification(sender_email, subject_line, attachment_names):
    """Rule-based fallback if Claude unavailable"""
    subject_lower = subject_line.lower()
    sender_lower = sender_email.lower()
    attachments_str = ' '.join(attachment_names).lower()
    
    is_from_hunch = '@hunch.co.nz' in sender_lower
    
    # Check for outgoing
    outgoing_signals = 0
    if is_from_hunch:
        outgoing_signals += 1
    if any(ext in attachments_str for ext in ['.pdf', '.docx', '.pptx']):
        outgoing_signals += 1
    if any(phrase in subject_lower for phrase in ['for your review', 'for review', 'attached', 'latest']):
        outgoing_signals += 1
    
    import re
    if re.search(r'[A-Z]{3}\s?\d{3}', ' '.join(attachment_names)):
        outgoing_signals += 1
    
    if outgoing_signals >= 2 and is_from_hunch:
        return {
            'folder': 'Other',
            'is_outgoing': True,
            'confidence': 'medium',
            'reasoning': 'Fallback: From Hunch with delivery signals'
        }
    
    if any(word in subject_lower for word in ['brief', 'scope', 'requirement', 'kickoff']):
        return {
            'folder': 'Briefs',
            'is_outgoing': False,
            'confidence': 'medium',
            'reasoning': 'Fallback: Brief keywords in subject'
        }
    
    if any(word in subject_lower for word in ['feedback', 'amend', 'comment', 'change', 'revision']):
        return {
            'folder': 'Feedback',
            'is_outgoing': False,
            'confidence': 'medium',
            'reasoning': 'Fallback: Feedback keywords in subject'
        }
    
    if not is_from_hunch and attachment_names:
        return {
            'folder': 'Feedback',
            'is_outgoing': False,
            'confidence': 'low',
            'reasoning': 'Fallback: Attachments from client'
        }
    
    return {
        'folder': 'Other',
        'is_outgoing': False,
        'confidence': 'low',
        'reasoning': 'Fallback: No clear signals'
    }
