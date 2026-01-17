# Dot File

Attachment filing service for Hunch. Receives requests from Traffic, classifies content, calls PA Filing.

## Position in Ecosystem

```
PA Listener → Dot Traffic → Dot File → PA Filing
   (email)      (routes)     (thinks)   (moves files)
```

## Endpoint

### `POST /file`

Receives filing request from Traffic.

**Input:**
```json
{
  "jobNumber": "SKY 045",
  "clientCode": "SKY",
  "senderName": "Sarah",
  "senderEmail": "sarah@sky.co.nz",
  "subjectLine": "Re: SKY 045 - Banner feedback",
  "emailContent": "<html>...</html>",
  "attachmentNames": ["Banner_v2.pdf"],
  "hasAttachments": true,
  "receivedDateTime": "2026-01-18T10:30:00Z",
  "projectRecordId": "recABC123",
  "allRecipients": ["sarah@sky.co.nz", "dot@hunch.co.nz"]
}
```

**Output:**
```json
{
  "success": true,
  "filed": true,
  "jobNumber": "SKY 045",
  "destination": "-- Feedback",
  "destPath": "/Shared Documents/SKY 045 - Banner Campaign/-- Feedback",
  "filesMoved": ["Banner_v2.pdf", "Email from Sarah - 18 Jan 2026.eml"],
  "roundNumber": null,
  "classification": {
    "folder": "Feedback",
    "is_outgoing": false,
    "confidence": "high",
    "reasoning": "Client sending feedback"
  }
}
```

## What It Does

1. **Receives** request from Traffic (job number, email, attachments)
2. **Looks up** client SharePoint URL (Airtable)
3. **Looks up** project folder name (Airtable)
4. **Classifies** content → Briefs / Feedback / Round X / Other (Claude)
5. **Builds** full destination path
6. **Calls** PA Filing with source + destination paths
7. **Updates** Airtable (round number, folder URL)
8. **Returns** result to Traffic

## Classification

| Signal | Destination |
|--------|-------------|
| From Hunch + delivery language + attachments | Round X (outgoing) |
| "brief", "scope", "requirements" | -- Briefs |
| "feedback", "amends" or client sender | -- Feedback |
| Everything else | -- Other |

## Environment Variables

```bash
# Power Automate
PA_FILING_URL=https://...invoke?api-version=1&sp=...

# Airtable
AIRTABLE_API_KEY=xxx
AIRTABLE_BASE_ID=app8CI7NAZqhQ4G1Y

# Claude
ANTHROPIC_API_KEY=xxx

# SharePoint (Hunch site where Incoming lives)
HUNCH_SITE_URL=https://hunch.sharepoint.com/sites/Hunch614
```

## Airtable Requirements

### Clients table
- `Client code` - e.g., "SKY"
- `Sharepoint URL` - e.g., "https://hunch.sharepoint.com/sites/SKY"

### Projects table
- `Job Number` - e.g., "SKY 045"
- `Project Name` - e.g., "Banner Campaign"
- `Round` - Current round number
- `Latest Folder URL` - Updated by Dot File
- `Files Updated` - Timestamp
- `Last Filed To` - e.g., "-- Feedback"

## Deployment

1. Push to GitHub
2. Create Railway project from repo
3. Add environment variables
4. Deploy

Service URL: `https://dot-file.up.railway.app`
