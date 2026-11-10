"""
Document upload, management, and text preview views.
"""
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, FileResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.conf import settings

from .models import Document, ExtractedText, ReferenceSource
from .forms import DocumentUploadForm
from .validators import validate_document
from .extractors import extract_text
from accounts.models import AuditLog
from accounts.decorators import role_required


@login_required
def upload_view(request):
    """Handle document upload with validation."""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            uploaded_file = request.FILES['file']

            # Validate file
            is_valid, file_type, errors = validate_document(uploaded_file)
            if not is_valid:
                for error in errors:
                    messages.error(request, error)
                return render(request, 'documents/upload.html', {'form': form})

            # Check for duplicate by hash or updated version with same title
            import hashlib
            sha256 = hashlib.sha256()
            for chunk in uploaded_file.chunks(8192):
                sha256.update(chunk)
            file_hash = sha256.hexdigest()
            uploaded_file.seek(0)

            clean_title = form.cleaned_data['title'].strip()

            existing_by_hash = Document.objects.filter(
                file_hash=file_hash,
                uploaded_by=request.user,
                is_deleted=False
            ).first()

            existing_by_title = Document.objects.filter(
                title__iexact=clean_title,
                uploaded_by=request.user,
                is_deleted=False
            ).first()

            existing = existing_by_hash or existing_by_title
            is_recheck = bool(existing)

            if existing:
                doc = existing
                doc.file = uploaded_file
                doc.original_filename = uploaded_file.name
                doc.file_type = file_type
                doc.file_size = uploaded_file.size
                doc.file_hash = file_hash
                doc.mime_type = uploaded_file.content_type
                doc.title = clean_title
                if form.cleaned_data.get('assignment'):
                    doc.assignment = form.cleaned_data.get('assignment')
                doc.status = Document.Status.PENDING
                doc.save()
            else:
                doc = Document(
                    title=clean_title,
                    original_filename=uploaded_file.name,
                    file=uploaded_file,
                    file_type=file_type,
                    file_size=uploaded_file.size,
                    file_hash=file_hash,
                    mime_type=uploaded_file.content_type,
                    uploaded_by=request.user,
                    assignment=form.cleaned_data.get('assignment'),
                    is_reference=form.cleaned_data.get('is_reference', False),
                    status=Document.Status.PENDING,
                )
                doc.save()

            # Audit log
            AuditLog.objects.create(
                user=request.user,
                action=AuditLog.Action.UPLOAD,
                resource_type='Document',
                resource_id=str(doc.id),
                details={'filename': uploaded_file.name, 'size': uploaded_file.size},
                ip_address=_get_client_ip(request),
            )

            # Extract text immediately (synchronous for Phase 1)
            try:
                doc.status = Document.Status.EXTRACTING
                doc.save(update_fields=['status'])

                file_path = doc.file.path
                result = extract_text(file_path, file_type)

                if result.errors:
                    doc.status = Document.Status.FAILED
                    doc.error_message = '; '.join(result.errors)
                    doc.save(update_fields=['status', 'error_message'])
                    messages.error(request, f'Text extraction failed: {doc.error_message}')
                    return redirect('documents:detail', doc_id=doc.id)

                # Clear previous extracted text on recheck
                if is_recheck:
                    doc.extracted_texts.all().delete()
                    # Also purge any previous ReferenceSource for this document to prevent self-matching
                    ReferenceSource.objects.filter(document=doc).delete()
                    ReferenceSource.objects.filter(url__icontains=str(doc.id)).delete()

                # Save extracted text
                char_offset = 0
                for page in result.pages:
                    for para in page['paragraphs']:
                        text_len = len(para['text'])
                        ExtractedText.objects.create(
                            document=doc,
                            page_number=page['page_number'],
                            paragraph_number=para['para_number'],
                            content=para['text'],
                            word_count=len(para['text'].split()),
                            char_start=char_offset,
                            char_end=char_offset + text_len,
                        )
                        char_offset += text_len + 2  # +2 for paragraph separator

                doc.page_count = result.page_count
                doc.word_count = result.word_count
                doc.status = Document.Status.EXTRACTED
                doc.processed_at = timezone.now()
                doc.save(update_fields=['page_count', 'word_count', 'status', 'processed_at'])

                # Sequence pipeline: run plagiarism comparison & AI detection first (in-memory)
                # and only index into reference search index after scoring to eliminate self-matching
                try:
                    from analysis.services import generate_both_reports
                    sim_report, ai_report = generate_both_reports(doc, user=request.user)
                    action_verb = "rechecked" if is_recheck else "uploaded & analyzed"
                    messages.success(
                        request,
                        f'Document "{doc.title}" {action_verb}! '
                        f'Plagiarism: {sim_report.similarity_display} • AI: {ai_report.overall_ai_score:.0f}%'
                    )
                except Exception as analysis_err:
                    messages.success(
                        request,
                        f'Document "{doc.title}" uploaded and text extracted successfully ({result.word_count} words).'
                    )

                # Index into internal database only after comparison is complete
                from analysis.services import index_document_into_internal_database
                index_document_into_internal_database(doc, full_text=result.full_text)

                return redirect('documents:detail', doc_id=doc.id)


            except Exception as e:
                doc.status = Document.Status.FAILED
                doc.error_message = str(e)
                doc.save(update_fields=['status', 'error_message'])
                messages.error(request, f'Processing error: {str(e)}')
                return redirect('documents:detail', doc_id=doc.id)
    else:
        form = DocumentUploadForm(user=request.user)

    return render(request, 'documents/upload.html', {'form': form})


@login_required
def document_list_view(request):
    """List user's documents."""
    if request.user.is_admin:
        documents = Document.objects.filter(is_deleted=False)
    elif request.user.is_teacher:
        # Teachers see their own docs + assignment submissions
        from django.db.models import Q
        documents = Document.objects.filter(
            Q(uploaded_by=request.user) |
            Q(assignment__created_by=request.user),
            is_deleted=False
        ).distinct()
    else:
        documents = Document.objects.filter(uploaded_by=request.user, is_deleted=False)

    documents = documents.select_related('uploaded_by', 'assignment')

    # Filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        documents = documents.filter(status=status_filter)

    search = request.GET.get('search', '')
    if search:
        documents = documents.filter(title__icontains=search)

    paginator = Paginator(documents, 15)
    page = request.GET.get('page', 1)
    docs_page = paginator.get_page(page)

    return render(request, 'documents/list.html', {
        'documents': docs_page,
        'status_filter': status_filter,
        'search': search,
        'statuses': Document.Status.choices,
    })


@login_required
def document_detail_view(request, doc_id):
    """View document details and extracted text preview."""
    doc = get_object_or_404(Document, id=doc_id, is_deleted=False)

    # Authorization
    if not _can_view_document(request.user, doc):
        return HttpResponseForbidden("You don't have permission to view this document.")

    extracted_texts = doc.extracted_texts.all().order_by('page_number', 'paragraph_number')

    # Check if analysis has been run
    from analysis.models import SimilarityReport
    reports = SimilarityReport.objects.filter(document=doc).order_by('-created_at')

    return render(request, 'documents/detail.html', {
        'document': doc,
        'extracted_texts': extracted_texts,
        'reports': reports,
    })


@login_required
def document_delete_view(request, doc_id):
    """Soft-delete a document."""
    doc = get_object_or_404(Document, id=doc_id, is_deleted=False)

    # Only owner or admin can delete
    if doc.uploaded_by != request.user and not request.user.is_admin:
        return HttpResponseForbidden("You don't have permission to delete this document.")

    if request.method == 'POST':
        doc.is_deleted = True
        doc.save(update_fields=['is_deleted'])

        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.DELETE,
            resource_type='Document',
            resource_id=str(doc.id),
            ip_address=_get_client_ip(request),
        )

        messages.success(request, f'Document "{doc.title}" has been deleted.')
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('documents:list')

    return render(request, 'documents/delete_confirm.html', {'document': doc})


@login_required
def document_download_view(request, doc_id):
    """Download the original uploaded document."""
    doc = get_object_or_404(Document, id=doc_id, is_deleted=False)

    if not _can_view_document(request.user, doc):
        return HttpResponseForbidden("You don't have permission to download this document.")

    return FileResponse(
        doc.file.open('rb'),
        as_attachment=True,
        filename=doc.original_filename,
    )


def _can_view_document(user, document):
    """Check if a user can view a document."""
    if user.is_admin:
        return True
    if document.uploaded_by == user:
        return True
    if user.is_teacher and document.assignment and document.assignment.created_by == user:
        return True
    return False


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
