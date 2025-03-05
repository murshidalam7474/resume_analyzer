from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('analyze/', views.upload_and_analyze, name='analyze'),
    path('results/<str:analysis_id>/', views.view_result, name='view_result'),
    path('download/<str:analysis_id>/', views.download_pdf, name='download_pdf'),
]