# Dot File

Attachment filing service for Hunch creative agency. Receives routed requests from Dot Traffic via n8n, files attachments to the correct SharePoint location, and updates Airtable.

## Position in Ecosystem

```
Power Automate → Dot Traffic → n8n workflow → Dot File → SharePoint
```

## Endpoints

### `POST /file`
Main filing endpoint. Receives payload from n8n with email metadata and attachment info.

**Input:**
```json
{
  "jobNumber": "SKY 045",
  "clientCode": "SKY",
  "senderName": "Sarah",
  "senderEmail": "sarah@sky.co.nz",
  "subjectLine": "Re: SKY 045 - Banner feedback",
  "emailContent": "<html>...</html>",
  "attachmentNames": ["Banner_v2.pdf", "Social_amends.docx"],
  "hasAttachments": true,
  "receivedDateTime": "2026-01-17T10:30:00Z",
  "projectRecordId": "recABC123...",
  "allRecipients": ["sarah@sky.co.nz", "dot@hunch.co.nz"]
}
```

**Output:**
```json
{
  "success": true,
  "jobNumber": "SKY 045",
  "destination": "-- Feedback",
  "folderUrl": "https://hunch.sharepoint.com/...",
  "filesMoved": ["Banner_v2.pdf", "Email from Sarah - 17 Jan 2026.eml"],
  "roundNumber": null,
  "airtableUpdated": true
}
```

### `POST /test/classify`
Test classification without filing.

### `POST /test/folder`
Test SharePoint folder lookup.

### `GET /`
Health check.

## Folder Structure

Each job folder in SharePoint gets these subfolders:
```
/SKY 045 - Job Name/
├── -- Briefs/       ← Initial brief, scope, requirements
├── -- Feedback/     ← Client feedback, amends, comments
├── -- Round 1/      ← Outgoing deliverables (version 1)
├── -- Round 2/      ← Outgoing deliverables (version 2)
└── -- Other/        ← Everything else
```

## Classification Logic

**Outgoing work (→ Round X)** - needs 3+ signals:
- Sender is @hunch.co.nz
- Recipient includes external (client) email
- Filename contains job number
- File type: .pdf, .docx, .pptx
- Email language: "here's the latest", "for your review"

**Otherwise:**
| Signal | Folder |
|--------|--------|
| "brief", "scope", "requirements" | -- Briefs |
| "feedback", "amends", "comments", client sender | -- Feedback |
| Everything else | -- Other |

## Environment Variables

```bash
# Microsoft Graph API
MS_TENANT_ID=xxx
MS_CLIENT_ID=xxx
MS_CLIENT_SECRET=xxx
HUNCH_SITE_ID=xxx  # Site ID for the main Hunch SharePoint (where Incoming lives)

# Airtable
AIRTABLE_API_KEY=xxx
AIRTABLE_BASE_ID=app8CI7NAZqhQ4G1Y

# Claude
ANTHROPIC_API_KEY=xxx
```

## Airtable Requirements

### Clients table
- `Client code` - e.g., "SKY", "TOW", "ONE"
- `Sharepoint ID` - Graph API site ID for this client's SharePoint
- `Sharepoint URL` - Web URL for reference

### Projects table
- `Job Number` - e.g., "SKY 045"
- `Round` - Current round number (updated by Dot File)
- `Latest Folder URL` - URL to last filed folder
- `Files Updated` - Timestamp of last filing

### Updates table (optional logging)
- `Job Number`
- `Update`
- `Source`
- `Details`

## Deployment (Railway)

1. Create new project from GitHub repo
2. Add environment variables
3. Deploy

Service will be available at `https://dot-file.up.railway.app`

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MS_TENANT_ID=xxx
export MS_CLIENT_ID=xxx
# ... etc

# Run
python app.py
```

## Flow

1. n8n calls `/file` with email metadata
2. Look up SharePoint site ID from Airtable (client code → site)
3. Find job folder in SharePoint (prefix match on job number)
4. Claude classifies → Briefs / Feedback / Round X / Other
5. Create subfolder if needed (with `--` prefix)
6. Move files from `/-- Incoming/` to destination
7. Save email as `.eml` file
8. Update Airtable with round number and folder URL
9. Return confirmation
