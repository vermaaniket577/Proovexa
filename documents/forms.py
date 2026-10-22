"""Document upload and management forms."""
from django import forms
from .models import Document
from accounts.models import Assignment


class DocumentUploadForm(forms.Form):
    """Form for uploading documents for plagiarism checking."""
    title = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Document title',
            'id': 'doc-title',
        })
    )
    file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'id': 'doc-file',
            'accept': '.pdf,.docx,.txt,.pptx',
        })
    )
    assignment = forms.ModelChoiceField(
        queryset=Assignment.objects.filter(is_active=True),
        required=False,
        empty_label="No assignment (standalone check)",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'doc-assignment',
        })
    )
    is_reference = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'doc-is-reference',
        }),
        label="Add to reference collection"
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            if user.is_student:
                # Students can't add reference docs or see is_reference
                del self.fields['is_reference']
                # Filter assignments to ones the student is enrolled in
                self.fields['assignment'].queryset = Assignment.objects.filter(
                    is_active=True,
                    course__students=user
                )
            elif user.is_teacher:
                # Teachers see their assignments
                self.fields['assignment'].queryset = Assignment.objects.filter(
                    is_active=True,
                    created_by=user
                )
