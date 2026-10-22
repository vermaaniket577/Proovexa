from django.contrib import admin
from .models import SimilarityReport, MatchedPassage, ExclusionRule, ProcessingJob


@admin.register(SimilarityReport)
class SimilarityReportAdmin(admin.ModelAdmin):
    list_display = ['document', 'overall_similarity', 'source_count', 'status', 'created_at']
    list_filter = ['status']
    readonly_fields = ['id', 'created_at', 'updated_at']


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
