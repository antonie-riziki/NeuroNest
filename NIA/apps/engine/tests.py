import json
from unittest.mock import patch

from django.test import Client, TestCase
from langchain_core.prompts import PromptTemplate

from apps.engine.prompt_builder import prompt_template_func


FAKE_CHILDREN = [
    {
        'id': 'child-1',
        'name': 'Brian',
        'dob': '2018-01-01',
        'concern': 'sensory overwhelm',
        'language': 'English',
        'profile_picture_url': '',
    }
]


class FakeSupabaseClient:
    def get_children(self, caregiver_id, token):
        return FAKE_CHILDREN


class PromptBuilderTests(TestCase):
    def test_prompt_escapes_dynamic_braces_and_keeps_langchain_slots(self):
        prompt = prompt_template_func(
            child_profile='Name: {Brian}',
            caregiver_profile='Caregiver: {A}',
            conversation_history='Caregiver: likes {trains}',
            audience='caregiver',
        )
        template = PromptTemplate(template=prompt, input_variables=['context', 'question'])
        formatted = template.format(context='retrieved context', question='What helps?')

        self.assertIn('Name: {Brian}', formatted)
        self.assertIn('Caregiver: {A}', formatted)
        self.assertIn('likes {trains}', formatted)
        self.assertIn('retrieved context', formatted)
        self.assertIn('What helps?', formatted)

    def test_prompt_footer_instruction_is_before_answer_slot(self):
        prompt = prompt_template_func(audience='child')

        self.assertLess(prompt.index('Required footer:'), prompt.index('Question: {question}'))
        self.assertTrue(prompt.rstrip().endswith('Answer:'))


class ChatViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session['access_token'] = 'token'
        session['caregiver_id'] = 'caregiver-1'
        session['caregiver_name'] = 'Caregiver One'
        session.save()

    @patch('apps.engine.views.SupabaseClient', FakeSupabaseClient)
    def test_chat_window_defaults_to_caregiver_copy(self):
        response = self.client.get('/chat/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profile ready")
        self.assertContains(response, 'Chat history')

    @patch('apps.engine.views.query_system', return_value='**Try this:**\n- Take one quiet breath.\n\nWhat happened right before it started?')
    @patch('apps.engine.views.get_qa_chain', return_value=object())
    @patch('apps.engine.views.SupabaseClient', FakeSupabaseClient)
    def test_chat_post_returns_response_and_persists_thread(self, mock_chain, mock_query):
        response = self.client.post(
            '/chat/',
            data=json.dumps({
                'message': 'What can help with sensory overload?',
                'conversation_id': 'missing-thread',
                'request_id': 'request-1',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('Try this', payload['response'])
        self.assertTrue(payload['conversation_id'])
        self.assertEqual(mock_chain.call_args.kwargs['audience'], 'caregiver')

        session = self.client.session
        threads = session['chat_threads']['child-1']
        self.assertEqual(threads[0]['messages'][0]['text'], 'What can help with sensory overload?')
        self.assertEqual(threads[0]['messages'][1]['text'], payload['response'])

    @patch('apps.engine.views.query_system', return_value='One cached answer')
    @patch('apps.engine.views.get_qa_chain', return_value=object())
    @patch('apps.engine.views.SupabaseClient', FakeSupabaseClient)
    def test_duplicate_chat_request_reuses_previous_response(self, mock_chain, mock_query):
        body = {
            'message': 'Help me with bedtime',
            'conversation_id': 'same-thread',
            'request_id': 'same-request',
        }
        first = self.client.post('/chat/', data=json.dumps(body), content_type='application/json')
        second = self.client.post('/chat/', data=json.dumps(body), content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(mock_query.call_count, 1)
