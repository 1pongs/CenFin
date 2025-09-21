from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from difflib import SequenceMatcher

from .models import Lender


@login_required
def lender_search(request):
    term = request.GET.get("q", "").strip()
    qs = Lender.objects.all()
    if term:
        qs = qs.filter(name__icontains=term)
    results = [{"id": lend.id, "text": lend.name} for lend in qs.order_by("name")[:10]]
    return JsonResponse({"results": results})


@login_required
@require_http_methods(["POST"])
def lender_create(request):
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "missing name"}, status=400)
    lender, _ = Lender.objects.get_or_create(name__iexact=name, defaults={"name": name})
    return JsonResponse({"id": lender.id, "text": lender.name})


@login_required
@require_http_methods(["GET", "POST"])
def lender_search_or_create(request):
    if request.method == "GET":
        term = request.GET.get("q", "").strip()
        qs = Lender.objects.all()
        if term:
            qs = qs.filter(name__icontains=term)
        results = [{"id": lend.id, "name": lend.name} for lend in qs.order_by("name")[:10]]
        return JsonResponse({"results": results})

    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "missing name"}, status=400)
    force = request.POST.get("force")

    match = Lender.objects.filter(name__iexact=name).first()
    if match:
        return JsonResponse({"id": match.id, "name": match.name})

    if not force:
        for lend in Lender.objects.all():
            ratio = SequenceMatcher(None, name.lower(), lend.name.lower()).ratio()
            if ratio >= 0.8:
                return JsonResponse(
                    {"similar": {"id": lend.id, "name": lend.name}}, status=409
                )
    try:
        lender = Lender.objects.create(name=name)
    except IntegrityError:
        return JsonResponse({"error": "duplicate"}, status=400)
    return JsonResponse({"id": lender.id, "name": lender.name}, status=201)
