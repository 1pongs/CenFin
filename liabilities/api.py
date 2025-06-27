from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from difflib import SequenceMatcher

from .models import Lender

@login_required
@require_http_methods(["GET", "POST"])
def lender_search_or_create(request):
    if request.method == "GET":
        term = request.GET.get("q", "").strip()
        qs = Lender.objects.all()
        if term:
            qs = qs.filter(name__icontains=term)
        results = [
            {"id": l.id, "name": l.name} for l in qs.order_by("name")[:10]
        ]
        return JsonResponse({"results": results})

    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "missing name"}, status=400)
    force = request.POST.get("force")

    match = Lender.objects.filter(name__iexact=name).first()
    if match:
        return JsonResponse({"id": match.id, "name": match.name})

    if not force:
        for l in Lender.objects.all():
            ratio = SequenceMatcher(None, name.lower(), l.name.lower()).ratio()
            if ratio >= 0.8:
                return JsonResponse({"similar": {"id": l.id, "name": l.name}}, status=409)
    try:
        lender = Lender.objects.create(name=name)
    except IntegrityError:
        return JsonResponse({"error": "duplicate"}, status=400)
    return JsonResponse({"id": lender.id, "name": lender.name}, status=201)