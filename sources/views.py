"""Source provider views."""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from .providers import get_all_providers


@login_required
@role_required(['admin'])
def source_providers_view(request):
    """View available source providers and their status."""
    providers = get_all_providers()
    return render(request, 'sources/providers.html', {
        'providers': providers,
    })
