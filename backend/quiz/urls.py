from django.http import JsonResponse
from django.urls import include,path

def healthz(request): return JsonResponse({'ok':True})  # для health-check хостинга (Koyeb/Render)

urlpatterns=[path('healthz/',healthz),path('api/',include('game.urls'))]
