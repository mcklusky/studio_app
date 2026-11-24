from django.contrib import admin

from apps.files.models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "content_type", "file_size", "purpose", "organization", "uploaded_by", "created_at")
    list_filter = ("organization", "content_type", "purpose")
    search_fields = ("original_name", "owner_type", "owner_id")
