from django.contrib import admin, messages
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404

from .models import Document, ExtractedText, ReferenceSource
from analysis.services import (
    generate_both_reports,
    generate_similarity_report,
    generate_ai_report,
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'title_display',
        'uploaded_by',
        'file_type',
        'status',
        'similarity_badge',
        'ai_badge',
        'one_click_actions',
        'uploaded_at',
    ]
    list_filter = ['status', 'file_type', 'is_reference', 'uploaded_at']
    search_fields = ['title', 'original_filename', 'uploaded_by__username', 'uploaded_by__email']
    readonly_fields = ['id', 'file_hash', 'uploaded_at', 'processed_at']
    actions = [
        'action_generate_both_reports',
        'action_generate_similarity_reports',
        'action_generate_ai_reports',
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by').prefetch_related(
            'similarity_reports', 'ai_reports'
        )

    def title_display(self, obj):
        return format_html(
            '<div style="max-width: 260px;">'
            '  <strong>{}</strong>'
            '  <div style="color: #64748b; font-size: 11px;">{} &bull; {}p</div>'
            '</div>',
            obj.title,
            obj.original_filename,
            obj.page_count or 1
        )
    title_display.short_description = "Document"

    def similarity_badge(self, obj):
        sim = obj.latest_similarity_report
        if sim:
            score = sim.overall_similarity
            color = "#059669" if score < 15 else "#d97706" if score < 30 else "#dc2626"
            bg = "#ecfdf5" if score < 15 else "#fffbeb" if score < 30 else "#fef2f2"
            view_url = reverse('reports:detail', args=[sim.id])
            pdf_url = reverse('reports:download_pdf', args=[sim.id])
            rescan_url = reverse('admin:documents_document_generate_similarity', args=[obj.id])
            return format_html(
                '<div style="display:flex; align-items:center; gap:6px;">'
                '  <a href="{}" target="_blank" style="background:{}; color:{}; border:1px solid {}; font-weight:bold; font-size:11px; padding:2px 7px; border-radius:12px; text-decoration:none;">{}</a>'
                '  <a href="{}" target="_blank" title="Download PDF" style="text-decoration:none; color:#475569; font-size:11px;">PDF</a>'
                '  <a href="{}" title="Re-run similarity analysis" style="text-decoration:none; color:#0284c7; font-size:12px;">&#x21bb;</a>'
                '</div>',
                view_url, bg, color, color, sim.similarity_display, pdf_url, rescan_url
            )
        else:
            scan_url = reverse('admin:documents_document_generate_similarity', args=[obj.id])
            return format_html(
                '<a href="{}" class="button" style="background:#0284c7; color:#fff; font-size:11px; padding:3px 8px; border-radius:4px; text-decoration:none; white-space:nowrap;">'
                '  &#9889; Gen Sim'
                '</a>',
                scan_url
            )
    similarity_badge.short_description = "Similarity Report"

    def ai_badge(self, obj):
        ai = obj.latest_ai_report
        if ai:
            score = ai.overall_ai_score
            color = "#059669" if score < 20 else "#d97706" if score < 50 else "#dc2626"
            bg = "#ecfdf5" if score < 20 else "#fffbeb" if score < 50 else "#fef2f2"
            view_url = reverse('reports:ai_report', args=[obj.id])
            pdf_url = reverse('reports:download_ai_pdf', args=[ai.id])
            rescan_url = reverse('admin:documents_document_generate_ai', args=[obj.id])
            score_str = f"{int(round(score))}% AI"
            return format_html(
                '<div style="display:flex; align-items:center; gap:6px;">'
                '  <a href="{}" target="_blank" style="background:{}; color:{}; border:1px solid {}; font-weight:bold; font-size:11px; padding:2px 7px; border-radius:12px; text-decoration:none;">{}</a>'
                '  <a href="{}" target="_blank" title="Download AI PDF" style="text-decoration:none; color:#475569; font-size:11px;">PDF</a>'
                '  <a href="{}" title="Re-run AI analysis" style="text-decoration:none; color:#0284c7; font-size:12px;">&#x21bb;</a>'
                '</div>',
                view_url, bg, color, color, score_str, pdf_url, rescan_url
            )
        else:
            scan_url = reverse('admin:documents_document_generate_ai', args=[obj.id])
            return format_html(
                '<a href="{}" class="button" style="background:#059669; color:#fff; font-size:11px; padding:3px 8px; border-radius:4px; text-decoration:none; white-space:nowrap;">'
                '  &#9889; Gen AI'
                '</a>',
                scan_url
            )
    ai_badge.short_description = "AI Plag Report"

    def one_click_actions(self, obj):
        both_url = reverse('admin:documents_document_generate_both', args=[obj.id])
        return format_html(
            '<a href="{}" class="button" style="background:linear-gradient(135deg, #0084ff, #0056b3); color:#fff; font-weight:bold; font-size:11.5px; padding:4px 10px; border-radius:5px; text-decoration:none; display:inline-block; white-space:nowrap; box-shadow:0 1px 3px rgba(0,132,255,0.3);">'
            '  &#9889; 1-Click Both Reports'
            '</a>',
            both_url
        )
    one_click_actions.short_description = "1-Click Generation"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/generate-both/',
                self.admin_site.admin_view(self.generate_both_view),
                name='documents_document_generate_both',
            ),
            path(
                '<path:object_id>/generate-similarity/',
                self.admin_site.admin_view(self.generate_similarity_view),
                name='documents_document_generate_similarity',
            ),
            path(
                '<path:object_id>/generate-ai/',
                self.admin_site.admin_view(self.generate_ai_view),
                name='documents_document_generate_ai',
            ),
        ]
        return custom_urls + urls

    def generate_both_view(self, request, object_id):
        doc = get_object_or_404(Document, pk=object_id)
        try:
            sim, ai = generate_both_reports(doc, user=request.user)
            self.message_user(
                request,
                f"1-Click Reports generated for '{doc.title}'! Similarity: {sim.similarity_display} | AI: {ai.overall_ai_score:.0f}%",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"Generation failed: {str(e)}", messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('admin:documents_document_changelist'))

    def generate_similarity_view(self, request, object_id):
        doc = get_object_or_404(Document, pk=object_id)
        try:
            sim = generate_similarity_report(doc, user=request.user)
            self.message_user(
                request,
                f"Similarity Report generated for '{doc.title}': {sim.similarity_display}",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"Similarity generation failed: {str(e)}", messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('admin:documents_document_changelist'))

    def generate_ai_view(self, request, object_id):
        doc = get_object_or_404(Document, pk=object_id)
        try:
            ai = generate_ai_report(doc, user=request.user)
            self.message_user(
                request,
                f"AI Detection Report generated for '{doc.title}': {ai.overall_ai_score:.0f}% AI",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"AI generation failed: {str(e)}", messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('admin:documents_document_changelist'))

    @admin.action(description="⚡ 1-Click Generate BOTH Reports (Similarity + AI)")
    def action_generate_both_reports(self, request, queryset):
        success_count = 0
        error_count = 0
        for doc in queryset:
            try:
                generate_both_reports(doc, user=request.user)
                success_count += 1
            except Exception as e:
                error_count += 1
        if success_count:
            self.message_user(
                request,
                f"Successfully generated Both Reports (Similarity + AI) for {success_count} document(s) in 1 click!",
                messages.SUCCESS
            )
        if error_count:
            self.message_user(request, f"Failed on {error_count} document(s).", messages.ERROR)

    @admin.action(description="🔍 Generate Similarity Plagiarism Reports")
    def action_generate_similarity_reports(self, request, queryset):
        success_count = 0
        error_count = 0
        for doc in queryset:
            try:
                generate_similarity_report(doc, user=request.user)
                success_count += 1
            except Exception:
                error_count += 1
        if success_count:
            self.message_user(
                request,
                f"Successfully generated Similarity Reports for {success_count} document(s).",
                messages.SUCCESS
            )
        if error_count:
            self.message_user(request, f"Failed on {error_count} document(s).", messages.ERROR)

    @admin.action(description="🤖 Generate AI Writing Detection Reports")
    def action_generate_ai_reports(self, request, queryset):
        success_count = 0
        error_count = 0
        for doc in queryset:
            try:
                generate_ai_report(doc, user=request.user)
                success_count += 1
            except Exception:
                error_count += 1
        if success_count:
            self.message_user(
                request,
                f"Successfully generated AI Detection Reports for {success_count} document(s).",
                messages.SUCCESS
            )
        if error_count:
            self.message_user(request, f"Failed on {error_count} document(s).", messages.ERROR)


@admin.register(ExtractedText)
class ExtractedTextAdmin(admin.ModelAdmin):
    list_display = ['document', 'page_number', 'paragraph_number', 'word_count']
    list_filter = ['document']


@admin.register(ReferenceSource)
class ReferenceSourceAdmin(admin.ModelAdmin):
    list_display = ['title', 'source_type', 'author', 'institution', 'is_active']
    list_filter = ['source_type', 'is_active']
    search_fields = ['title', 'author']
