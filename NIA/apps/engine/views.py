import os
import json
import uuid
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from apps.core.supabase_client import SupabaseClient
from apps.engine.pipeline import get_qa_chain, query_system, update_vector_store_for_child, update_global_vector_store


def _chat_store(request):
    return request.session.setdefault('chat_threads', {})


def _child_thread_bucket(request, child_id):
    store = _chat_store(request)
    key = str(child_id)
    store.setdefault(key, [])
    return store[key]


def _chat_audience(request):
    """Return who NIA should speak to in this session."""
    role = (
        request.session.get('account_type')
        or request.session.get('user_role')
        or request.session.get('role')
        or 'caregiver'
    )
    return 'child' if str(role).lower() == 'child' else 'caregiver'


def _summarize_history(messages, limit=10, user_label='Caregiver'):
    recent = messages[-limit:]
    lines = []
    for message in recent:
        role = user_label if message.get('sender') == 'user' else 'NIA'
        text = message.get('text', '').strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _new_chat_thread(child_name):
    return {
        'id': uuid.uuid4().hex,
        'title': f"Chat with {child_name}",
        'messages': [],
    }


def _handled_chat_requests(request):
    return request.session.setdefault('handled_chat_requests', {})

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

    child_threads = _child_thread_bucket(request, active_child.get('id'))
    requested_thread_id = request.GET.get('conversation')
    active_thread = None
    for thread in child_threads:
        if thread.get('id') == requested_thread_id:
            active_thread = thread
            break

    if not active_thread:
        if request.GET.get('new') == '1' or not child_threads:
            active_thread = _new_chat_thread(active_child.get('name'))
            child_threads.insert(0, active_thread)
            request.session.modified = True
        else:
            active_thread = child_threads[0]

    audience = _chat_audience(request)
    user_label = 'Child' if audience == 'child' else 'Caregiver'

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            query = body.get('message', '').strip()
            conversation_id = body.get('conversation_id')
            request_id = body.get('request_id')
        except Exception:
            return JsonResponse({'error': 'Invalid request payload'}, status=400)

        if not query:
            return JsonResponse({'error': 'Query cannot be empty'}, status=400)

        handled_requests = _handled_chat_requests(request)
        duplicate_key = f"{active_child.get('id')}:{conversation_id}:{request_id}" if request_id else None
        if duplicate_key and duplicate_key in handled_requests:
            return JsonResponse(handled_requests[duplicate_key])

        for thread in child_threads:
            if thread.get('id') == conversation_id:
                active_thread = thread
                break
        else:
            active_thread = _new_chat_thread(active_child.get('name'))
            child_threads.insert(0, active_thread)

        previous_messages = list(active_thread.get('messages', []))

        # Personalize system instructions
        child_profile_str = f"Name: {active_child.get('name')}, DOB/Age: {active_child.get('dob')}, Concern/Diagnosis: {active_child.get('concern')}, Language: {active_child.get('language')}"
        caregiver_profile_str = f"Caregiver ID: {caregiver_id}"
        conversation_history = _summarize_history(previous_messages, user_label=user_label)

        # Load QA RAG chain
        qa_chain = get_qa_chain(
            use_global_db=False,
            child_profile=child_profile_str,
            caregiver_profile=caregiver_profile_str,
            child_id=str(active_child.get('id')),
            conversation_history=conversation_history,
            audience=audience
        )
        response = query_system(query, qa_chain)

        active_thread.setdefault('messages', []).append({'sender': 'user', 'text': query})
        active_thread.setdefault('messages', []).append({'sender': 'nia', 'text': response})
        if len(active_thread['messages']) == 2:
            active_thread['title'] = query[:48] + ('...' if len(query) > 48 else '')
        child_threads.remove(active_thread)
        child_threads.insert(0, active_thread)
        request.session.modified = True

        response_payload = {
            'response': response,
            'conversation_id': active_thread.get('id'),
            'title': active_thread.get('title'),
        }
        if duplicate_key:
            handled_requests[duplicate_key] = response_payload
            # Keep the session payload small while still de-duping recent retries.
            if len(handled_requests) > 25:
                oldest_key = next(iter(handled_requests))
                handled_requests.pop(oldest_key, None)
            request.session.modified = True

        return JsonResponse(response_payload)

    context = {
        'active_child': active_child,
        'children': children,
        'chat_threads': child_threads,
        'active_thread': active_thread,
        'chat_audience': audience,
    }
    return render(request, 'chatbot.html', context)

