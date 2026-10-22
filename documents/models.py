"""
Document and text extraction models.
"""
import uuid
import hashlib
from django.db import models
from django.conf import settings


class Document(models.Model):
    """Uploaded document for plagiarism checking."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        EXTRACTING = 'extracting', 'Extracting Text'
        EXTRACTED = 'extracted', 'Text Extracted'
        ANALYZING = 'analyzing', 'Analyzing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    class FileType(models.TextChoices):
        PDF = 'pdf', 'PDF'
        DOCX = 'docx', 'DOCX'
        TXT = 'txt', 'TXT'
        PPTX = 'pptx', 'PPTX'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=500)
    file = models.FileField(upload_to='documents/%Y/%m/')
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    file_hash = models.CharField(max_length=64, blank=True, db_index=True,
                                  help_text="SHA-256 hash for deduplication")
    mime_type = models.CharField(max_length=100, blank=True)
    page_count = models.IntegerField(default=0)
    word_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)

    # Relationships
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='documents'
    )
    assignment = models.ForeignKey(
        'accounts.Assignment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='documents'
    )
    is_reference = models.BooleanField(
        default=False,
        help_text="Whether this is a reference document in the institution's collection"
    )

    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Retention
    retention_until = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['uploaded_by', '-uploaded_at']),
            models.Index(fields=['status']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['assignment']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_file_type_display()})"

    def compute_hash(self):
        """Compute SHA-256 hash of the file."""
        sha256 = hashlib.sha256()
        self.file.seek(0)
        for chunk in self.file.chunks(8192):
            sha256.update(chunk)
        self.file.seek(0)
        self.file_hash = sha256.hexdigest()
        return self.file_hash

    @property
    def file_size_display(self):
        """Human-readable file size."""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class ExtractedText(models.Model):
    """Extracted text content from a document, organized by page/section."""
    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='extracted_texts'
    )
    page_number = models.IntegerField(default=1)
    paragraph_number = models.IntegerField(default=1)
    content = models.TextField()
    word_count = models.IntegerField(default=0)
    char_start = models.IntegerField(default=0, help_text="Character offset start in full text")
    char_end = models.IntegerField(default=0, help_text="Character offset end in full text")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document', 'page_number', 'paragraph_number']
        indexes = [
            models.Index(fields=['document', 'page_number']),
        ]

    def __str__(self):
        return f"Page {self.page_number}, Para {self.paragraph_number} of {self.document.title}"


class ReferenceSource(models.Model):
    """External or internal reference source for comparison."""

    class SourceType(models.TextChoices):
        UPLOADED = 'uploaded', 'Uploaded Document'
        INSTITUTIONAL = 'institutional', 'Institutional Collection'
        WEB = 'web', 'Web Source'
        ACADEMIC = 'academic', 'Academic Database'
        OPEN_ACCESS = 'open_access', 'Open Access Repository'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=500, blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    url = models.URLField(max_length=1000, blank=True)
    doi = models.CharField(max_length=100, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    retrieved_text = models.TextField(blank=True)
    word_count = models.IntegerField(default=0)
    retrieval_timestamp = models.DateTimeField(null=True, blank=True)
    access_limitations = models.TextField(blank=True)

    # Link to uploaded document if source is internal
    document = models.ForeignKey(
        Document, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='as_reference'
    )
    institution = models.ForeignKey(
        'accounts.Institution', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reference_sources'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        indexes = [
            models.Index(fields=['source_type']),
            models.Index(fields=['institution']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_source_type_display()})"
