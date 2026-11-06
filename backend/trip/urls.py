from django.urls import path

from .views import AnalyzeView, HeatmapView, PlacesView, ReversePlaceView

urlpatterns = [
    path("analyze", AnalyzeView.as_view(), name="analyze"),
    path("heatmap", HeatmapView.as_view(), name="heatmap"),
    path("places", PlacesView.as_view(), name="places"),
    path("places/reverse", ReversePlaceView.as_view(), name="places-reverse"),
]
