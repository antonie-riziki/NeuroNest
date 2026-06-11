from django.shortcuts import render, redirect
from django.contrib import messages
from .supabase_client import SupabaseClient

def auth(request):
    # If already logged in, redirect to profile page
    if request.session.get('access_token') and request.session.get('caregiver_id'):
        return redirect('child_profile')

    active_tab = 'signin'
    if request.method == 'POST':
        action = request.POST.get('action')
        client = SupabaseClient()
        
        if action == 'signup':
            active_tab = 'signup'
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not full_name or not email or not password:
                messages.error(request, "Please fill in all required fields.")
                return render(request, 'auth.html', {'active_tab': active_tab})
                
            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, 'auth.html', {'active_tab': active_tab})
                
            try:
                # 1. Sign up user
                res = client.signup(email, password, full_name, phone)
                
                # Check if email confirmation is required (Supabase signup returns user but might not return session token if confirmation is enabled)
                access_token = res.get('access_token')
                user = res.get('user', {})
                user_id = user.get('id')
                
                if access_token and user_id:
                    request.session['access_token'] = access_token
                    request.session['caregiver_id'] = user_id
                    request.session['caregiver_name'] = full_name
                    messages.success(request, f"Welcome, {full_name}! Account created successfully.")
                    return redirect('child_profile')
                else:
                    messages.success(request, "Account created! Please check your email to confirm registration.")
                    return redirect('auth')
            except Exception as e:
                messages.error(request, f"Signup failed: {str(e)}")
                
        elif action == 'signin':
            active_tab = 'signin'
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '')
            
            if not email or not password:
                messages.error(request, "Please fill in all fields.")
                return render(request, 'auth.html', {'active_tab': active_tab})
                
            try:
                res = client.signin(email, password)
                access_token = res.get('access_token')
                user = res.get('user', {})
                user_id = user.get('id')
                
                if access_token and user_id:
                    request.session['access_token'] = access_token
                    request.session['caregiver_id'] = user_id
                    
                    # Fetch profile details
                    profile = client.get_caregiver_profile(user_id, access_token)
                    request.session['caregiver_name'] = profile.get('full_name', email.split('@')[0]) if profile else email.split('@')[0]
                    
                    messages.success(request, f"Logged in successfully. Welcome back!")
                    return redirect('child_profile')
                else:
                    messages.error(request, "Invalid credentials.")
            except Exception as e:
                messages.error(request, f"Login failed: {str(e)}")

    return render(request, 'auth.html', {'active_tab': active_tab})


def child_profile(request):
    token = request.session.get('access_token')
    caregiver_id = request.session.get('caregiver_id')
    
    if not token or not caregiver_id:
        messages.warning(request, "Please sign in to access child profiles.")
        return redirect('auth')
        
    client = SupabaseClient()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_child':
            name = request.POST.get('name', '').strip()
            dob = request.POST.get('dob', '').strip()
            concern = request.POST.get('concern', '').strip()
            language = request.POST.get('language', 'English').strip()
            profile_picture = request.FILES.get('profile_picture')
            
            if not name or not dob or not concern:
                messages.error(request, "Please fill in all required child details.")
                return redirect('child_profile')
                
            profile_picture_url = None
            if profile_picture:
                try:
                    profile_picture_url = client.upload_avatar(
                        profile_picture.name,
                        profile_picture.read(),
                        profile_picture.content_type,
                        token
                    )
                except Exception as e:
                    messages.warning(request, f"Failed to upload profile picture: {str(e)}")
                    # Continue creating the child profile anyway without photo if upload failed
            
            try:
                res = client.add_child(
                    caregiver_id=caregiver_id,
                    name=name,
                    dob=dob,
                    concern=concern,
                    language=language,
                    profile_picture_url=profile_picture_url,
                    token=token
                )
                
                # Auto-select the newly added child if there isn't one active
                if not request.session.get('active_child_id') and res:
                    item = res[0] if isinstance(res, list) else res
                    request.session['active_child_id'] = item.get('id')
                    
                messages.success(request, f"Successfully registered profile for {name}!")
            except Exception as e:
                messages.error(request, f"Failed to register child: {str(e)}")
                
            return redirect('child_profile')
            
    # GET Request: Fetch and display children
    try:
        children = client.get_children(caregiver_id, token)
    except Exception as e:
        messages.error(request, f"Could not retrieve children profiles: {str(e)}")
        children = []
        
    caregiver_name = request.session.get('caregiver_name', 'Caregiver')
    active_child_id = request.session.get('active_child_id')
    
    # If no active child is selected but profiles exist, default to the first one
    if not active_child_id and children:
        active_child_id = children[0].get('id')
        request.session['active_child_id'] = active_child_id
        
    context = {
        'children': children,
        'caregiver_name': caregiver_name,
        'caregiver_id': caregiver_id,
        'active_child_id': active_child_id
    }
    return render(request, 'child_profile.html', context)


def select_child(request, child_id):
    if not request.session.get('access_token'):
        return redirect('auth')
    request.session['active_child_id'] = str(child_id)
    messages.success(request, "Active profile switched.")
    
    # Redirect back to where the request came from or child_profile
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('child_profile')


def logout_view(request):
    request.session.flush()
    messages.success(request, "Logged out successfully.")
    return redirect('auth')
