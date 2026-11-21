"""Context processors for Sanjeevani."""
from .models import DonorProfile, Notification


def site_context(request):
    """Global context available to all templates."""
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

    total_donors = DonorProfile.objects.filter(is_active=True, show_in_directory=True).count()
    available_donors = DonorProfile.objects.filter(is_active=True, show_in_directory=True, is_available=True).count()

    return {
        'site_name': 'Sanjeevani',
        'site_name_ml': 'സഞ്ജീവനി',
        'site_tagline': 'Donate Blood. Save Lives.',
        'site_tagline_ml': 'ഒരു തുള്ളി രക്തം, ഒരു ജീവന് പ്രതീക്ഷ.',
        'unread_notifications': unread_count,
        'total_donors': total_donors,
        'available_donors': available_donors,
    }
