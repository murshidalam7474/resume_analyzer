from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("analyze/", views.upload_and_analyze, name="analyze"),
    path("results/<uuid:analysis_id>/", views.view_result, name="view_result"),
    path("download/<uuid:analysis_id>/", views.download_pdf, name="download_pdf"),
    path("bot-question/", views.bot_question, name="bot_question"),
    path("compare/", views.compare_resumes, name="compare_resumes"),  # Fixed incorrect function reference
]
