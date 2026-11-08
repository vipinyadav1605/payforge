from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse


class Command(BaseCommand):
    help = "Smoke test: open the home page and every admin list and detail page against the real database."

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first()
        if user is None:
            raise CommandError("No superuser yet: run 'manage.py bootstrap' first.")
        client = Client()
        client.force_login(user)

        failures = []

        def check(url, label):
            response = client.get(url)
            ok = response.status_code == 200
            self.stdout.write(f"{'OK  ' if ok else 'FAIL'} {response.status_code} {label}")
            if not ok:
                failures.append(label)
            return response

        home = check("/", "home (KPI dashboard)")
        if home.status_code == 200 and b"Ledger balanced" not in home.content:
            failures.append("home: KPI cards missing")

        for model, model_admin in admin.site._registry.items():
            if model._meta.app_label != "core":
                continue
            info = (model._meta.app_label, model._meta.model_name)
            check(reverse("admin:%s_%s_changelist" % info), f"{model.__name__} list")
            first = model.objects.first()
            if first is not None:
                check(reverse("admin:%s_%s_change" % info, args=[first.pk]), f"{model.__name__} detail")

        if failures:
            raise CommandError(f"{len(failures)} page(s) failed: {failures}")
        self.stdout.write(self.style.SUCCESS("All back-office pages loaded"))
