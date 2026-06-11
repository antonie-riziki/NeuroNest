import json
import urllib.request
import urllib.error
import uuid
from django.conf import settings

class SupabaseClient:
    def __init__(self):
        self.url = getattr(settings, 'SUPABASE_URL', '')
        self.key = getattr(settings, 'SUPABASE_KEY', '')

    def _request(self, method, path, headers=None, body=None, is_json=True, raw_data=None):
        if not self.url or not self.key:
            raise ValueError("Supabase configuration is missing URL or Key.")
        
        url = f"{self.url.rstrip('/')}/{path.lstrip('/')}"
        
        req_headers = {
            'apikey': self.key,
            'Authorization': f'Bearer {self.key}',
        }
        if headers:
            req_headers.update(headers)
            
        data = None
        if raw_data is not None:
            data = raw_data
        elif body is not None:
            data = json.dumps(body).encode('utf-8')
            if 'Content-Type' not in req_headers:
                req_headers['Content-Type'] = 'application/json'
                
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        
        try:
            with urllib.request.urlopen(req) as response:
                resp_data = response.read()
                if is_json and resp_data:
                    return json.loads(resp_data.decode('utf-8'))
                return resp_data.decode('utf-8') if resp_data else None
        except urllib.error.HTTPError as e:
            err_data = e.read()
            try:
                err_json = json.loads(err_data.decode('utf-8'))
                err_msg = err_json.get('msg') or err_json.get('message') or err_json.get('error_description') or str(e)
            except Exception:
                err_msg = err_data.decode('utf-8') or str(e)
            raise Exception(err_msg)
        except Exception as e:
            raise Exception(str(e))

    def signup(self, email, password, full_name, phone):
        # 1. Sign up user via GoTrue Auth
        path = "auth/v1/signup"
        body = {
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name,
                "phone": phone
            }
        }
        res = self._request("POST", path, body=body)
        user = res.get('user', {})
        user_id = user.get('id')
        access_token = res.get('access_token')
        
        # 2. Insert into public.caregivers table
        if user_id:
            try:
                # Use access token if available, otherwise fallback to anon key headers (handled by client init)
                headers = {'Authorization': f'Bearer {access_token}'} if access_token else {}
                self.create_caregiver_profile(user_id, email, full_name, phone, headers=headers)
            except Exception as e:
                print(f"Error creating caregiver profile: {e}")
                
        return res

    def signin(self, email, password):
        path = "auth/v1/token?grant_type=password"
        body = {
            "email": email,
            "password": password
        }
        return self._request("POST", path, body=body)

    def create_caregiver_profile(self, user_id, email, full_name, phone, headers=None):
        path = "rest/v1/caregivers"
        body = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "phone": phone
        }
        req_headers = {'Prefer': 'return=representation'}
        if headers:
            req_headers.update(headers)
        return self._request("POST", path, headers=req_headers, body=body)

    def get_caregiver_profile(self, user_id, token):
        path = f"rest/v1/caregivers?id=eq.{user_id}"
        headers = {'Authorization': f'Bearer {token}'}
        res = self._request("GET", path, headers=headers)
        return res[0] if res else None

    def get_children(self, caregiver_id, token):
        path = f"rest/v1/children?caregiver_id=eq.{caregiver_id}&select=*"
        headers = {'Authorization': f'Bearer {token}'}
        return self._request("GET", path, headers=headers)

    def add_child(self, caregiver_id, name, dob, concern, language, profile_picture_url, token):
        path = "rest/v1/children"
        body = {
            "caregiver_id": caregiver_id,
            "name": name,
            "dob": dob,
            "concern": concern,
            "language": language,
            "profile_picture_url": profile_picture_url
        }
        headers = {
            'Authorization': f'Bearer {token}',
            'Prefer': 'return=representation'
        }
        return self._request("POST", path, headers=headers, body=body)

    def upload_avatar(self, file_name, file_data, mime_type, token):
        # Clean file name to avoid path traversal / issues
        ext = file_name.split('.')[-1] if '.' in file_name else 'png'
        unique_name = f"{uuid.uuid4()}.{ext}"
        path = f"storage/v1/object/child-profiles/{unique_name}"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': mime_type
        }
        
        # Upload object
        self._request("POST", path, headers=headers, raw_data=file_data, is_json=True)
        
        # Get public url
        public_url = f"{self.url.rstrip('/')}/storage/v1/object/public/child-profiles/{unique_name}"
        return public_url
