from django.contrib import admin

from . import stats


class PayForgeAdminSite(admin.AdminSite):
    site_header = "PayForge Back-office"
    site_title = "PayForge Back-office"
    index_title = "Operations overview"

    def index(self, request, extra_context=None):
        context = {**(extra_context or {}), "kpis": stats.collect()}
        return super().index(request, context)
