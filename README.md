# The Ashy Notes YouTube Automation

Python automation for authenticating with YouTube once and uploading Shorts from a local `uploads` folder.

## Project Structure

```text
TheAshyNotes/
├── auth.py
├── config.py
├── main.py
├── uploader.py
├── requirements.txt
├── client_secret.json      # You add this locally
├── token.json              # Created after first OAuth login
├── uploads/
│   ├── video1.mp4
│   └── video1.json         # Optional metadata
└── uploaded/               # Optional archive after upload
```

## Setup

1. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Download your OAuth client secret from Google Cloud Console and save it here:

```text
E:\TheAshyNotes\client_secret.json
```

The app expects an OAuth client of type **Desktop app**.

## First Authentication

Run:

```powershell
python main.py --auth-only
```

If there are videos ready, you can also simply run `python main.py`. The first OAuth run opens a browser for Google consent and creates `token.json`. Later runs reuse `token.json` and refresh expired access tokens automatically.

## Upload Videos

Place Shorts in:

```text
E:\TheAshyNotes\uploads
```

Then run:

```powershell
python main.py
```

Upload only the first three videos:

```powershell
python main.py --limit 3
```

Move uploaded videos into `uploaded/` after a successful upload:

```powershell
python main.py --limit 3 --move-uploaded
```

## Optional Metadata

For a video named `student_story.mp4`, create `student_story.json` beside it:

```json
{
  "title": "He failed one exam, but his father still smiled #Shorts",
  "description": "A short emotional story from The Ashy Notes.\n\n#Shorts #TheAshyNotes",
  "tags": ["Shorts", "The Ashy Notes", "student life", "emotional story"],
  "privacy_status": "private",
  "made_for_kids": false
}
```

Supported `privacy_status` values are `private`, `unlisted`, and `public`.

## Future Scheduler

Scheduling is intentionally kept outside the uploader. Later, a scheduler can call:

```python
from main import upload_pending_videos

upload_pending_videos(limit=3, move_uploaded=True)
```

That keeps the current upload logic reusable for daily schedules such as 3 Shorts per day at fixed times.

## Story Video Generation

The video generation pipeline uses approved stories only. It does not generate, rewrite, or modify story text.

Folders:

```text
stories/     # Approved story .txt files
audio/       # Your manually provided music
videos/      # Optional local stock clips
downloads/   # Pexels clips downloaded by the system
output/      # Final rendered videos
logs/        # Render logs
public/      # Logo assets
```

Your logo is expected at:

```text
E:\TheAshyNotes\public\logo.png
```

It is added as a low-opacity center watermark in every rendered video.

### Story File Format

Create a file like:

```text
E:\TheAshyNotes\stories\story001.txt
```

Example:

```text
TITLE: Fees Ka Din
MOOD: Student_Struggle

Us din mere paas fees bharne ke paise nahi the...
Class ke bahar khada tha,
aur andar sab apne forms submit kar rahe the.
```

Supported moods include:

```text
sad
heartbreak
loneliness
motivation
hope
success
family
parents
friendship
student_struggle
```

`TITLE` and `MOOD` are metadata. Only the body is displayed in the video.

### Pexels Setup

Create a Pexels API key and set it in PowerShell:

```powershell
$env:PEXELS_API_KEY="your_pexels_api_key_here"
```

Or create a local `.env` file:

```text
PEXELS_API_KEY=your_pexels_api_key_here
```

`.env` is ignored by git.

### Add Music

Put your own copyright-safe music files in:

```text
E:\TheAshyNotes\audio
```

Good names help the system pick better tracks:

```text
sad_piano_01.mp3
emotional_family_01.mp3
uplifting_hope_01.mp3
```

### Render One Video

Render the first unused story from `stories/`:

```powershell
python render_story.py
```

Render a specific story:

```powershell
python render_story.py --story stories\story001.txt
```

Use local clips from `videos/` instead of Pexels:

```powershell
python render_story.py --story stories\story001.txt --use-local-videos
```

The final video is saved as:

```text
E:\TheAshyNotes\output\story001.mp4
```
