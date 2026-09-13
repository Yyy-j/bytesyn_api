import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import types

from app.ai.gemini_provider import AIProviderFailure, GeminiProvider, get_text_meal_provider
from app.main import app
from conftest import headers

PATH = '/ai/meals/analyze-text'
ESTIMATE = {'name':'三文鱼套餐', 'calories':500, 'protein':30, 'carbs':45, 'fat':20,
            'dishes':[{'name':'米饭','calories':200}, {'name':'三文鱼','calories':250},
                      {'name':'沙拉','calories':50}]}


class FakeProvider:
    def __init__(self):
        self.result = json.dumps(ESTIMATE)
        self.error = None
        self.calls = []

    def analyze_text(self, text):
        self.calls.append(text)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def ai_client():
    fake = FakeProvider()
    app.dependency_overrides[get_text_meal_provider] = lambda: fake
    try:
        with TestClient(app) as client:
            yield client, fake
    finally:
        app.dependency_overrides.pop(get_text_meal_provider, None)


def test_analyze_success(ai_client):
    client, fake = ai_client
    response = client.post(PATH, headers=headers(uuid4()), json={'text':' 半碗米饭，一块三文鱼，一点沙拉 '})
    assert response.status_code == 200, response.text
    assert response.json() == dict(ESTIMATE, source='text')
    assert fake.calls == ['半碗米饭，一块三文鱼，一点沙拉']


@pytest.mark.parametrize('body', [{'text':''}, {'text':' \n '}, {}, {'text':None},
    {'text':123}, {'text':'a'*2001}, {'text':'米饭', 'user_id':str(uuid4())}])
def test_invalid_text(ai_client, body):
    client, fake = ai_client
    assert client.post(PATH, headers=headers(uuid4()), json=body).status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize('auth', [{}, {'Authorization':'Bearer invalid'}])
def test_analyze_unauthenticated(ai_client, auth):
    client, fake = ai_client
    assert client.post(PATH, headers=auth, json={'text':'米饭'}).status_code == 401
    assert fake.calls == []


def test_analyze_failure(ai_client):
    client, fake = ai_client
    fake.error = RuntimeError('upstream stack trace GEMINI_API_KEY=secret')
    response = client.post(PATH, headers=headers(uuid4()), json={'text':'米饭'})
    assert response.status_code == 502
    assert response.json() == {'detail':'AI analysis failed'}


@pytest.mark.parametrize('raw', ['', 'not JSON', '{}', 'null', '[]',
    json.dumps(ESTIMATE | {'calories':-1}),
    json.dumps(ESTIMATE | {'protein':'30'}),
    json.dumps(ESTIMATE | {'carbs':True}),
    json.dumps(ESTIMATE | {'fat':float('inf')}),
    json.dumps(ESTIMATE | {'fat':float('nan')}),
    json.dumps(ESTIMATE | {'name':' '}),
    json.dumps(ESTIMATE | {'dishes':[]}),
    json.dumps(ESTIMATE | {'dishes':[{'name':'米饭','calories':-1}]}),
    json.dumps(ESTIMATE | {'source':'ai'}),
])
def test_malformed_ai_result(ai_client, raw):
    client, fake = ai_client
    fake.result = raw
    response = client.post(PATH, headers=headers(uuid4()), json={'text':'米饭'})
    assert response.status_code == 502
    assert response.json() == {'detail':'Invalid AI response'}


def test_missing_key_is_controlled(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with TestClient(app) as client:
        response = client.post(PATH, headers=headers(uuid4()), json={'text':'米饭'})
    assert response.status_code == 503
    assert response.json() == {'detail':'AI service unavailable'}


@pytest.mark.parametrize('model, expected_model, disable_thinking', [
    (None, 'gemini-3.6-flash', False),
    ('', 'gemini-3.6-flash', False),
    ('   ', 'gemini-3.6-flash', False),
    ('gemini-2.5-flash', 'gemini-2.5-flash', True),
    (' models/gemini-2.5-flash ', 'gemini-2.5-flash', True),
    ('gemini-2.5-flash-lite', 'gemini-2.5-flash-lite', True),
    ('gemini-2.5-pro', 'gemini-2.5-pro', False),
    ('models/gemini-2.5-pro', 'gemini-2.5-pro', False),
    # Synthetic model name tests passthrough, not upstream model availability.
    ('gemini-3.6-flash', 'gemini-3.6-flash', False),
])
def test_real_sdk_adapter_with_fake_transport(monkeypatch, model, expected_model, disable_thinking):
    # Exercises SDK request/schema conversion without sending any network traffic.
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-only')
    if model is None:
        monkeypatch.delenv('AI_MODEL', raising=False)
    else:
        monkeypatch.setenv('AI_MODEL', model)
    original_client = genai.Client
    requests = []

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body['contents'][0]['parts'][0]['text'] == '米饭'
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert 'responseSchema' not in body['generationConfig']
        schema = body['generationConfig']['responseJsonSchema']
        assert schema['additionalProperties'] is False
        assert schema['$defs']['DishEstimate']['additionalProperties'] is False
        assert 'additional_properties' not in json.dumps(schema)
        assert request.url.path.endswith(f'/models/{expected_model}:generateContent')
        if disable_thinking:
            # SDK releases use either protobuf field names or JSON aliases.
            assert body['generationConfig']['thinkingConfig'] in (
                {'thinking_budget': 0}, {'thinkingBudget': 0},
            )
        else:
            assert body['generationConfig'].get('thinkingConfig') is None
        return httpx.Response(200, json={'candidates':[{'content':{'role':'model',
            'parts':[{'text':json.dumps(ESTIMATE)}]}, 'finishReason':'STOP'}]})

    def client_factory(**kwargs):
        options = kwargs['http_options']
        assert options.timeout == 30000 and options.retry_options.attempts == 1
        assert kwargs['api_key'] == 'test-key-only' and kwargs['vertexai'] is False
        kwargs['http_options'] = types.HttpOptions(timeout=options.timeout,
            retry_options=options.retry_options, client_args={'transport':httpx.MockTransport(handle)})
        return original_client(**kwargs)

    monkeypatch.setattr(genai, 'Client', client_factory)
    assert json.loads(GeminiProvider().analyze_text('米饭')) == ESTIMATE
    assert len(requests) == 1


def test_sdk_failure_is_sanitized(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-only')
    def broken_client(**kwargs):
        raise RuntimeError('sensitive upstream error')
    monkeypatch.setattr(genai, 'Client', broken_client)
    with pytest.raises(AIProviderFailure) as caught:
        GeminiProvider().analyze_text('米饭')
    assert str(caught.value) == ''
