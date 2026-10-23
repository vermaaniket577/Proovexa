from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import SimilarityReport, MatchedPassage, ExclusionRule, ProcessingJob, AIReport


@admin.register(SimilarityReport)
class SimilarityReportAdmin(admin.ModelAdmin):
    list_display = ['document', 'similarity_badge', 'source_count', 'status', 'view_report_link', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']
    search_fields = ['document__title', 'document__original_filename']

    def similarity_badge(self, obj):
        score = obj.overall_similarity
        color = "#059669" if score < 15 else "#d97706" if score < 30 else "#dc2626"
        bg = "#ecfdf5" if score < 15 else "#fffbeb" if score < 30 else "#fef2f2"
        return format_html(
            '<span style="background:{}; color:{}; border:1px solid {}; font-weight:bold; padding:2px 8px; border-radius:12px;">{}</span>',
            bg, color, color, obj.similarity_display
        )
    similarity_badge.short_description = "Similarity"

    def view_report_link(self, obj):
        view_url = reverse('reports:detail', args=[obj.id])
        pdf_url = reverse('reports:download_pdf', args=[obj.id])
        return format_html(
            '<a href="{}" target="_blank" style="margin-right:8px; font-weight:600;">View Report &rarr;</a>'
            '<a href="{}" target="_blank" style="color:#64748b;">Download PDF</a>',
            view_url, pdf_url
        )
    view_report_link.short_description = "Actions"


@admin.register(AIReport)
class AIReportAdmin(admin.ModelAdmin):
    list_display = ['document', 'overall_ai_badge', 'ai_sentence_count', 'total_sentences', 'status', 'view_report_link', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['id', 'created_at', 'updated_at']
    search_fields = ['document__title', 'document__original_filename']

    def overall_ai_badge(self, obj):
        score = obj.overall_ai_score
        color = "#059669" if score < 20 else "#d97706" if score < 50 else "#dc2626"
        bg = "#ecfdf5" if score < 20 else "#fffbeb" if score < 50 else "#fef2f2"
        score_str = f"{int(round(score))}% AI"
        return format_html(
            '<span style="background:{}; color:{}; border:1px solid {}; font-weight:bold; padding:2px 8px; border-radius:12px;">{}</span>',
            bg, color, color, score_str
        )
    overall_ai_badge.short_description = "AI Score"

    def view_report_link(self, obj):
        view_url = reverse('reports:ai_report', args=[obj.document.id])
        pdf_url = reverse('reports:download_ai_pdf', args=[obj.id])
        return format_html(
            '<a href="{}" target="_blank" style="margin-right:8px; font-weight:600; color:#0284c7;">View AI Report &rarr;</a>'
            '<a href="{}" target="_blank" style="color:#64748b;">Download PDF</a>',
            view_url, pdf_url
        )
    view_report_link.short_description = "Actions"


@admin.register(MatchedPassage)
class MatchedPassageAdmin(admin.ModelAdmin):
    list_display = ['report', 'match_type', 'similarity_score', 'word_count', 'is_excluded']
    list_filter = ['match_type', 'is_excluded']


@admin.register(ExclusionRule)
class ExclusionRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'rule_type', 'is_enabled', 'institution']
    list_filter = ['rule_type', 'is_enabled']


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ['document', 'job_type', 'status', 'progress', 'created_at']
    list_filter = ['status', 'job_type']
