# BiteSync V1 Feature Freeze

## Freeze status

BiteSync enters feature freeze after the Backend and Flutter changes in this
review are accepted. From that point forward, product work is limited to UI
reconstruction, visual polish, dark mode, copy, device adaptation, bug fixes,
tests, builds, and deployment. Changes to the frozen API contracts require a
demonstrated V1 blocker rather than feature expansion.

## Final GAP Review

The review covered the current FastAPI service, the current Flutter app, and
the legacy `BYTESYNC-develope` mini-program. Legacy functionality was treated
as reference material rather than a migration checklist.

- P0 resolved in this round: logout is available even while the mandatory
  Pair gate is active, and it clears the local JWT/auth state without deleting
  the Backend user or changing Pair membership.
- No unresolved P0 V1 launch blocker remains in the reviewed user paths.
- P1 resolved in this round: one external teaching-video URL per private
  exercise reference; a usable Profile/My page; visible logout; user-facing
  Pair member identity; and the Backend Pair query that previously returned
  empty display names and avatar URLs.
- P1 resolved in this round: the Pair details action now performs real
  navigation back to the main app instead of only changing an internal flag.
- P2: intentionally deferred items are recorded in `FUTURE_FEATURES.md`.
- Visual-only findings are recorded in `FINAL_UI_TODO.md`.

The final repository-level walkthrough covered this complete V1 path:
Login -> Pair -> Today -> Record -> AI -> save meal -> dual-person sharing ->
edit/delete -> Goals -> Training -> Template -> fixed/custom exercise ->
strength/duration/cardio -> check-in -> set edit -> History -> Video ->
Profile -> Logout. No remaining functional blocker was found in that path.

## Completed V1 capabilities

- Google authentication, local JWT session restore, expiry handling, logout.
- Private user profile with display name, avatar URL, and nutrition goals.
- Pair creation/joining, invite code, member status and partner identity.
- Meal CRUD, text/image AI analysis, refine/reuse, solo/shared portions,
  two-person daily summary, and personal goals.
- Training templates, weekly snapshots, explicit current-week sync, history,
  strength/duration/cardio items, set check-in/edit, fixed exercise catalog,
  custom exercise CRUD, and optional duration values in seconds.
- One user-private external teaching-video URL per fixed or custom exercise
  catalog reference. Opening is delegated to the device browser/app; BiteSync
  stores no video binary and performs no transcoding.

## Frozen Backend API range

- Auth and user: `POST /auth/google`; `GET|PATCH /users/me`.
- Pair: `POST /pairs`; `POST /pairs/join`; `GET /pairs/me`.
- Meals: `POST|GET /meals`; `GET /meals/recent`; `GET /meals/reuse`;
  `GET|PATCH|DELETE /meals/{meal_id}`.
- Meal AI and summary: `POST /ai/meals/analyze-text`;
  `POST /ai/meals/analyze-image`; `GET /summary/daily`.
- Training template and weeks: `GET|PUT /training/template`;
  `GET /training/weeks`; `GET /training/weeks/current`;
  `GET /training/weeks/{week_id}`; `POST /training/weeks/current/sync`.
- Training set records:
  `POST /training/weeks/{week_id}/items/{item_id}/sets` and
  `PATCH /training/weeks/{week_id}/items/{item_id}/sets/{request_id}`.
- Training catalog: `GET|POST /training/exercises/custom` and
  `PATCH|DELETE /training/exercises/custom/{exercise_id}`.
- Training videos: `GET /training/exercises/videos`;
  `PUT|DELETE /training/exercises/{exercise_id}/video`.

Training is user-private and is never shared through Pair. Weekly JSONB data
is a snapshot: catalog deletion or later catalog/video edits do not mutate
existing Template/Week/History facts.

The video contract stores one external `http`/`https` URL, at most 2048
characters, for each `(user_id, exercise_id)` pair. PUT is an upsert. Video
responses do not expose `user_id`, and every operation requires JWT auth.

## Frozen Flutter page range

- Login and authentication routing.
- Today summary and meal management/record/AI result flows.
- Pair create/join/status page.
- Training current week, template, fixed/custom picker, set check-in/edit,
  history, and external teaching-video actions.
- Nutrition goals and Profile/My page.
- Four-tab bottom navigation: Today, Record, Training, My.

## Explicitly out of V1

No distance, pace, speed, GPS, heart rate, countdown timer, social feed, chat,
notifications, subscriptions, image-upload infrastructure, training-video
upload/transcoding, or new AI capability is part of the frozen V1 contract.
Richer multi-video objects, titles/thumbnails, and in-app playback are also P2.

## Allowed post-freeze work

- UI/visual redesign and dark mode.
- Layout, copy, accessibility, and real-device adaptation.
- Bug fixes that preserve the frozen product scope.
- Test, build, release, migration execution, and deployment work.
