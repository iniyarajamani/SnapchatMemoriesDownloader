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

try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

JSON_FILE = "INSERT_PATH_TO_JSON_FILE"
OUTPUT_DIR = "INSERT_PATH_TO_OUTPUT_DIRECTORY"
START_DATE = None  # "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
END_DATE = None    # "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"

MAX_DOWNLOAD_RETRIES = 3
MAX_METADATA_RETRIES = 3
ADD_OVERLAYS = True

os.makedirs(OUTPUT_DIR, exist_ok=True)

if not HAS_PIEXIF:
    print("⚠️  WARNING: piexif is not installed! Install with: pip3 install piexif")
    print("-" * 60)

if ADD_OVERLAYS and not HAS_PIL:
    print("⚠️  WARNING: PIL/Pillow is not installed! Install with: pip3 install Pillow")
    print("-" * 60)

with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

media_items = data.get("Saved Media", [])

def extract_media_from_zip(zip_path, output_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            media_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v')
            
            media_files = []
            overlay_files = []
            for f in file_list:
                if f.endswith('/'):
                    continue
                filename_lower = os.path.basename(f).lower()
                
                if ADD_OVERLAYS and 'overlay' in filename_lower and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                    overlay_files.append(f)
                
                if 'overlay' in filename_lower:
                    continue
                    
                if f.lower().endswith(media_extensions):
                    media_files.append(f)
            
            if not media_files:
                return False, "No media file found in ZIP"
            
            main_files = [f for f in media_files if 'main' in os.path.basename(f).lower()]
            if main_files:
                media_file = max(main_files, key=lambda f: zip_ref.getinfo(f).file_size)
            else:
                media_file = max(media_files, key=lambda f: zip_ref.getinfo(f).file_size)
            
            temp_dir = tempfile.mkdtemp()
            overlay_path = None
            try:
                zip_ref.extract(media_file, temp_dir)
                extracted_path = os.path.join(temp_dir, media_file)
                
                if ADD_OVERLAYS and overlay_files:
                    overlay_file = max(overlay_files, key=lambda f: zip_ref.getinfo(f).file_size) if len(overlay_files) > 1 else overlay_files[0]
                    zip_ref.extract(overlay_file, temp_dir)
                    overlay_path = os.path.join(temp_dir, overlay_file)
                
                if ADD_OVERLAYS and overlay_path and os.path.exists(overlay_path):
                    ext = os.path.splitext(output_path)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png']:
                        success, error = composite_overlay_on_image(extracted_path, overlay_path)
                        if success:
                            print("🎨 Overlay composited (image)", end=" ", flush=True)
                
                if os.path.exists(output_path):
                    os.remove(output_path)
                shutil.move(extracted_path, output_path)
                
                return True, output_path
            finally:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
    except Exception as e:
        return False, f"ZIP extraction error: {str(e)}"

def download_file(url, filepath, max_retries=MAX_DOWNLOAD_RETRIES):
    use_post = False
    
    for attempt in range(1, max_retries + 1):
        try:
            if use_post:
                parts = url.split('?', 1)
                post_data = parts[1].encode() if len(parts) > 1 else b''
                req = urllib.request.Request(parts[0], data=post_data)
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            else:
                req = urllib.request.Request(url)
                req.add_header('X-Snap-Route-Tag', 'mem-dmd')
            
            req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
            
            temp_filepath = filepath + '.tmp'
            with urllib.request.urlopen(req, timeout=90) as response:
                with open(temp_filepath, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            
            try:
                with zipfile.ZipFile(temp_filepath, 'r') as zf:
                    success_extract, result = extract_media_from_zip(temp_filepath, filepath)
                    os.remove(temp_filepath)
                    if success_extract:
                        return True
                    elif attempt < max_retries:
                        continue
                    else:
                        return False, result
            except (zipfile.BadZipFile, zipfile.LargeZipFile):
                if os.path.exists(filepath):
                    os.remove(filepath)
                shutil.move(temp_filepath, filepath)
                return True
            
        except urllib.error.HTTPError as e:
            if ("GET is not supported" in str(e) or e.code == 405) and not use_post:
                use_post = True
                continue
            if attempt < max_retries:
                continue
            return False, str(e)
        except Exception as e:
            if ("GET is not supported" in str(e) or "HTTP method GET" in str(e)) and not use_post:
                use_post = True
                continue
            if attempt < max_retries:
                continue
            return False, str(e)
    
    return False, "All attempts failed"

def parse_location(location_str):
    if not location_str:
        return None, None
    
    match = re.search(r'Latitude, Longitude:\s*([-\d.]+),\s*([-\d.]+)', location_str)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except:
            pass
    
    return None, None

def decimal_to_dms(decimal):
    degrees = int(abs(decimal))
    minutes_float = (abs(decimal) - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    return (degrees, minutes, int(seconds * 100))

def add_exif_metadata(image_path, date_str, lat=None, lon=None):
    if not HAS_PIEXIF:
        return False, "piexif not installed"
    
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
        date_formatted = dt.strftime("%Y:%m:%d %H:%M:%S")
        
        try:
            exif_dict = piexif.load(image_path)
        except:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
        
        exif_dict["0th"][piexif.ImageIFD.DateTime] = date_formatted
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_formatted
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_formatted
        
        if lat is not None and lon is not None:
            lat_dms = decimal_to_dms(lat)
            lon_dms = decimal_to_dms(lon)
            
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = ((lat_dms[0], 1), (lat_dms[1], 1), (lat_dms[2], 100))
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = ((lon_dms[0], 1), (lon_dms[1], 1), (lon_dms[2], 100))
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
        
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, image_path)
        return True, None
    except Exception as e:
        return False, str(e)

def composite_overlay_on_image(image_path, overlay_path):
    if not HAS_PIL:
        return False, "PIL/Pillow not installed"
    
    try:
        main_img = Image.open(image_path)
        overlay_img = Image.open(overlay_path)
        
        if overlay_img.mode != 'RGBA':
            overlay_img = overlay_img.convert('RGBA')
        
        if overlay_img.size != main_img.size:
            overlay_img = overlay_img.resize(main_img.size, Image.Resampling.LANCZOS)
        
        if main_img.mode != 'RGBA':
            main_img = main_img.convert('RGBA')
        
        composite = Image.alpha_composite(main_img, overlay_img)
        
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            rgb_composite = Image.new('RGB', composite.size, (255, 255, 255))
            rgb_composite.paste(composite, mask=composite.split()[3] if composite.mode == 'RGBA' else None)
            composite = rgb_composite
        
        composite.save(image_path, quality=95)
        return True, None
    except Exception as e:
        return False, str(e)

def add_video_metadata(video_path, date_str, lat=None, lon=None):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
        date_formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
        temp_path = video_path + '.tmp'
        
        cmd = ['ffmpeg', '-i', video_path, '-c', 'copy']
        cmd.extend(['-metadata', f'creation_time={date_formatted}'])
        cmd.extend(['-metadata', f'date={date_formatted}'])
        
        if lat is not None and lon is not None:
            cmd.extend(['-metadata', f'location={lat},{lon}'])
            cmd.extend(['-metadata', f'location-eng={lat},{lon}'])
        
        cmd.extend(['-f', 'mp4', '-y', temp_path])
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(temp_path):
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
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return False, str(e)

def embed_metadata(filepath, date_str, location_str, media_type, max_retries=MAX_METADATA_RETRIES):
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
    
    return False, error

used_filenames = set(os.listdir(OUTPUT_DIR))

def find_duplicate_by_size_and_date(filepath, date_str):
    if not os.path.exists(filepath):
        return None
    
    file_size = os.path.getsize(filepath)
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    date_pattern = dt.strftime("%Y-%m-%d_%H-%M-%S")
    
    for existing_file in os.listdir(OUTPUT_DIR):
        if existing_file.startswith('.'):
            continue
        
        existing_path = os.path.join(OUTPUT_DIR, existing_file)
        if not os.path.isfile(existing_path):
            continue
        
        if existing_file.startswith(date_pattern) and os.path.getsize(existing_path) == file_size:
            if existing_path != filepath:
                return existing_path
    
    return None

start_datetime = None
end_datetime = None

if START_DATE:
    try:
        try:
            start_datetime = datetime.strptime(START_DATE, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            start_datetime = datetime.strptime(START_DATE, "%Y-%m-%d")
        print(f"📅 Start date filter: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    except ValueError:
        print(f"⚠️  WARNING: Invalid START_DATE format: {START_DATE}")
        print("   Expected format: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")

if END_DATE:
    try:
        try:
            end_datetime = datetime.strptime(END_DATE, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            end_datetime = datetime.strptime(END_DATE, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        print(f"📅 End date filter: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    except ValueError:
        print(f"⚠️  WARNING: Invalid END_DATE format: {END_DATE}")
        print("   Expected format: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")

if start_datetime and end_datetime and start_datetime.date() == end_datetime.date():
    print(f"📌 Filtering for single day: {start_datetime.date()}")

items_to_process = []
for item in media_items:
    if not item.get("Date") or not item.get("Media Download Url"):
        continue
    
    try:
        item_date_str = item.get("Date")
        item_datetime = datetime.strptime(item_date_str, "%Y-%m-%d %H:%M:%S UTC")
        item_date = item_datetime.date()
        
        if start_datetime:
            start_date = start_datetime.date()
            if start_datetime.hour == 0 and start_datetime.minute == 0 and start_datetime.second == 0:
                if item_date < start_date:
                    continue
            else:
                if item_datetime < start_datetime:
                    continue
        
        if end_datetime:
            end_date = end_datetime.date()
            if end_datetime.hour == 23 and end_datetime.minute == 59 and end_datetime.second == 59:
                if item_date > end_date:
                    continue
            else:
                if item_datetime > end_datetime:
                    continue
        
        items_to_process.append(item)
    except ValueError:
        continue

total_items = len(items_to_process)
total_available = len([item for item in media_items if item.get("Date") and item.get("Media Download Url")])

if start_datetime or end_datetime:
    print(f"📊 Filtered {total_items} file(s) from {total_available} available")
    if total_items == 0 and total_available > 0:
        sample_item = next((item for item in media_items if item.get("Date") and item.get("Media Download Url")), None)
        if sample_item:
            sample_date = datetime.strptime(sample_item.get("Date"), "%Y-%m-%d %H:%M:%S UTC")
            print(f"   Sample date in data: {sample_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

print(f"Downloading and embedding metadata for {total_items} file(s)...")
print("-" * 60)

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
    
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S UTC")
    base = dt.strftime("%Y-%m-%d_%H-%M-%S")
    url_hash = hashlib.md5(primary_url.encode()).hexdigest()[:8]
    filename = f"{base}_{url_hash}{ext}"
    
    counter = 1
    while filename in used_filenames or os.path.exists(os.path.join(OUTPUT_DIR, filename)):
        filename = f"{base}_{url_hash}_{counter}{ext}"
        counter += 1
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    if os.path.exists(filepath):
        skipped += 1
        print(f"[{idx}/{total_items}] {filename} (exists, embedding metadata)...", end=" ", flush=True)
        success, error = embed_metadata(filepath, date_str, location_str, media_type)
        if success:
            print("✅")
            metadata_embedded += 1
        else:
            print(f"⚠️  Metadata failed: {error}")
        continue

    print(f"[{idx}/{total_items}] Downloading {filename}...", end=" ", flush=True)

    download_success = False
    last_error = None
    
    for url in [primary_url, alternate_url]:
        if not url or download_success:
            continue
        
        result = download_file(url, filepath, max_retries=MAX_DOWNLOAD_RETRIES)
        if result is True:
            duplicate_file = find_duplicate_by_size_and_date(filepath, date_str)
            if duplicate_file:
                os.remove(filepath)
                filepath = duplicate_file
                filename = os.path.basename(duplicate_file)
                duplicates_found += 1
                print(f" (duplicate found: {os.path.basename(duplicate_file)})", end="", flush=True)
            
            used_filenames.add(filename)
            download_success = True
            break
        else:
            last_error = result[1] if isinstance(result, tuple) else str(result)
    
    if not download_success:
        error_msg = last_error or "All URLs failed"
        print(f"❌ Download failed: {error_msg}")
        failed_download += 1
        continue
    
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

