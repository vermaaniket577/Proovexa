"""Document URL patterns."""
from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('upload/', views.upload_view, name='upload'),
    path('', views.document_list_view, name='list'),
    path('<uuid:doc_id>/', views.document_detail_view, name='detail'),
    path('<uuid:doc_id>/delete/', views.document_delete_view, name='delete'),
    path('<uuid:doc_id>/download/', views.document_download_view, name='download'),
]
