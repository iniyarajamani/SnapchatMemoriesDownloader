import json
import os
import urllib.request
import urllib.error
import hashlib
import zipfile
import tempfile
import shutil
import subprocess
import re
from datetime import datetime

# Try to import piexif for EXIF embedding
try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

JSON_FILE = "/Users/iniya/Downloads/mydata~1766461823337/json/memories_history.json"
OUTPUT_DIR = "/Users/iniya/Downloads/SnapchatMemories_test"

# Resume from this filename (set to None to start from beginning)
RESUME_FROM = None
MAX_DOWNLOAD_RETRIES = 3
MAX_METADATA_RETRIES = 3

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Check for required dependencies at startup
if not HAS_PIEXIF:
    print("⚠️  WARNING: piexif is not installed!")
    print("   Image metadata embedding will fail for all images.")
    print("   Install with: pip3 install piexif")
    print("-" * 60)

with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

media_items = data.get("Saved Media", [])

def build_filename(date_str, url, ext):
    """Build filename using date and URL hash to ensure uniqueness."""
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    base = dt.strftime("%Y-%m-%d_%H-%M-%S")
    
    # Create a short hash from the URL to differentiate files with same timestamp
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{base}_{url_hash}{ext}"

    # If file exists, it's the same media (same URL), so skip it
    # Otherwise, if hash collision, add counter
    counter = 1
    while os.path.exists(os.path.join(OUTPUT_DIR, filename)):
        filename = f"{base}_{url_hash}_{counter}{ext}"
        counter += 1

    return filename

def extract_media_from_zip(zip_path, output_path):
    """Extract media file from ZIP, discarding caption files."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Find media files (images/videos) and exclude caption/text files
            media_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v')
            
            # Filter out directories and overlay/caption files
            media_files = []
            for f in file_list:
                if f.endswith('/'):
                    continue
                filename_lower = os.path.basename(f).lower()
                # Skip overlay/caption files
                if 'overlay' in filename_lower:
                    continue
                # Check if it's a media file
                if f.lower().endswith(media_extensions):
                    media_files.append(f)
            
            if not media_files:
                return False, "No media file found in ZIP"
            
            # Prefer file with "main" in the name
            main_files = [f for f in media_files if 'main' in os.path.basename(f).lower()]
            if main_files:
                # If multiple main files, pick the largest
                media_file = max(main_files, key=lambda f: zip_ref.getinfo(f).file_size)
            else:
                # Fallback: get the largest media file
                media_file = max(media_files, key=lambda f: zip_ref.getinfo(f).file_size)
            
            # Extract to temp location first
            temp_dir = tempfile.mkdtemp()
            try:
                zip_ref.extract(media_file, temp_dir)
                extracted_path = os.path.join(temp_dir, media_file)
                
                # Move to final location
                if os.path.exists(output_path):
                    os.remove(output_path)
                shutil.move(extracted_path, output_path)
                
                return True, output_path
            finally:
                # Clean up temp directory
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
    except zipfile.BadZipFile:
        return False, "Invalid ZIP file"
    except Exception as e:
        return False, f"ZIP extraction error: {str(e)}"

def download_file(url, filepath, max_retries=MAX_DOWNLOAD_RETRIES):
    """Download file with retry logic, handles GET/POST and ZIP extraction."""
    use_post = False  # Try GET first, then POST if needed
    
    for attempt in range(1, max_retries + 1):
        try:
            # Try GET first, then POST if GET fails
            if use_post:
                # POST request: split URL and send query string as POST data
                parts = url.split('?', 1)
                post_data = parts[1].encode() if len(parts) > 1 else b''
                req = urllib.request.Request(parts[0], data=post_data)
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            else:
                # GET request
                req = urllib.request.Request(url)
                req.add_header('X-Snap-Route-Tag', 'mem-dmd')
            
            req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
            
            # Download to temp file first
            temp_filepath = filepath + '.tmp'
            with urllib.request.urlopen(req, timeout=90) as response:
                with open(temp_filepath, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            
            # Check if downloaded file is a ZIP
            try:
                with zipfile.ZipFile(temp_filepath, 'r') as zf:
                    # It's a ZIP, extract media
                    success_extract, result = extract_media_from_zip(temp_filepath, filepath)
                    os.remove(temp_filepath)  # Remove temp ZIP
                    if success_extract:
                        return True
                    else:
                        if attempt < max_retries:
                            continue  # Try again
                        else:
                            return False, result
            except (zipfile.BadZipFile, zipfile.LargeZipFile):
                # Not a ZIP, move temp file to final location
                if os.path.exists(filepath):
                    os.remove(filepath)
                shutil.move(temp_filepath, filepath)
                return True
            
        except urllib.error.HTTPError as e:
            # If GET method not supported, try POST on next attempt
            if "GET is not supported" in str(e) or e.code == 405:
                if not use_post:
                    use_post = True
                    continue  # Retry immediately with POST
            
            if attempt < max_retries:
                continue  # Try again immediately
            else:
                return False, str(e)
        except Exception as e:
            # If GET method not supported, try POST on next attempt
            if "GET is not supported" in str(e) or "HTTP method GET" in str(e):
                if not use_post:
                    use_post = True
                    continue  # Retry immediately with POST
            
            if attempt < max_retries:
                continue  # Try again immediately
            else:
                return False, str(e)
    
    return False, "All attempts failed"

def parse_location(location_str):
    """Parse location string like 'Latitude, Longitude: 40.420906, -74.528625'"""
    if not location_str:
        return None, None
    
    # Extract lat/lon from string
    match = re.search(r'Latitude, Longitude:\s*([-\d.]+),\s*([-\d.]+)', location_str)
    if match:
        try:
            lat = float(match.group(1))
            lon = float(match.group(2))
            return lat, lon
        except:
            pass
    
    return None, None

def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds"""
    degrees = int(abs(decimal))
    minutes_float = (abs(decimal) - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    
    return (degrees, minutes, int(seconds * 100))

def add_exif_metadata(image_path, date_str, lat=None, lon=None):
    """Add EXIF metadata to image file."""
    if not HAS_PIEXIF:
        return False, "piexif not installed"
    
    try:
        # Parse date
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
        date_formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
        
        # Load existing EXIF or create new
        try:
            exif_dict = piexif.load(image_path)
        except:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
        
        # Set date/time
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_formatted
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_formatted
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_formatted
        
        # Set GPS if available
        if lat is not None and lon is not None:
            # Convert to DMS
            lat_dms = decimal_to_dms(lat)
            lon_dms = decimal_to_dms(lon)
            
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = ((lat_dms[0], 1), (lat_dms[1], 1), (lat_dms[2], 100))
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = ((lon_dms[0], 1), (lon_dms[1], 1), (lon_dms[2], 100))
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
        
        # Embed EXIF
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, image_path)
        
        return True, None
    except Exception as e:
        return False, str(e)

def add_video_metadata(video_path, date_str, lat=None, lon=None):
    """Add metadata to video file using ffmpeg."""
    try:
        # Parse date
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
        date_formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create temp output file
        temp_path = video_path + '.tmp'
        
        # Build ffmpeg command
        cmd = ['ffmpeg', '-i', video_path, '-c', 'copy']
        
        # Add date metadata
        cmd.extend(['-metadata', f'creation_time={date_formatted}'])
        cmd.extend(['-metadata', f'date={date_formatted}'])
        
        # Add location metadata if available
        if lat is not None and lon is not None:
            cmd.extend(['-metadata', f'location={lat},{lon}'])
            cmd.extend(['-metadata', f'location-eng={lat},{lon}'])
        
        cmd.extend(['-f', 'mp4', '-y', temp_path])
        
        # Run ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(temp_path):
            # Replace original with temp file
            shutil.move(temp_path, video_path)
            return True, None
        else:
            error = result.stderr or result.stdout or "Unknown error"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, error
    except FileNotFoundError:
        return False, "ffmpeg not found"
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False, str(e)

def embed_metadata(filepath, date_str, location_str, media_type, max_retries=MAX_METADATA_RETRIES):
    """Embed metadata into file with retry logic."""
    lat, lon = parse_location(location_str)
    ext = os.path.splitext(filepath)[1].lower()
    
    for attempt in range(1, max_retries + 1):
        if ext in ['.jpg', '.jpeg']:
            success, error = add_exif_metadata(filepath, date_str, lat, lon)
        elif ext == '.mp4':
            success, error = add_video_metadata(filepath, date_str, lat, lon)
        else:
            return False, "Unsupported file type"
        
        if success:
            return True, None
        
        if attempt < max_retries:
            continue  # Retry
    
    return False, error

# Track filenames used in this session to prevent duplicates
used_filenames = set(os.listdir(OUTPUT_DIR))

def find_duplicate_by_size_and_date(filepath, date_str):
    """Check if a file with same timestamp and size already exists."""
    if not os.path.exists(filepath):
        return None
    
    file_size = os.path.getsize(filepath)
    
    # Convert date string to filename pattern: "YYYY-MM-DD HH:MM:SS UTC" -> "YYYY-MM-DD_HH-MM-SS"
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    date_pattern = dt.strftime("%Y-%m-%d_%H-%M-%S")
    
    # Check all files in output directory
    for existing_file in os.listdir(OUTPUT_DIR):
        if existing_file.startswith('.'):
            continue
        
        existing_path = os.path.join(OUTPUT_DIR, existing_file)
        if not os.path.isfile(existing_path):
            continue
        
        # Check if filename starts with same date pattern
        if existing_file.startswith(date_pattern):
            # Check if file size matches
            if os.path.getsize(existing_path) == file_size:
                # Same timestamp and size - likely duplicate content
                if existing_path != filepath:  # Don't match the file itself
                    return existing_path
    
    return None

# Find starting point if resuming
start_index = 0
if RESUME_FROM:
    for i, item in enumerate(media_items):
        date_str = item.get("Date")
        primary_url = item.get("Media Download Url")
        if not date_str or not primary_url:
            continue
        media_type = item.get("Media Type", "").lower()
        ext = ".mp4" if media_type == "video" else ".jpg"
        filename = build_filename(date_str, primary_url, ext)
        if RESUME_FROM in filename or filename == RESUME_FROM:
            start_index = i
            print(f"Resuming from: {filename} (item {i+1}/{len(media_items)})")
            print("-" * 60)
            break

# Filter items to process
items_to_process = [item for item in media_items[start_index:] if item.get("Date") and item.get("Media Download Url")]
total_items = len(items_to_process)

print(f"Downloading and embedding metadata for {total_items} file(s)...")
print("-" * 60)

# Download files in order
downloaded = 0
skipped = 0
duplicates_found = 0
failed_download = 0
failed_metadata = 0
metadata_embedded = 0

for idx, item in enumerate(items_to_process, start=1):
    media_type = item.get("Media Type", "").lower()
    ext = ".mp4" if media_type == "video" else ".jpg"
    
    date_str = item.get("Date")
    primary_url = item.get("Media Download Url")
    alternate_url = item.get("Download Link")
    location_str = item.get("Location", "")
    
    # Build filename, checking both filesystem and in-memory set
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    base = dt.strftime("%Y-%m-%d_%H-%M-%S")
    url_hash = hashlib.md5(primary_url.encode()).hexdigest()[:8]
    filename = f"{base}_{url_hash}{ext}"
    
    counter = 1
    while filename in used_filenames or os.path.exists(os.path.join(OUTPUT_DIR, filename)):
        filename = f"{base}_{url_hash}_{counter}{ext}"
        counter += 1
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Skip if file already exists on disk
    if os.path.exists(filepath):
        skipped += 1
        # Try to embed metadata if file exists but might not have metadata
        print(f"[{idx}/{total_items}] {filename} (exists, embedding metadata)...", end=" ", flush=True)
        success, error = embed_metadata(filepath, date_str, location_str, media_type)
        if success:
            print("✅")
            metadata_embedded += 1
        else:
            print(f"⚠️  Metadata failed: {error}")
        continue

    print(f"[{idx}/{total_items}] Downloading {filename}...", end=" ", flush=True)

    # Try primary URL first, then alternate if primary fails
    download_success = False
    last_error = None
    
    for url in [primary_url, alternate_url]:
        if not url:
            continue
        if download_success:
            break
        
        result = download_file(url, filepath, max_retries=MAX_DOWNLOAD_RETRIES)
        if result is True:
            # Check for duplicate content (same timestamp and file size)
            duplicate_file = find_duplicate_by_size_and_date(filepath, date_str)
            if duplicate_file:
                # Found duplicate - remove downloaded file and use existing one
                os.remove(filepath)
                filepath = duplicate_file
                filename = os.path.basename(duplicate_file)
                duplicates_found += 1
                print(f" (duplicate found: {os.path.basename(duplicate_file)})", end="", flush=True)
            
            used_filenames.add(filename)  # Track this filename to prevent duplicates
            download_success = True
            break
        else:
            # Store error message
            last_error = result[1] if isinstance(result, tuple) else str(result)
            # Continue to try alternate URL if available
    
    if not download_success:
        # Both URLs failed
        error_msg = last_error or "All URLs failed"
        print(f"❌ Download failed: {error_msg}")
        failed_download += 1
        continue
    
    # Download succeeded, now embed metadata
    print("✅ Downloaded, embedding metadata...", end=" ", flush=True)
    success, error = embed_metadata(filepath, date_str, location_str, media_type, max_retries=MAX_METADATA_RETRIES)
    if success:
        print("✅")
        downloaded += 1
        metadata_embedded += 1
    else:
        print(f"⚠️  Metadata failed: {error}")
        downloaded += 1
        failed_metadata += 1

print("-" * 60)
print(f"✅ Downloaded: {downloaded}")
print(f"⏭️  Skipped (already exists): {skipped}")
if duplicates_found > 0:
    print(f"🔄 Duplicates found (same timestamp + size): {duplicates_found}")
print(f"📝 Metadata embedded: {metadata_embedded}")
if failed_download > 0:
    print(f"❌ Download failed: {failed_download}")
if failed_metadata > 0:
    print(f"⚠️  Metadata embedding failed: {failed_metadata}")
print("Done ✅")

