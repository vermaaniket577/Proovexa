"""
Document validation utilities.
"""
import os
import mimetypes
from django.conf import settings


# File signature (magic bytes) validation
FILE_SIGNATURES = {
    '.pdf': [b'%PDF'],
    '.docx': [b'PK\x03\x04'],  # ZIP-based format
    '.pptx': [b'PK\x03\x04'],  # ZIP-based format
    '.txt': None,  # No specific signature for text files
}


def validate_file_extension(filename):
    """Check if file extension is allowed."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        return False, f"File type '{ext}' is not supported. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
    return True, ext


def validate_file_size(file_obj):
    """Check if file size is within limits."""
    max_size = settings.MAX_UPLOAD_SIZE_BYTES
    if file_obj.size > max_size:
        max_mb = settings.MAX_UPLOAD_SIZE_MB
        actual_mb = file_obj.size / (1024 * 1024)
        return False, f"File size ({actual_mb:.1f} MB) exceeds the maximum allowed ({max_mb} MB)."
    return True, file_obj.size


def validate_mime_type(file_obj, expected_ext):
    """Validate MIME type matches expected extension."""
    content_type = file_obj.content_type
    allowed_mimes = settings.ALLOWED_MIME_TYPES.get(expected_ext, [])

    if allowed_mimes and content_type not in allowed_mimes:
        # Also check via mimetypes library
        guessed_type, _ = mimetypes.guess_type(file_obj.name)
        if guessed_type not in allowed_mimes:
            return False, f"File MIME type '{content_type}' does not match expected type for {expected_ext}."
    return True, content_type


def validate_file_signature(file_obj, expected_ext):
    """Validate file magic bytes match expected format."""
    signatures = FILE_SIGNATURES.get(expected_ext)
    if signatures is None:
        return True, "No signature check needed"

    file_obj.seek(0)
    header = file_obj.read(16)
    file_obj.seek(0)

    for sig in signatures:
        if header.startswith(sig):
            return True, "Signature valid"

    return False, f"File content does not match expected format for {expected_ext}. File may be corrupted or disguised."


def validate_document(file_obj):
    """
    Run all validations on an uploaded file.
    
    Returns:
        tuple: (is_valid, file_type, errors)
    """
    errors = []

    # Extension check
    valid, ext = validate_file_extension(file_obj.name)
    if not valid:
        return False, None, [ext]

    file_type = ext.lstrip('.')

    # Size check
    valid, msg = validate_file_size(file_obj)
    if not valid:
        errors.append(msg)

    # MIME type check
    valid, msg = validate_mime_type(file_obj, ext)
    if not valid:
        errors.append(msg)

    # Signature check
    valid, msg = validate_file_signature(file_obj, ext)
    if not valid:
        errors.append(msg)

    if errors:
        return False, file_type, errors

    return True, file_type, []
