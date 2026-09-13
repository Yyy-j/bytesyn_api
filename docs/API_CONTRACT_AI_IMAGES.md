# Image meal nutrition estimation

## POST /ai/meals/analyze-image

Requires `Authorization: Bearer <access_token>`, validated by the existing JWT
dependency. The request uses `multipart/form-data`:

- `image`: required file; accepted media types are `image/jpeg`, `image/png` and
  `image/webp`.
- `hint`: optional text. Surrounding whitespace is removed; blank text is treated
  as absent.

The maximum image size is 5 MiB (5 × 1024 × 1024 bytes). The endpoint validates
both the declared media type and the JPEG, PNG or WebP file signature. It reads at
most 5 MiB plus one byte, closes the upload object, and passes only in-memory bytes
to Gemini. It does not write PostgreSQL, create an image URL, retain base64, or
permanently save the image.

Success: 200

```json
{
  "name": "鸡肉便当",
  "calories": 500,
  "protein": 30,
  "carbs": 50,
  "fat": 20,
  "dishes": [
    {"name":"米饭","calories":220},
    {"name":"鸡肉","calories":230},
    {"name":"酱汁","calories":50}
  ],
  "source": "ai"
}
```

The nutrition fields reuse `MealEstimate`. Image results allow 1..10 meaningful
dishes. A genuinely single food can have one dish; compound foods should be split
without inventing components. `source` is always set by the server to the Flutter
wire value `ai`.

## Controlled errors

| Status | Body | Meaning |
| --- | --- | --- |
| 400 | `{"detail":"Invalid image format"}` | Unsupported media type or mismatched/invalid signature |
| 401 | `{"detail":"Invalid authentication credentials"}` | Missing, invalid or expired Bearer JWT |
| 413 | `{"detail":"Image too large"}` | File exceeds 5 MiB |
| 422 | Standard FastAPI validation detail | Missing `image` or malformed multipart request |
| 503 | `{"detail":"AI service unavailable"}` | `GEMINI_API_KEY` is missing or blank |
| 502 | `{"detail":"AI analysis failed"}` | Gemini SDK, network, timeout, quota or provider failure |
| 502 | `{"detail":"Invalid AI response"}` | Empty, malformed, schema-invalid, or over-10-dish AI output |

The response never includes Gemini error text, the API key, prompt, raw AI output,
or a stack trace.

## Gemini call

`GeminiProvider.analyze_image(image_bytes, mime_type, hint=None)` uses the same
`GEMINI_API_KEY` and `AI_MODEL` configuration as text analysis. The request sends
the image as a Gemini inline-data part and the optional hint as a separate user
text part. The hint is never interpolated into the system instruction.

The image prompt estimates the visible amount, uses reasonable common portions
when exact weight is unknown, considers non-conflicting hints, prefers readable
nutrition labels, limits the breakdown to ten meaningful components, and avoids
invented brands, exact weights, cooking methods, or dietary and medical advice.
The response uses Gemini structured output with a JSON schema derived from
`MealEstimate`; the raw response is independently validated before it becomes the
API response. No markdown or fallback string parser is used.

## curl example

```bash
BASE_URL=http://127.0.0.1:8000
IMAGE_PATH=/path/to/meal.jpg
read -rsp 'Bearer JWT: ' TOKEN
printf '\n'

curl --fail-with-body -sS \
  -X POST "$BASE_URL/ai/meals/analyze-image" \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@$IMAGE_PATH;type=image/jpeg" \
  -F 'hint=米饭只有半碗，没有吃鸡皮' | jq .

unset TOKEN
```

Omit the final `-F 'hint=...'` line when no hint is needed. Use the matching
`image/png` or `image/webp` type for those formats.

## Automated verification

Tests use an injected fake image provider or the real Google Gen AI SDK with an
`httpx.MockTransport`; they never contact Gemini. Coverage includes JPEG, PNG,
WebP, hint/no-hint behavior, authentication, MIME and signature rejection, the
5 MiB limit, controlled provider errors, invalid AI JSON, the 10-dish limit,
fixed `source: ai`, inline image bytes, shared model configuration, structured
output, and sanitized SDK failures.
