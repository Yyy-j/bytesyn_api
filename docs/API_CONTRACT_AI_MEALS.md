# Text meal nutrition estimation

## POST /ai/meals/analyze-text

Requires `Authorization: Bearer <access_token>`, validated by the existing JWT
users.id dependency. Pair membership is not required. This endpoint neither
reads nor writes meals and does not save the estimate automatically.

Request:

```json
{"text":"半碗米饭，一块三文鱼，一点沙拉"}
```

`text` is required, trimmed, and must contain 1..2000 characters after trimming.
Empty/whitespace-only input, non-string input and extra fields return 422.

Success: 200, example shape (actual values depend on Gemini):

```json
{
  "name": "三文鱼套餐",
  "calories": 500,
  "protein": 30,
  "carbs": 45,
  "fat": 20,
  "dishes": [
    {"name":"米饭","calories":200},
    {"name":"三文鱼","calories":250},
    {"name":"沙拉","calories":50}
  ],
  "source": "text"
}
```

Calories use kcal; protein/carbs/fat use grams. Integer or fractional JSON numbers
are supported. All nutrition values, including dish calories, must be finite and
nonnegative. Numeric strings, booleans, NaN and infinity are rejected. Meal/dish
names are nonblank strings of at most 255 characters. The dishes array is required
and contains 1..50 validated objects. Unexpected AI fields are rejected.
`source` is set by the server, never taken from model output.

Gemini structured output passes MealEstimate.model_json_schema() through
response_json_schema, preserving JSON Schema keywords such as additionalProperties
and nested dish definitions without SDK Schema-field conversion. The returned raw JSON
is independently validated with MealEstimate.model_validate_json before building
the API response; schema guidance alone is not trusted. Food descriptions are
passed as user content, separate from system instructions. The prompt requests
portion-aware estimates and consistent dish totals; calorie/dish equality and
nutrition accuracy are not guaranteed by structural validation.

## Controlled errors

| Status | Body | Meaning |
| --- | --- | --- |
| 401 | `{"detail":"Invalid authentication credentials"}` | Missing/invalid/expired Bearer JWT |
| 422 | Standard FastAPI validation detail | Invalid request |
| 503 | `{"detail":"AI service unavailable"}` | GEMINI_API_KEY missing or blank |
| 502 | `{"detail":"AI analysis failed"}` | SDK/network/timeout/quota/provider failure |
| 502 | `{"detail":"Invalid AI response"}` | Empty, malformed or schema-invalid AI output |

No upstream exception text, raw AI output, API key or stack trace is returned.
Blocked/refused/non-food responses without a valid estimate are handled as AI
failure or invalid response; there is no fabricated fallback estimate.

## Configuration and implementation

```dotenv
GEMINI_API_KEY=<your Google Gemini API key>
AI_MODEL=gemini-3.6-flash
```

The model defaults to gemini-3.6-flash if AI_MODEL is unset/blank. The key is read
explicitly from GEMINI_API_KEY. Only gemini-2.5-flash and gemini-2.5-flash-lite
receive thinking_budget=0; other models use provider defaults. Model names with
the models/ prefix are supported. Gemini 2.5 Pro cannot disable thinking, as
documented in Google's [thinking configuration guide](https://ai.google.dev/gemini-api/docs/generate-content/thinking).
Add these variables to the deployment environment
(.env.runtime on the NAS) and recreate the API container after building the new
image. No secret is committed and no migration is needed. Missing AI configuration
does not prevent Auth, Meals or Summary from starting.

The official [Google Gen AI Python SDK](https://github.com/googleapis/python-genai)
is declared in requirements.txt. GeminiProvider owns client construction and
calling models.generate_content, with JSON response schema, a 30,000 ms HTTP
timeout and one attempt (no automatic retries). The client is closed after each
call. The router only authenticates, validates input/output and maps errors.
Implementation follows Google's [structured output documentation](https://ai.google.dev/gemini-api/docs/structured-output).

Image recognition is documented separately in
[API_CONTRACT_AI_IMAGES.md](API_CONTRACT_AI_IMAGES.md). No refinement, meal
persistence, Flutter changes or production mock is included.

## Automated verification

2026-09-13 compatibility repair: 105 passed in 4.61s, comprising 36 AI cases
plus all 69 existing Meals/Summary regression cases.
Two existing test-dependency deprecation warnings, no failures.
AI endpoint tests inject a fake provider defined only in tests. Adapter tests
use the actual google-genai 1.75.0 SDK with httpx.MockTransport to verify local
request/schema conversion without network requests. Tests run in the isolated
PostgreSQL container network with no external network access or real Gemini key.

Coverage: success, text trimming/validation, authentication before inference,
controlled provider failure, malformed/missing/negative/non-finite values,
invalid dish data, fixed source, missing key, model default, SDK timeout/retry
configuration and sanitized adapter errors.

Additional adapter coverage checks blank model fallback, whitespace trimming,
models/ prefixes, Flash Lite, Pro without a forced thinking budget, and a
synthetic model name for configuration passthrough. Synthetic names do not
assert availability in Gemini. The repair was deployed on 2026-09-13 and a live
Gemini request using gemini-3.6-flash returned a schema-valid meal estimate.
