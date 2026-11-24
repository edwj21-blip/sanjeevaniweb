"""Context processors for Sanjeevani."""
from .models import Notification


def site_context(request):
    unread = 0
    donor = None
    if request.user.is_authenticated:
        unread = Notification.objects.filter(user=request.user, is_read=False).count()
        donor = getattr(request.user, 'donor_profile', None)
    return {
        'site_name': 'Sanjeevani',
        'unread_notifications': unread,
        'my_donor': donor,
    }
