from django.shortcuts import render

# Create your views here.
def auth(request):
    return render(request, 'auth.html')


def child_profile(request):
    return render(request, 'child_profile.html')

