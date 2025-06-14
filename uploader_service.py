from flask import Flask, request, jsonify
from PIL import Image, ExifTags
import io
import os
from google.cloud import storage
import uuid

app = Flask(__name__)

# Configuration
LOGO_PATH = 'nobroker_logo.png'  # Path to NoBroker logo
BUCKET_NAME = 'your-gcs-bucket'  # Replace with your Google Cloud Storage bucket name
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Initialize Google Cloud Storage client
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Check if file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Correct image orientation based on EXIF data
def correct_orientation(image):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = image._getexif()
        if exif is not None:
            orientation = exif.get(orientation)
            if orientation == 3:
                image = image.rotate(180, expand=True)
            elif orientation == 6:
                image = image.rotate(270, expand=True)
            elif orientation == 8:
                image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, IndexError):
        pass  # No EXIF data or error, return original image
    return image

# Adjust aspect ratio to a target (e.g., 4:3)
def adjust_aspect_ratio(image, target_ratio=4/3):
    width, height = image.size
    current_ratio = width / height
    if abs(current_ratio - target_ratio) > 0.01:  # Allow small tolerance
        if current_ratio > target_ratio:
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            image = image.crop((left, 0, left + new_width, height))
        else:
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            image = image.crop((0, top, width, top + new_height))
    return image

# Add NoBroker logo to the bottom-right corner
def add_logo(image, logo_path):
    logo = Image.open(logo_path).convert('RGBA')
    logo = logo.resize((int(image.width * 0.2), int(image.height * 0.2)))  # Scale logo to 20% of image size
    image = image.convert('RGBA')
    logo_width, logo_height = logo.size
    position = (image.width - logo_width - 10, image.height - logo_height - 10)  # 10px padding
    image.paste(logo, position, logo)  # Use logo's alpha channel as mask
    return image.convert('RGB')  # Convert back to RGB for saving

# Compress image to reduce file size
def compress_image(image, quality=85):
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    return Image.open(output)

# Upload image to Google Cloud Storage
def upload_to_gcs(image, filename):
    output = io.BytesIO()
    image.save(output, format='JPEG')
    output.seek(0)
    blob = bucket.blob(f'uploads/{filename}')
    blob.upload_from_file(output, content_type='image/jpeg')
    return blob.public_url

# Flask route for image upload and processing
@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file and allowed_file(file.filename):
        try:
            # Load image
            image = Image.open(file)
            # Process image
            image = correct_orientation(image)
            image = adjust_aspect_ratio(image)
            image = add_logo(image, LOGO_PATH)
            image = compress_image(image)
            # Generate unique filename
            filename = f"{uuid.uuid4()}.jpg"
            # Upload to GCS
            public_url = upload_to_gcs(image, filename)
            return jsonify({'message': 'Image processed and uploaded', 'url': public_url}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Invalid file format'}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
