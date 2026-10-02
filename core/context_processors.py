from django.conf import settings
def site_settings(request):
    return {"WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER, "SITE_NAME": "Web Price Shoes"}
