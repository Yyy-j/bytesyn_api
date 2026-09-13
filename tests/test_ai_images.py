import base64
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import types

from app.ai.gemini_provider import (
    AIProviderFailure, AIUnavailable, GeminiProvider, get_image_meal_provider,
)
from app.main import app
from conftest import headers

PATH = '/ai/meals/analyze-image'
JPEG = b'\xff\xd8\xff\xe0test-jpeg'
PNG = b'\x89PNG\r\n\x1a\ntest-png'
WEBP = b'RIFF\x08\x00\x00\x00WEBPtest-webp'
ESTIMATE = {'name':'鸡肉便当', 'calories':500, 'protein':30, 'carbs':50, 'fat':20,
            'dishes':[{'name':'米饭','calories':220}, {'name':'鸡肉','calories':230},
                      {'name':'酱汁','calories':50}]}


class FakeImageProvider:
    def __init__(self):
        self.result = json.dumps(ESTIMATE)
        self.error = None
        self.calls = []

    def analyze_image(self, image_bytes, mime_type, hint=None):
        self.calls.append((image_bytes, mime_type, hint))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def image_client():
    fake = FakeImageProvider()
    app.dependency_overrides[get_image_meal_provider] = lambda: fake
    try:
        with TestClient(app) as client:
            yield client, fake
    finally:
        app.dependency_overrides.pop(get_image_meal_provider, None)


@pytest.mark.parametrize(('content', 'mime_type'), [
    (JPEG, 'image/jpeg'),
    (PNG, 'image/png'),
    (WEBP, 'image/webp'),
])
def test_valid_image_success(image_client, content, mime_type):
    client, fake = image_client
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal', content, mime_type)})
    assert response.status_code == 200, response.text
    assert response.json() == dict(ESTIMATE, source='ai')
    assert fake.calls == [(content, mime_type, None)]


def test_hint_is_trimmed_and_passed_to_provider(image_client):
    client, fake = image_client
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal.jpg', JPEG, 'image/jpeg')},
                           data={'hint':' 米饭只有半碗 '})
    assert response.status_code == 200
    assert fake.calls == [(JPEG, 'image/jpeg', '米饭只有半碗')]


def test_blank_hint_becomes_none(image_client):
    client, fake = image_client
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal.jpg', JPEG, 'image/jpeg')},
                           data={'hint':'   '})
    assert response.status_code == 200
    assert fake.calls == [(JPEG, 'image/jpeg', None)]


def test_image_requires_authentication(image_client):
    client, fake = image_client
    response = client.post(PATH, files={'image':('meal.jpg', JPEG, 'image/jpeg')})
    assert response.status_code == 401
    assert fake.calls == []


def test_image_is_required(image_client):
    client, fake = image_client
    response = client.post(PATH, headers=headers(uuid4()), data={'hint':'米饭半碗'})
    assert response.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(('content', 'mime_type'), [
    (JPEG, 'application/octet-stream'),
    (b'not-an-image', 'image/jpeg'),
])
def test_invalid_image_format_is_rejected(image_client, content, mime_type):
    client, fake = image_client
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal', content, mime_type)})
    assert response.status_code == 400
    assert response.json() == {'detail':'Invalid image format'}
    assert fake.calls == []


def test_image_over_five_mb_is_rejected(image_client):
    client, fake = image_client
    content = b'\xff\xd8\xff' + b'x' * (5 * 1024 * 1024 - 2)
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('large.jpg', content, 'image/jpeg')})
    assert response.status_code == 413
    assert response.json() == {'detail':'Image too large'}
    assert fake.calls == []


def test_image_provider_unavailable_is_controlled(image_client):
    client, fake = image_client
    fake.error = AIUnavailable()
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal.jpg', JPEG, 'image/jpeg')})
    assert response.status_code == 503
    assert response.json() == {'detail':'AI service unavailable'}


def test_image_provider_requires_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(AIUnavailable):
        GeminiProvider().analyze_image(JPEG, 'image/jpeg')


def test_image_provider_failure_is_sanitized(image_client):
    client, fake = image_client
    fake.error = RuntimeError('upstream error GEMINI_API_KEY=secret')
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal.jpg', JPEG, 'image/jpeg')})
    assert response.status_code == 502
    assert response.json() == {'detail':'AI analysis failed'}
    assert 'secret' not in response.text


@pytest.mark.parametrize('raw', [
    'not JSON', '{}',
    json.dumps(ESTIMATE | {'dishes':[{'name':str(i), 'calories':1} for i in range(11)]}),
])
def test_malformed_image_ai_result_is_rejected(image_client, raw):
    client, fake = image_client
    fake.result = raw
    response = client.post(PATH, headers=headers(uuid4()),
                           files={'image':('meal.jpg', JPEG, 'image/jpeg')})
    assert response.status_code == 502
    assert response.json() == {'detail':'Invalid AI response'}


def test_real_image_sdk_adapter_uses_inline_bytes(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-only')
    monkeypatch.setenv('AI_MODEL', 'gemini-3.6-flash')
    original_client = genai.Client
    requests = []

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        parts = body['contents'][0]['parts']
        assert parts[0]['inlineData']['mimeType'] == 'image/jpeg'
        assert base64.urlsafe_b64decode(parts[0]['inlineData']['data']) == JPEG
        assert '米饭只有半碗' in parts[1]['text']
        assert '米饭只有半碗' not in body['systemInstruction']['parts'][0]['text']
        schema = body['generationConfig']['responseJsonSchema']
        assert schema['properties']['dishes']['maxItems'] == 10
        assert body['generationConfig'].get('thinkingConfig') is None
        assert request.url.path.endswith('/models/gemini-3.6-flash:generateContent')
        return httpx.Response(200, json={'candidates':[{'content':{'role':'model',
            'parts':[{'text':json.dumps(ESTIMATE)}]}, 'finishReason':'STOP'}]})

    def client_factory(**kwargs):
        options = kwargs['http_options']
        assert options.timeout == 30000 and options.retry_options.attempts == 1
        kwargs['http_options'] = types.HttpOptions(timeout=options.timeout,
            retry_options=options.retry_options, client_args={'transport':httpx.MockTransport(handle)})
        return original_client(**kwargs)

    monkeypatch.setattr(genai, 'Client', client_factory)
    result = GeminiProvider().analyze_image(JPEG, 'image/jpeg', '米饭只有半碗')
    assert json.loads(result) == ESTIMATE
    assert len(requests) == 1


def test_image_sdk_failure_is_sanitized(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-only')
    monkeypatch.setattr(genai, 'Client', lambda **kwargs: (_ for _ in ()).throw(
        RuntimeError('sensitive upstream error')))
    with pytest.raises(AIProviderFailure) as caught:
        GeminiProvider().analyze_image(JPEG, 'image/jpeg')
    assert str(caught.value) == ''
