# Snapchat Memories Downloader

A Python script to download Snapchat memories from your JSON data export and automatically embed date and location metadata into the files.

## Why?

Recently, Snapchat announced that in order to "save more than 5GB of Memories, you'll need to upgrade to one of our Memories storage plans." Which means paying $1.99/month (or more if needed).

Snapchat allows you to export your memories data, but the process has several limitations:

1. **Random Order**: When you click the button to download your memories, Snapchat downloads it in a random order, making it impossible to sort it by date (and the naming convention has no data regarding the file's data)

2. **Missing Metadata**: When you download memories through Snapchat's interface, the files don't include important metadata like:
   - The date and time the photo/video was taken
   - GPS location coordinates (where the photo/video was taken)

3. **ZIP File Handling**: Some memories are downloaded as ZIP files containing the media file plus caption/overlay files. Manually unzipping these files is annoying.
    - Also, added option to put the caption onto the media file

4. **No Duplicate Prevention**: Not sure if this is a problem with everyone, but there were duplicates in the HTML/JSON for my Snapchat memories, which takes up unecessary space.

## Features

- Downloads all memories from Snapchat JSON export (newest to oldest)
- Automatically embeds metadata (date and location) into media
- Handles ZIP files - automatically extracts media and discards caption files
- Optional overlay compositing - can merge overlay images onto image files (working on video file overlay)
- Date range filtering
- Duplicate detection

## Installation

```bash
pip3 install piexif Pillow
brew install ffmpeg
```

## Setup

1. Export your Snapchat data:
   - Log into Snapchat on desktop browser
   - Go to "My Data"
   - Select "Export your Memories" AND "Export JSON Files"

2. Edit `download_with_metadata.py`:
   ```python
   JSON_FILE = "/path/to/memories_history.json"
   OUTPUT_DIR = "/path/to/output/directory"
   START_DATE = None  # Optional: "YYYY-MM-DD" to filter by date
   END_DATE = None    # Optional: "YYYY-MM-DD" to filter by date
   ADD_OVERLAYS = False  # Set True to composite overlay images onto media
   ```

## Usage

```bash
python3 download_with_metadata.py
```

## File Naming

Files are named: `YYYY-MM-DD_HH-MM-SS_<url_hash>.<ext>`

Example: `2025-07-04_19-24-21_a8c934d6.jpg`
