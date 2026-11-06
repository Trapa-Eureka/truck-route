from django.urls import include, path

urlpatterns = [
    path("api/", include("trip.urls")),
]

# This server only speaks JSON: its own error pages are in the API's error shape too.
handler400 = "trip.errors.bad_request"
handler404 = "trip.errors.not_found"
handler500 = "trip.errors.server_error"
