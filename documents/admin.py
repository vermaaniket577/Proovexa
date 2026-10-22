from django.contrib import admin
from .models import Document, ExtractedText, ReferenceSource


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'file_type', 'uploaded_by', 'status', 'word_count', 'uploaded_at']
    list_filter = ['status', 'file_type', 'is_reference']
    search_fields = ['title', 'original_filename']
    readonly_fields = ['id', 'file_hash', 'uploaded_at', 'processed_at']


@admin.register(ExtractedText)
class ExtractedTextAdmin(admin.ModelAdmin):
    list_display = ['document', 'page_number', 'paragraph_number', 'word_count']
    list_filter = ['document']


@admin.register(ReferenceSource)
class ReferenceSourceAdmin(admin.ModelAdmin):
    list_display = ['title', 'source_type', 'author', 'institution', 'is_active']
    list_filter = ['source_type', 'is_active']
    search_fields = ['title', 'author']
