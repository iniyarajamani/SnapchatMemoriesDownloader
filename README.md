# Snapchat Memories Downloader with Metadata

A Python script to download Snapchat memories from your JSON data export and automatically embed date and location metadata into the files.

## Problem Description

Snapchat allows you to export your memories data, but the process has several limitations:

1. **Random Order**: When you click the button to download your memories, Snapchat downloads it in a random order, making it impossible to sort it by date (the naming convention has no data regarding the file's data)

2. **Missing Metadata**: When you download memories through Snapchat's interface, the files don't include important metadata like:
   - The date and time the photo/video was taken
   - GPS location coordinates (where the photo/video was taken)

3. **ZIP File Handling**: Some memories are downloaded as ZIP files containing the media file plus caption/overlay files. Manually unzipping these files is annoying.

4. **No Duplicate Prevention**: Not sure if this is a problem with everyone, but there were duplicates in the HTML/JSON for my Snapchat memories, which takes up unecessary space.


## Features
- ✅ Downloads all memories from Snapchat JSON export (in order from newest to oldest)
- ✅ Automatically embeds metadata (date and location) into videos
- ✅ Handles ZIP files - automatically extracts media and discards caption files (working on a way to add overlay to the original media)
- ✅ Smart retry logic - automatically retries failed downloads and metadata embedding
- ✅ URL fallback - tries alternate download URLs if primary fails
- ✅ Unique filenames - uses date + URL hash to prevent duplicates
- ✅ Resume capability - can resume from any point if interrupted

## Prerequisites

- Python 3.6 or higher
- Snapchat JSON export file (`memories_history.json`)
- `piexif` library (for image metadata embedding)
- `ffmpeg` (for video metadata embedding)

## Installation

### 1. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

Or install individually:

```bash
pip3 install piexif
```

### 2. Install FFmpeg (for video metadata)

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use:
```bash
choco install ffmpeg
```

## How to Get Your Snapchat Data

1. Log into Snapchat on desktop browser
2. Go to "My Data"
3. Select "Export your Memories" AND "Export JSON Files"
4. Follow the steps to download the data

## Configuration

Before running the script, edit these variables in `download_with_metadata.py`:

```python
JSON_FILE = "/path/to/your/memories_history.json"
OUTPUT_DIR = "/path/to/output/directory"
RESUME_FROM = None  # Set to filename to resume from a specific file (only really needed if script stops in the middle)
```

**Example:**
```python
JSON_FILE = "/Users/iniya/Downloads/mydata~1766461823337/json/memories_history.json"
OUTPUT_DIR = "/Users/iniya/Downloads/SnapchatMemories"
```

## Usage

### Basic Usage

```bash
python3 download_with_metadata.py
```

The script will:
1. Download all memories from the JSON file
2. Automatically embed metadata (date and location) into each file
3. Show progress for each file
4. Report summary statistics at the end

### Resume from a Specific File

If the script is interrupted, you can resume from a specific file:

1. Edit `download_with_metadata.py` and set:
   ```python
   RESUME_FROM = "2025-07-04_19-24-21_abc12345.jpg"
   ```

2. Run the script again:
   ```bash
   python3 download_with_metadata.py
   ```

## File Naming Convention

Files are named with the following format:

```
YYYY-MM-DD_HH-MM-SS_<url_hash>.<ext>
```

**Examples:**
- `2025-07-04_19-24-21_a8c934d6.jpg`
- `2020-03-10_15-29-30_d435bfa6.mp4`

The URL hash ensures uniqueness even if multiple memories have the same timestamp.

## Metadata Embedding

### Images (JPG/PNG)

The script embeds EXIF metadata including:
- **Date/Time**: DateTime, DateTimeOriginal, DateTimeDigitized
- **GPS Location**: Latitude and Longitude (if available in JSON)

This metadata is preserved even if files are moved or renamed, and works with:
- Photos app (macOS/iOS)
- Google Photos
- Adobe Lightroom
- Most photo management software

### Videos (MP4)

The script embeds metadata including:
- **Creation Time**: Date and time the video was taken
- **Location**: GPS coordinates (if available in JSON)

## Features Explained

### ZIP File Handling

Some Snapchat memories are downloaded as ZIP files containing:
- The actual media file (image/video)
- Caption/overlay files (PNG images with text)

The script automatically:
- Detects ZIP files
- Extracts the main media file
- Discards caption/overlay files
- Prefers files with "main" in the filename

### Retry Logic

The script includes robust retry logic:
- **Downloads**: Retries up to 3 times per URL
- **Metadata Embedding**: Retries up to 3 times per file
- **URL Fallback**: Tries primary URL first, then alternate URL if primary fails
- **GET/POST Handling**: Automatically switches to POST if GET method fails

### Duplicate Prevention

The script prevents duplicate downloads through multiple methods:
- **URL-based**: Uses URL hashes in filenames (same URL = same hash = same filename)
- **Filesystem check**: Checks if files already exist before downloading
- **Content-based**: After downloading, checks if a file with the same timestamp and file size already exists (handles cases where different URLs point to the same content)
- **Session tracking**: Tracks filenames during the session to prevent duplicates within a single run

## Output

The script provides detailed progress information:

```
Downloading and embedding metadata for 2283 file(s)...
------------------------------------------------------------
[1/2283] Downloading 2025-07-04_19-24-21_a8c934d6.jpg... ✅ Downloaded, embedding metadata... ✅
[2/2283] Downloading 2025-07-01_18-54-58_d6ceabb7.jpg... ✅ Downloaded, embedding metadata... ✅
...
------------------------------------------------------------
✅ Downloaded: 2280
⏭️  Skipped (already exists): 3
📝 Metadata embedded: 2280
Done ✅
```

## Troubleshooting

### "piexif not installed" Warning

If you see this warning, image metadata embedding will fail:

```bash
pip3 install piexif
```

### "ffmpeg not found" Error

Videos will fail metadata embedding if ffmpeg is not installed. See [Installation](#2-install-ffmpeg-for-video-metadata) section above.

### Download Failures

If downloads fail:
1. Check your internet connection
2. Verify the JSON file path is correct
3. Check that the URLs in the JSON are still valid (Snapchat URLs may expire)
4. The script will retry automatically, but you can also run it again

### Metadata Embedding Failures

If metadata embedding fails:
- Check that `piexif` is installed for images
- Check that `ffmpeg` is installed for videos
- Some files may be corrupted - the script will log failures
- Run the script again - it will retry failed metadata embedding

### Files Not Downloading

If files are being skipped:
- They may already exist in the output directory
- Check the output directory for existing files
- The script skips existing files to avoid re-downloading

### Resume Not Working

If resume doesn't work:
- Make sure `RESUME_FROM` matches the exact filename (including extension)
- The filename should be in the format: `YYYY-MM-DD_HH-MM-SS_hash.ext`
- Check that the file exists in the output directory

## Advanced Configuration

### Adjust Retry Counts

Edit these variables in the script:

```python
MAX_DOWNLOAD_RETRIES = 3  # Number of retries for downloads
MAX_METADATA_RETRIES = 3  # Number of retries for metadata embedding
```

### Change Timeout

The download timeout is set to 90 seconds. To change it, edit the `timeout=90` parameter in the `download_file` function.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
