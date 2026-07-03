from .models import SchoolProfile


def school_profile(request):
    return {"school_profile": SchoolProfile.current()}
