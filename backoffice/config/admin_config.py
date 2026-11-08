from django.contrib.admin.apps import AdminConfig


class BackofficeAdminConfig(AdminConfig):
    """Swap Django's default admin site for our customised one (KPI dashboard on the home page)."""

    default_site = "core.site.PayForgeAdminSite"
