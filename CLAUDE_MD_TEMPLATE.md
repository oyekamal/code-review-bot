# Taleemabad Core - Code Review Standards

> This file is used by the PR Review Bot to understand project-specific rules and conventions.
> Place this file at: `.github/claude.md` in your repository.

---

## 📋 Project Context

| Property | Value |
|----------|-------|
| Project | taleemabad-core — multi-tenant educational platform |
| Backend | Python 3.10, Django 4.2.8, DRF 3.14.0, PostgreSQL, Redis, Celery |
| Frontend | React 18, TypeScript, Dexie.js (offline-first) |
| Multi-tenancy | django-tenants with PostgreSQL schema isolation |
| Style | black, isort, flake8 (enforced by pre-commit) |

---

## 🚨 CRITICAL RULES - Always Flag These

### RULE 1: Soft-Delete Only

**Purpose:** Data must never be permanently deleted. Soft-deletion preserves audit trails.

**VIOLATION - Hard delete:**
```python
# WRONG
instance.delete()
School.objects.filter(is_active=False).delete()
cursor.execute("DELETE FROM schools_school WHERE id = %s", [school_id])
```

**CORRECT - Soft delete:**
```python
# CORRECT
instance.is_active = False
instance.save(update_fields=["is_active"])

# CORRECT
School.objects.filter(is_active=False).update(is_active=False)
```

**What to flag:**
- Any `.delete()` call on model instances or querysets
- Any `DELETE FROM` in raw SQL
- New models that don't inherit from `SoftDeleteAuditableMixin`

**Exception:** Test files may use `.delete()` for cleanup - do NOT flag this.

---

### RULE 2: Multi-Tenancy Safety

**Purpose:** Each tenant's data is isolated in its own PostgreSQL schema. Cross-schema access is a critical security violation.

**VIOLATION - Hardcoded schema:**
```python
# WRONG
cursor.execute("SET search_path TO public")
cursor.execute("SELECT * FROM tenant1.schools")

# WRONG - Celery task without tenant context
@shared_task
def send_report():
    schools = School.objects.all()  # Which tenant?
```

**CORRECT - Tenant-aware:**
```python
# CORRECT
from django.db import connection
schema = connection.schema_name

# CORRECT - Celery task with tenant parameter
@shared_task
def send_report(schema_name):
    from django_tenants.utils import schema_context
    with schema_context(schema_name):
        schools = School.objects.all()
```

**What to flag:**
- Hardcoded schema names like `"public"`, `"tenant1"`
- Celery tasks operating on tenant models without schema parameter
- Raw SQL with `schema.table` notation
- Manual `SET search_path` without restoration

---

### RULE 3: API Versioning - Never Break Existing Versions

**Purpose:** Mobile clients may run old app versions for months. Breaking an API response causes crashes.

**VIOLATION - Removing/renaming fields:**
```python
# WRONG - Field removed from v1 serializer
class SchoolSerializerV1(serializers.ModelSerializer):
    class Meta:
        fields = ["id", "name"]  # "phone" was here before - REMOVED!

# WRONG - Field renamed
class UserSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField()  # Was "first_name" before

# WRONG - URL changed
path("schools/<uuid:pk>/", ...)  # Was "<int:pk>/" before
```

**CORRECT - Backward compatible:**
```python
# CORRECT - Add optional field
class SchoolSerializerV1(serializers.ModelSerializer):
    class Meta:
        fields = ["id", "name", "phone", "new_optional_field"]

# CORRECT - Create new version
class SchoolSerializerV2(serializers.ModelSerializer):
    class Meta:
        fields = ["id", "school_name"]  # Different structure
```

**What to flag:**
- Removing fields from existing versioned serializers
- Renaming existing fields
- Changing URL patterns for existing endpoints
- Changing response structure (list → single object)

**Exception:** Adding new OPTIONAL fields is safe.

---

### RULE 4: Migration Safety

**Purpose:** Migrations run across ALL tenant schemas. Bad migrations corrupt data or cause downtime.

**VIOLATION - Direct model import:**
```python
# WRONG - Direct import in migration
from taleemabad_core.apps.schools.models import School

def forwards(apps, schema_editor):
    School.objects.filter(...).update(...)  # Must use apps.get_model()
```

**VIOLATION - NOT NULL without default:**
```python
# WRONG - NOT NULL on existing table
migrations.AddField(
    model_name="school",
    name="region_code",
    field=models.CharField(max_length=10),  # No null=True, no default
)
```

**VIOLATION - Missing reverse:**
```python
# WRONG - No backward migration
migrations.RunPython(forwards)  # No second argument
```

**CORRECT:**
```python
# CORRECT - Use apps.get_model()
def forwards(apps, schema_editor):
    School = apps.get_model('schools', 'School')
    School.objects.filter(...).update(...)

def backwards(apps, schema_editor):
    School = apps.get_model('schools', 'School')
    # Undo the forwards step

migrations.RunPython(forwards, backwards)

# CORRECT - NULL allowed or default provided
migrations.AddField(
    model_name="school",
    name="region_code",
    field=models.CharField(max_length=10, null=True),  # Safe
)
```

**What to flag:**
- `from app.models import` inside migrations
- `AddField` with NOT NULL on existing tables without default
- `RunPython` without reverse function
- `AddIndex` without `concurrently=True` on large tables

---

### RULE 5: Offline-First Safety (Frontend TypeScript/React)

**Purpose:** Frontend is offline-first. Data must be written to IndexedDB before syncing.

**VIOLATION - Direct API call:**
```tsx
// WRONG - Direct API call bypasses offline storage
const schools = await axios.get("/api/schools/")
```

**VIOLATION - Missing 'use client' with hooks:**
```tsx
// WRONG - Using hooks without 'use client' (if Next.js)
function Button() {
  const [count, setCount] = useState(0)  // Missing 'use client'
  return <button>{count}</button>
}
```

**CORRECT:**
```tsx
// CORRECT - Use Dexie service
import { schoolService } from '@taleemabad/db'
const schools = await schoolService.getAll()

// CORRECT - Add 'use client' directive
'use client'
function Button() {
  const [count, setCount] = useState(0)
  return <button>{count}</button>
}
```

**What to flag:**
- Components calling Axios/fetch directly when Dexie service exists
- Dexie schema changes without version increment
- Components not checking `SyncRecordStatus`

---

## ⚠️ IMPORTANT PATTERNS TO ENFORCE

### Model Patterns

**All models should include:**
```python
class MyModel(SoftDeleteAuditableMixin, models.Model):
    # Model fields
    
    history = HistoricalRecords()  # Audit trail
```

**What to flag:**
- New models without `SoftDeleteAuditableMixin`
- New models without `HistoricalRecords()`
- Tree models not using `SoftDeleteAuditableMpttMixin`

**Exception:** Don't flag migrations or test files.

---

### Security Patterns

**Sensitive fields:**
```python
# WRONG - Password field readable
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField()

# CORRECT - Write-only
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
```

**What to flag:**
- Fields named `password`, `token`, `secret`, `key` without `write_only=True`
- `AllowAny` permission without comment explaining why
- Raw SQL with f-strings: `f"SELECT * FROM {table}"`
- Empty `permission_classes = []` without comment

---

### Celery Task Patterns

**Cross-tenant tasks:**
```python
# CORRECT
@shared_task(bind=True)
def process_reports(self, schema_name):
    try:
        with schema_context(schema_name):
            # Do work
            pass
    except Exception as exc:
        self.retry(exc=exc, countdown=60)
```

**What to flag:**
- Tasks operating on tenant models without `schema_name` parameter
- Tasks with DB writes but no error handling
- Tasks without `bind=True` and `self.retry()`

---

### DRF Serializer/View Patterns

**Public endpoints need docs:**
```python
# CORRECT
from drf_spectacular.utils import extend_schema

class SchoolViewSet(viewsets.ModelViewSet):
    @extend_schema(
        summary="List all schools",
        description="Returns all schools for current tenant"
    )
    def list(self, request):
        pass
```

**What to flag:**
- New public ViewSets without `@extend_schema`
- Removing fields from existing serializers
- Private endpoints (internal/retool) can skip `@extend_schema`

---

## ✅ WHAT NOT TO FLAG

Do NOT flag these patterns:

- Adding new OPTIONAL fields to serializers (backward compatible)
- `null=True` on new migrations (this is correct)
- Code comments and docstrings
- Import ordering (handled by isort)
- Line length (handled by black)
- Unused imports (handled by flake8)
- Test files using `.delete()` for cleanup
- Test files with hardcoded schema names
- Test files with `AllowAny` in test views
- `RunPython.noop` as reverse for additive migrations
- Type annotations/Pydantic models not extending `SoftDeleteAuditableMixin`

---

## 📤 OUTPUT FORMAT

Return JSON in this exact format:

```json
{
  "event": "REQUEST_CHANGES" | "APPROVE" | "COMMENT",
  "summary": "One paragraph summary of overall code quality and main issues found. If approving, state what was checked and that no issues were found.",
  "comments": [
    {
      "path": "relative/file/path.py",
      "line": 15,
      "body": "1-2 sentences. State violation and which rule it breaks. No code examples."
    }
  ]
}
```

**Rules:**
- `event`: `REQUEST_CHANGES` if any CRITICAL RULE violated, `APPROVE` if no issues
- `summary`: Plain text, one paragraph, no markdown
- `comments`: Max 8, prioritize CRITICAL RULES
- `comments.path`: Relative path from repo root
- `comments.line`: Integer line number where violation occurs
- `comments.body`: 1-2 sentences, no code snippets

---

## 🎯 REVIEW PRIORITY

When reviewing, check in this order:

1. **CRITICAL RULES** (1-5) - Always flag
2. **Security patterns** - AllowAny, sensitive fields, SQL injection
3. **Model patterns** - Missing mixins or history
4. **Celery patterns** - Cross-tenant safety
5. **API docs** - Missing @extend_schema

If more than 8 violations found, prioritize:
1. CRITICAL RULE violations
2. Security issues
3. Everything else

---

## 📚 EXAMPLE REVIEWS

### Example 1: Hard Delete Violation

**Input diff:**
```python
# app/views.py
def delete_school(request, school_id):
    school = School.objects.get(id=school_id)
    school.delete()  # VIOLATION
    return Response(status=204)
```

**Output:**
```json
{
  "event": "REQUEST_CHANGES",
  "summary": "One RULE 1 violation found: hard delete used instead of soft-delete. This must be fixed before merging as it violates the data preservation policy.",
  "comments": [
    {
      "path": "app/views.py",
      "line": 4,
      "body": "Hard delete violates RULE 1 (Soft-Delete Only). Use instance.is_active = False instead."
    }
  ]
}
```

### Example 2: All Good

**Output:**
```json
{
  "event": "APPROVE",
  "summary": "Reviewed all changed files. No violations of soft-delete rule, multi-tenancy safety, API versioning, migration safety, or offline-first patterns were found. Code follows project conventions.",
  "comments": []
}
```

---

**This guide is complete. The bot will use these rules to review every PR automatically.** 🎯
