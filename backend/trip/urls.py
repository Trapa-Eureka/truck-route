from django.urls import path

from .views import AnalyzeView, HeatmapView

urlpatterns = [
    path("analyze", AnalyzeView.as_view(), name="analyze"),
    path("heatmap", HeatmapView.as_view(), name="heatmap"),
]
