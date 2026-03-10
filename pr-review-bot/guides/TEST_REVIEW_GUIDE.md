# Test Review Guide — taleemabad-core

This guide is for an LLM reviewing Django/pytest test files in GitHub PRs.
Read this guide fully, then review the diff, then output JSON as described at the end.

---

## CONTEXT

- Project: taleemabad-core — Django 4.2, DRF 3.14, **pytest + pytest-django** (NOT Django's `unittest`)
- Test framework: pure pytest classes with `@pytest.mark.django_db` — no `unittest.TestCase` base class (except rare legacy files)
- Test client: `APITenantClient` (a DRF `APIClient` subclass) provided by the `client` fixture in global `conftest.py`
- Global fixtures (auto-applied): `with_tenant_context` (sets test schema), `clear_cache`, `media_storage`
- Test data: factory-boy ONLY — never `.objects.create()` in tests (see exceptions in Rule 5)
- Tests live in: `taleemabad_core/apps/<app_name>/tests/`
- Auth in tests: always `client.force_authenticate(user=user)` — never `force_login()`
- Run tests: `make test` or `docker compose -f local.yml run --rm django pytest <path> -v`

---

## RULE 1 — Folder Structure

REQUIRED layout for any app with non-trivial tests:
```
tests/
├── factories.py           ← all factories for this app
├── conftest.py            ← shared fixtures used by multiple test files
├── base/
│   ├── constants.py       ← URL strings, expected key sets, magic values
│   ├── helpers.py         ← data-setup functions (create_X, build_Y)
│   └── assertions.py      ← reusable assertion functions
└── views/
    └── <feature>/
        ├── test_authentication.py
        ├── test_response_structure.py
        ├── test_data_content.py
        └── test_<concern>.py
```

VIOLATION examples:
- All tests in one file `test_views.py` or `test_api.py`
- Test files directly under `tests/` without `views/<feature>/` subdirectory split
- No `base/` directory when helpers/constants are needed

---

## RULE 2 — URL Constants Must Be in base/constants.py

VIOLATION: URL string hardcoded inside a test file
```python
response = client.post("/users/login/", data)          # WRONG
response = client.get("/api/v2/sync-courses/")         # WRONG
self.url = reverse("users:login")                       # WRONG — reverse() breaks at import
```

CORRECT:
```python
# In base/constants.py:
LOGIN_URL = "/users/login/"

# In test file:
from ..base.constants import LOGIN_URL
response = client.post(LOGIN_URL, data)
```

Flag any URL string literal (starting with `/`) found directly in a test method or setup fixture.

---

## RULE 3 — No Duplicate Private Helpers Across Files

VIOLATION: The same private method defined in multiple test classes across different files:
```python
# In test_file_a.py:
def _get_profile_data(self): ...

# In test_file_b.py:
def _get_profile_data(self): ...   # WRONG — duplicated
```

CORRECT: Extract to `base/helpers.py` and import in both files.

Rule: If ANY helper method appears with the same name in 2+ different test files, it belongs in `base/helpers.py`.

Common duplicate helpers to flag: `_get_profile_data`, `_get_sync_response`, `_get_participant_data`, `_make_fresh_client`, `_get_gq_from_response`, `_get_training`, `_get_level`, `_get_course`.

---

## RULE 4 — Reusable Assertions Must Be in base/assertions.py

VIOLATION: Same assertion pattern copy-pasted in multiple test methods:
```python
# In test A:
assert "created" in section
assert "updated" in section
assert "deleted" in section

# In test B:
assert "created" in section   # WRONG — duplicated
assert "updated" in section
assert "deleted" in section
```

CORRECT: Extract to `base/assertions.py`:
```python
def assert_sync_section_structure(section):
    assert "created" in section
    assert "updated" in section
    assert "deleted" in section
```

---

## RULE 5 — Always Use Factories, Never .objects.create()

VIOLATION: Using Django ORM directly to create test data:
```python
Assessment.objects.create(profile=..., score=80)           # WRONG
TeacherTrainingStatus.objects.create(profile=..., ...)     # WRONG
GrandQuiz.objects.create(level=level, title="...")          # WRONG (unless justified)
```

CORRECT:
```python
AssessmentFactory(profile=teacher_profile, score=80)
TeacherTrainingStatusFactory(profile=teacher_profile, ...)
```

If a factory does not exist yet for a model, flag it: "Add `<Model>Factory` to `factories.py`".

Exception (do NOT flag): `GrandQuiz.objects.create(...)` is acceptable ONLY when the factory uses
`django_get_or_create = ["level", "type"]` and a unique instance is intentionally needed.
The test comment should say "# can't use factory due to django_get_or_create constraint".

---

## RULE 6 — @pytest.mark.django_db Is Required

VIOLATION: Test class that uses the database but has no marker:
```python
class TestUserViewSet:              # WRONG — missing @pytest.mark.django_db
    def test_get_queryset(self, user, rf):
        assert user in view.get_queryset()   # this queries the DB
```

CORRECT:
```python
@pytest.mark.django_db
class TestUserViewSet:
    ...
```

Flag any test class that uses model instances, factories, or database fixtures without `@pytest.mark.django_db`.

---

## RULE 7 — Test Naming Must Follow test_<what>_<condition>_<expected>

VIOLATION:
```python
def test_login(self): ...                # too vague
def test_successful_login(self): ...     # missing condition/expected format
def test_get_queryset(self): ...         # no condition or expected result
def test_me(self): ...                   # meaningless name
```

CORRECT:
```python
def test_login_with_valid_credentials_returns_200_and_tokens(self): ...
def test_login_with_wrong_password_returns_401(self): ...
def test_get_queryset_for_authenticated_user_returns_user_in_results(self): ...
```

Every test method name MUST describe: what is being tested, under what condition, and what the expected result is.

---

## RULE 8 — setUpTestData Is a Django TestCase Method — Don't Use in Pure Pytest Classes

The project uses **pure pytest** (`@pytest.mark.django_db`) for almost all tests. `setUpTestData` is a `django.test.TestCase` classmethod — pytest's runner does NOT call it automatically in plain pytest classes.

VIOLATION: Using `setUpTestData` in a class that does NOT inherit from `django.test.TestCase`:
```python
@pytest.mark.django_db
class TestUserViewSet:              # WRONG — setUpTestData is silently ignored by pytest
    @classmethod
    def setUpTestData(cls):         # pytest never calls this; cls.user will be missing
        cls.user = UserFactory()
```

CORRECT primary pattern — `@pytest.fixture(autouse=True)` for per-test setup (most common):
```python
@pytest.mark.django_db
class TestCourseSyncV2DataContent:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client
        self.user = UserFactory()
        self.teacher_profile = TeacherProfileFactory(user=self.user)
        self.client.force_authenticate(user=self.user)
```

This runs before EACH test. It is the expected, correct pattern — do NOT flag it.

CORRECT advanced pattern — shared class-level data using `scope="class"` (for expensive setup only):
```python
@pytest.fixture(scope="class")
def class_data(django_db_blocker):
    with django_db_blocker.unblock():
        return {"org": OrganizationFactory(), "user": UserFactory()}

@pytest.mark.django_db
@pytest.mark.usefixtures("class_data")
class TestSomeModel:
    def test_something(self, class_data):
        assert class_data["org"].pk is not None
```

ACCEPTABLE (legacy only) — Django TestCase with setUpTestData is valid ONLY when the class explicitly inherits `TestCase`:
```python
from django.test import TestCase

class TestSchoolGroup(TestCase):        # OK — inherits TestCase, setUpTestData works
    @classmethod
    def setUpTestData(cls):
        cls.organization = OrganizationFactory()
```

Only flag `setUpTestData` when the class uses `@pytest.mark.django_db` without a `TestCase` base class.

---

## RULE 9 — Shared Fixtures Belong in conftest.py

VIOLATION: Identical user+profile+authenticate setup repeated in the autouse fixture of 3+ test classes:
```python
# In class A:
@pytest.fixture(autouse=True)
def setup(self, client):
    self.user = UserFactory()
    self.teacher_profile = TeacherProfileFactory(user=self.user)
    self.participant = create_participant_for_profile(self.teacher_profile)
    self.client.force_authenticate(user=self.user)

# In class B: identical code
# In class C: identical code
```

CORRECT: Put in `conftest.py`:
```python
@pytest.fixture
def authenticated_teacher_client(client, teacher_with_participant):
    user, profile, participant = teacher_with_participant
    client.force_authenticate(user=user)
    return client
```

---

## RULE 10 — Inline Magic Values Must Use Constants

VIOLATION: Phone numbers, passwords, or domain values hardcoded inline:
```python
UserFactory(username="03000000000")                # WRONG
response = client.post(url, {"username": "03000000000"})  # WRONG
```

CORRECT:
```python
# In base/constants.py:
VALID_PHONE = "03000000000"

# In test:
UserFactory(username=VALID_PHONE)
```

Flag any phone number string, "test@123" password string, or other domain constant appearing more than once inline in test files.

---

## RULE 11 — Never Use force_login()

VIOLATION:
```python
client.force_login(user)    # WRONG — this is for session auth, not JWT
```

CORRECT:
```python
client.force_authenticate(user=user)    # CORRECT for DRF JWT
```

---

## WHAT IS ACCEPTABLE — DO NOT FLAG THESE:

- `@pytest.fixture(autouse=True)` for `setup` in a test class — this is the **primary pattern** used throughout the project; do NOT flag it
- `@pytest.mark.django_db` on test class — this is correct
- `force_authenticate` called in setup fixture — this is correct
- `create_participant_for_profile(profile)` called in setup — this is the required pattern
- `GrandQuiz.objects.create(...)` with a comment explaining the factory constraint
- `.objects.create(...)` for join/through models (e.g. `TeacherTrainingStatus`, `Assessment`) when no factory exists — these are exceptions to Rule 5 (add the factory suggestion as a comment-only, not a REQUEST_CHANGES violation)
- `from django.test import TestCase` with `setUpTestData` — valid only when the class explicitly inherits `TestCase`
- Private helpers defined once inside a single test class (only flag if duplicated across files)
- Docstrings on test methods describing the BDD scenario
- BDD-style comments (`# ------ Scenario: ... ------`)

---

## PRIORITY ORDER (if you must limit to 8 comments, use this order):

1. Missing `@pytest.mark.django_db` (test silently passes with no DB access)
2. `.objects.create()` without factory (most common violation)
3. Duplicate helpers across files (worst reuse violation)
4. Hardcoded URL in test body (should be in constants)
5. Missing factory for a model that is used 5+ times
6. Test naming violations (too vague)
7. `setUpTestData` used in a pure pytest class without `TestCase` inheritance (silently ignored — data never created)
8. Inline magic values not in constants

---

## OUTPUT FORMAT

You MUST respond with valid JSON only. No text before or after the JSON block.

```json
{
  "event": "REQUEST_CHANGES",
  "body": "One paragraph (2-4 sentences) summarizing overall quality, what was done well, and the main issues found.",
  "comments": [
    {
      "path": "taleemabad_core/apps/users/tests/views/authentication/test_login.py",
      "line": 25,
      "body": "Short comment — 1 to 2 sentences only. No code. Describe the violation and what to do instead."
    }
  ]
}
```

Rules:
- `event` must be one of: `"REQUEST_CHANGES"`, `"APPROVE"`, `"COMMENT"`
- Use `"REQUEST_CHANGES"` if ANY violation from the rules above is found
- Use `"APPROVE"` if NO violations are found
- Use `"COMMENT"` only for neutral feedback with no violations
- Maximum 8 objects in the `comments` array
- Each `body` string: 1-2 sentences, no code snippets
- `line` must be the actual line number in the file where the violation is located
- `path` must be the relative file path as shown in the diff header
- If no violations, use `"APPROVE"` with `"comments": []`
