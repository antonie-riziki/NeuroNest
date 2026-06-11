import os
import json
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from apps.core.supabase_client import SupabaseClient
from apps.engine.pipeline import get_qa_chain, query_system, update_vector_store_for_child, update_global_vector_store

def knowledgebase(request):
    token = request.session.get('access_token')
    caregiver_id = request.session.get('caregiver_id')
    
    if not token or not caregiver_id:
        messages.warning(request, "Please sign in to access the knowledge base.")
        return redirect('auth')
        
    client = SupabaseClient()
    
    try:
        children = client.get_children(caregiver_id, token)
    except Exception as e:
        messages.error(request, f"Error fetching child profiles: {e}")
        children = []

    if request.method == 'POST':
        # Check if this is an AJAX search query (JSON payload)
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body)
                query = body.get('query', '').strip()
            except Exception:
                return JsonResponse({'error': 'Invalid request body'}, status=400)
                
            if not query:
                return JsonResponse({'error': 'Query cannot be empty'}, status=400)
                
            # Build children profiles context summary for global search
            child_profiles_info = []
            for child in children:
                child_profiles_info.append(
                    f"Child Name: {child.get('name')}, Age/DOB: {child.get('dob')}, Primary Concern: {child.get('concern')}, Language: {child.get('language')}"
                )
            child_profiles_context = "\n".join(child_profiles_info) if child_profiles_info else "No children registered yet."
            caregiver_profile_str = f"Caregiver ID: {caregiver_id}"
            
            # Load global chain
            qa_chain = get_qa_chain(
                use_global_db=True, 
                child_profile=child_profiles_context, 
                caregiver_profile=caregiver_profile_str
            )
            response = query_system(query, qa_chain)
            return JsonResponse({'response': response})
            
        else:
            # File Ingestion Upload
            uploaded_file = request.FILES.get('file')
            title = request.POST.get('title', '').strip()
            category = request.POST.get('category', '').strip()
            tier = request.POST.get('tier', '').strip()
            status = request.POST.get('status', 'Pending').strip()
            associated_child_id = request.POST.get('associated_child', '').strip()
            
            if not uploaded_file:
                messages.error(request, "Please select a document to upload.")
                return redirect('knowledgebase')
                
            # Save local copy under appropriate directory
            if associated_child_id and associated_child_id != 'global':
                target_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', f'child_{associated_child_id}')
            else:
                target_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', 'global')
                
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, uploaded_file.name)
            
            try:
                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
                
                messages.success(request, f"Successfully uploaded '{uploaded_file.name}'!")
                
                # Re-index the FAISS vector store
                if associated_child_id and associated_child_id != 'global':
                    update_vector_store_for_child(associated_child_id)
                    messages.success(request, f"Updated localized vector store database.")
                else:
                    update_global_vector_store()
                    messages.success(request, "Updated global vector store database.")
                    
            except Exception as e:
                messages.error(request, f"Failed to ingest file: {e}")
                
            return redirect('knowledgebase')

    # GET Request: scan local directories to display recent upload names
    recent_uploads = []
    
    # Global docs
    global_docs_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', 'global')
    if os.path.exists(global_docs_dir):
        for f in os.listdir(global_docs_dir):
            if f != '.gitkeep' and os.path.isfile(os.path.join(global_docs_dir, f)):
                recent_uploads.append({
                    'name': f,
                    'category': 'Global Knowledge',
                    'status': 'Approved',
                    'date': 'Core Document'
                })
                
    # Child specific docs
    docs_root = os.path.join(settings.BASE_DIR, 'media', 'docs')
    if os.path.exists(docs_root):
        for item in os.listdir(docs_root):
            if item.startswith('child_'):
                child_id_str = item.replace('child_', '')
                child_name = "Personalized"
                for child in children:
                    if str(child.get('id')) == child_id_str:
                        child_name = child.get('name')
                        break
                child_dir = os.path.join(docs_root, item)
                for f in os.listdir(child_dir):
                    if os.path.isfile(os.path.join(child_dir, f)):
                        recent_uploads.append({
                            'name': f,
                            'category': f"Personalized ({child_name})",
                            'status': 'Approved',
                            'date': 'Child Profile Info'
                        })

    context = {
        'children': children,
        'recent_uploads': recent_uploads[:10]
    }
    return render(request, 'knowledge_graph.html', context)


def chat(request):
    token = request.session.get('access_token')
    caregiver_id = request.session.get('caregiver_id')
    active_child_id = request.session.get('active_child_id')
    
    if not token or not caregiver_id:
        messages.warning(request, "Please sign in to access the chatbot.")
        return redirect('auth')
        
    client = SupabaseClient()
    try:
        children = client.get_children(caregiver_id, token)
    except Exception as e:
        messages.error(request, f"Error loading child profiles: {e}")
        children = []
        
    active_child = None
    if children:
        if active_child_id:
            for child in children:
                if str(child.get('id')) == str(active_child_id):
                    active_child = child
                    break
        if not active_child:
            active_child = children[0]
            request.session['active_child_id'] = str(active_child.get('id'))
    else:
        messages.info(request, "Please register a child profile first to access personalized services.")
        return redirect('child_profile')
        
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            query = body.get('message', '').strip()
        except Exception:
            return JsonResponse({'error': 'Invalid request payload'}, status=400)
            
        if not query:
            return JsonResponse({'error': 'Query cannot be empty'}, status=400)
            
        # Personalize system instructions
        child_profile_str = f"Name: {active_child.get('name')}, DOB/Age: {active_child.get('dob')}, Concern/Diagnosis: {active_child.get('concern')}, Language: {active_child.get('language')}"
        caregiver_profile_str = f"Caregiver ID: {caregiver_id}"
        
        # Load QA RAG chain
        qa_chain = get_qa_chain(
            use_global_db=False,
            child_profile=child_profile_str,
            caregiver_profile=caregiver_profile_str,
            child_id=str(active_child.get('id'))
        )
        response = query_system(query, qa_chain)
        return JsonResponse({'response': response})
        
    context = {
        'active_child': active_child,
        'children': children
    }
    return render(request, 'chatbot.html', context)
    