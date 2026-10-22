"""
Analysis models: SimilarityReport, MatchedPassage, ExclusionRule, ProcessingJob.
"""
import uuid
from django.db import models
from django.conf import settings


class SimilarityReport(models.Model):
    """Generated similarity report for a document."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        'documents.Document', on_delete=models.CASCADE, related_name='similarity_reports'
    )
    
    # Overall results
    overall_similarity = models.FloatField(default=0.0, help_text="Overall similarity percentage (0-100)")
    total_words = models.IntegerField(default=0)
    matched_words = models.IntegerField(default=0)
    source_count = models.IntegerField(default=0, help_text="Number of matching sources found")
    
    # Match breakdown
    exact_match_count = models.IntegerField(default=0)
    phrase_match_count = models.IntegerField(default=0)
    fuzzy_match_count = models.IntegerField(default=0)
    
    # Processing info
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    engine_version = models.CharField(max_length=20, default='1.0.0')
    processing_time_seconds = models.FloatField(default=0.0)
    
    # Exclusion settings used (stored as JSON for reproducibility)
    exclusion_settings = models.JSONField(default=dict, blank=True)
    
    # Sources checked
    sources_checked = models.JSONField(default=list, blank=True,
        help_text="List of source types/names that were checked")
    
    # Limitations and disclaimer
    limitations = models.TextField(
        default="This report indicates text similarity, not definitive plagiarism. "
                "Similarity scores reflect textual overlap with checked sources only. "
                "Results should be interpreted by a qualified reviewer.",
    )
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Report for {self.document.title} - {self.overall_similarity:.1f}%"

    @property
    def similarity_color(self):
        """Return a color class based on similarity percentage."""
        if self.overall_similarity < 15:
            return 'success'  # Green - low similarity
        elif self.overall_similarity < 25:
            return 'info'     # Blue - moderate
        elif self.overall_similarity < 50:
            return 'warning'  # Yellow/Orange - concerning
        else:
            return 'danger'   # Red - high similarity


class MatchedPassage(models.Model):
    """Individual matched passage between submitted document and a source."""

    class MatchType(models.TextChoices):
        EXACT = 'exact', 'Exact Match'
        PHRASE = 'phrase', 'Phrase Match (N-gram)'
        FUZZY = 'fuzzy', 'Fuzzy Match'
        TFIDF = 'tfidf', 'Document Similarity (TF-IDF)'

    id = models.BigAutoField(primary_key=True)
    report = models.ForeignKey(
        SimilarityReport, on_delete=models.CASCADE, related_name='matched_passages'
    )
    
    # Submitted document passage
    submitted_text = models.TextField(help_text="Matched text from the submitted document")
    submitted_page = models.IntegerField(default=1)
    submitted_paragraph = models.IntegerField(default=1)
    submitted_char_start = models.IntegerField(default=0)
    submitted_char_end = models.IntegerField(default=0)
    
    # Source passage
    source = models.ForeignKey(
        'documents.ReferenceSource', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='matched_passages'
    )
    source_text = models.TextField(blank=True, help_text="Matching text from the source")
    source_page = models.IntegerField(null=True, blank=True)
    source_paragraph = models.IntegerField(null=True, blank=True)
    
    # Match details
    match_type = models.CharField(max_length=20, choices=MatchType.choices)
    similarity_score = models.FloatField(default=0.0, help_text="Similarity score for this passage (0-1)")
    word_count = models.IntegerField(default=0)
    
    # Color coding for visualization (1-based source index for coloring)
    source_index = models.IntegerField(default=0, help_text="Index for color-coding in the report")
    
    # Exclusion status
    is_excluded = models.BooleanField(default=False)
    exclusion_reason = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['submitted_page', 'submitted_char_start']
        indexes = [
            models.Index(fields=['report', 'match_type']),
            models.Index(fields=['source']),
        ]

    def __str__(self):
        return f"{self.get_match_type_display()} on page {self.submitted_page}"


class ExclusionRule(models.Model):
    """Configurable exclusion rules for similarity analysis."""

    class RuleType(models.TextChoices):
        BIBLIOGRAPHY = 'bibliography', 'Bibliography / References'
        QUOTATION = 'quotation', 'Direct Quotations'
        CITATION = 'citation', 'Formatted Citations'
        MIN_WORDS = 'min_words', 'Minimum Word Count'
        COMMON_PHRASES = 'common_phrases', 'Common Phrases'
        SPECIFIC_SOURCE = 'specific_source', 'Specific Source'
        TEXT_SECTION = 'text_section', 'Specific Text Section'
        SELF_MATCH = 'self_match', 'Self-Matching'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=30, choices=RuleType.choices)
    is_enabled = models.BooleanField(default=True)
    
    # Configuration
    min_word_count = models.IntegerField(default=5, help_text="For min_words type")
    common_phrases_list = models.TextField(blank=True, help_text="One phrase per line")
    excluded_source = models.ForeignKey(
        'documents.ReferenceSource', on_delete=models.SET_NULL,
        null=True, blank=True
    )
    
    # Scope
    institution = models.ForeignKey(
        'accounts.Institution', on_delete=models.CASCADE,
        null=True, blank=True, related_name='exclusion_rules'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='exclusion_rules'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rule_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"


class ProcessingJob(models.Model):
    """Lightweight job tracking for document processing."""

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class JobType(models.TextChoices):
        EXTRACTION = 'extraction', 'Text Extraction'
        ANALYSIS = 'analysis', 'Similarity Analysis'
        REPORT = 'report', 'Report Generation'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=20, choices=JobType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    document = models.ForeignKey(
        'documents.Document', on_delete=models.CASCADE, related_name='processing_jobs'
    )
    progress = models.IntegerField(default=0, help_text="Progress percentage 0-100")
    result_message = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='processing_jobs'
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['document']),
        ]

    def __str__(self):
        return f"{self.get_job_type_display()} - {self.document.title} ({self.get_status_display()})"


class AIReport(models.Model):
    """AI writing & content generation detection report."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        'documents.Document', on_delete=models.CASCADE, related_name='ai_reports'
    )
    overall_ai_score = models.FloatField(default=0.0, help_text="Estimated AI writing percentage (0-100)")
    ai_sentence_count = models.IntegerField(default=0)
    human_sentence_count = models.IntegerField(default=0)
    total_sentences = models.IntegerField(default=0)

    # Linguistic indicators
    perplexity_score = models.FloatField(default=0.0, help_text="Average lexical predictability")
    burstiness_score = models.FloatField(default=0.0, help_text="Sentence structure variance")

    # Sentence-level analysis data
    sentences_data = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    processing_time_seconds = models.FloatField(default=0.0)

    limitations = models.TextField(
        default="Our AI detection model reflects the probability that text was generated by an AI tool. "
                "AI writing detection is an indicator, not definitive proof of academic misconduct. "
                "Faculty should use discretion when interpreting scores.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_ai_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"AI Report for {self.document.title} - {self.overall_ai_score:.1f}% AI"

