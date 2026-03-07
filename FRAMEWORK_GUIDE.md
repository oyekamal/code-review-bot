# Quick Start: Adding Framework Support

This guide shows you **exactly how to add support for a new framework** (Next.js, Vue, Go, etc.) to your refactored PR review bot.

---

## 📚 Table of Contents
1. [Framework Reviewer Template](#framework-reviewer-template)
2. [Example: Adding Next.js Support](#example-adding-nextjs-support)
3. [Example: Adding React Support](#example-adding-react-support)
4. [Creating Framework-Specific Review Guides](#creating-framework-specific-review-guides)
5. [Testing Your New Reviewer](#testing-your-new-reviewer)

---

## Framework Reviewer Template

Every framework reviewer follows this pattern:

```python
# src/pr_review_bot/reviewers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from ..models.pr import File, PullRequest
from ..models.review import Review

class BaseReviewer(ABC):
    """Abstract base class for all framework reviewers."""
    
    def __init__(self, project_config, llm_client):
        self.config = project_config
        self.llm = llm_client
        self.guide = self._load_guide()
    
    @abstractmethod
    def can_review(self, file: File) -> bool:
        """Return True if this reviewer handles the given file."""
        pass
    
    @abstractmethod
    def classify_pr(self, files: List[File]) -> str:
        """Classify the PR type (e.g., 'api', 'components', 'mixed')."""
        pass
    
    @abstractmethod
    def _load_guide(self) -> str:
        """Load the framework-specific review guide."""
        pass
    
    @abstractmethod
    def get_rules(self) -> List[str]:
        """Return list of rule names to enforce."""
        pass
    
    def review(self, pr: PullRequest) -> Review:
        """Main review method (same for all frameworks)."""
        files = [f for f in pr.files if self.can_review(f)]
        pr_type = self.classify_pr(files)
        
        chunks = self._create_chunks(files)
        results = []
        
        for chunk in chunks:
            result = self.llm.review_code(
                guide=self.guide,
                diff=chunk.diff,
                pr_type=pr_type
            )
            results.append(result)
        
        return self._merge_results(results)
```

---

## Example: Adding Next.js Support

### Step 1: Create Next.js Reviewer

```python
# src/pr_review_bot/reviewers/nextjs_reviewer.py
from pathlib import Path
from fnmatch import fnmatch
from typing import List
from .base import BaseReviewer
from ..models.pr import File

class NextJSReviewer(BaseReviewer):
    """Reviewer for Next.js projects (App Router & Pages Router)."""
    
    # File patterns this reviewer handles
    PATTERNS = [
        "app/**/*.ts",
        "app/**/*.tsx",
        "app/**/*.js",
        "app/**/*.jsx",
        "pages/**/*.ts",
        "pages/**/*.tsx",
        "pages/**/*.js",
        "pages/**/*.jsx",
        "components/**/*.tsx",
        "components/**/*.jsx",
        "lib/**/*.ts",
        "utils/**/*.ts",
        "next.config.js",
        "next.config.ts",
    ]
    
    def can_review(self, file: File) -> bool:
        """Check if file is a Next.js file."""
        return any(fnmatch(file.path, pattern) for pattern in self.PATTERNS)
    
    def classify_pr(self, files: List[File]) -> str:
        """Classify Next.js PR by primary change area."""
        api_files = [f for f in files if "/api/" in f.path or "/route." in f.path]
        page_files = [f for f in files if self._is_page_file(f)]
        component_files = [f for f in files if "/components/" in f.path]
        lib_files = [f for f in files if "/lib/" in f.path or "/utils/" in f.path]
        config_files = [f for f in files if "next.config" in f.path]
        
        # Priority: config > api > pages > components > lib
        if config_files:
            return "config"
        if api_files:
            return "api"
        if page_files:
            return "pages"
        if component_files:
            return "components"
        if lib_files:
            return "library"
        
        return "mixed"
    
    def _is_page_file(self, file: File) -> bool:
        """Check if file is a Next.js page/route."""
        path = Path(file.path)
        
        # App Router: app/*/page.tsx or app/*/layout.tsx
        if "app/" in file.path:
            return path.name in ["page.tsx", "page.ts", "layout.tsx", "layout.ts"]
        
        # Pages Router: pages/**/*.tsx
        if "pages/" in file.path:
            return not path.name.startswith("_")  # Exclude _app, _document
        
        return False
    
    def _load_guide(self) -> str:
        """Load Next.js review guide."""
        guide_path = Path(self.config.guides_dir or "guides/nextjs") / "CODE_REVIEW.md"
        if not guide_path.exists():
            return self._get_default_guide()
        return guide_path.read_text()
    
    def get_rules(self) -> List[str]:
        """Next.js specific rules to enforce."""
        return [
            "no-blocking-in-server-components",
            "proper-client-component-boundaries",
            "metadata-for-seo",
            "image-optimization",
            "font-optimization",
            "proper-loading-states",
            "error-boundary-usage",
            "no-use-effect-for-data-fetching",
            "proper-cache-revalidation",
        ]
    
    def _get_default_guide(self) -> str:
        """Default Next.js review guide if custom guide not found."""
        return """
# Next.js Code Review Guide

## CRITICAL RULES

### 1. Server vs Client Components
- Server Components (default) should NOT use React hooks (useState, useEffect, etc.)
- Client Components MUST have 'use client' directive at the top
- Client Components should be as small as possible (wrap only interactive parts)

### 2. Data Fetching
- Use async Server Components for data fetching, NOT useEffect
- Cache data fetches with proper revalidation: `fetch(url, { next: { revalidate: 3600 } })`
- For mutations, use Server Actions with proper error handling

### 3. Metadata & SEO
- Every page route MUST export `metadata` or `generateMetadata` function
- Use `<Image>` component from next/image, never raw <img> tags
- Use `<Link>` component from next/link, never <a> tags for internal navigation

### 4. Performance
- Use next/font for font optimization
- Implement proper loading.tsx and error.tsx files
- Use Suspense boundaries for streaming
- Minimize client-side JavaScript (prefer Server Components)

### 5. API Routes
- Validate all incoming request data
- Return proper HTTP status codes
- Use NextResponse for consistent responses
- Implement rate limiting for public endpoints

## COMMON VIOLATIONS

**VIOLATION - Using useEffect for data fetching:**
```tsx
'use client'
function Page() {
  const [data, setData] = useState(null)
  useEffect(() => {
    fetch('/api/data').then(r => r.json()).then(setData)
  }, [])
}
```

**CORRECT - Use async Server Component:**
```tsx
async function Page() {
  const data = await fetch('/api/data').then(r => r.json())
  return <div>{data}</div>
}
```

**VIOLATION - Missing 'use client' directive:**
```tsx
function Button() {
  const [count, setCount] = useState(0)  // ERROR: hooks in Server Component
  return <button onClick={() => setCount(count + 1)}>{count}</button>
}
```

**CORRECT - Add 'use client':**
```tsx
'use client'
function Button() {
  const [count, setCount] = useState(0)
  return <button onClick={() => setCount(count + 1)}>{count}</button>
}
```

**VIOLATION - No image optimization:**
```tsx
<img src="/hero.jpg" alt="Hero" />  {/* WRONG */}
```

**CORRECT - Use next/image:**
```tsx
import Image from 'next/image'
<Image src="/hero.jpg" alt="Hero" width={800} height={600} />
```

## OUTPUT FORMAT

Return JSON:
```json
{
  "event": "REQUEST_CHANGES" | "APPROVE" | "COMMENT",
  "summary": "Brief summary of findings",
  "comments": [
    {
      "path": "app/dashboard/page.tsx",
      "line": 15,
      "body": "Using useEffect for data fetching in a Server Component. Convert to async function."
    }
  ]
}
```
"""


# Register the reviewer
from ..core.registry import ReviewerRegistry
ReviewerRegistry.register("nextjs", NextJSReviewer)
```

---

### Step 2: Create Next.js Review Guide

```markdown
# guides/nextjs/CODE_REVIEW.md

# Next.js Code Review Guide

## Project Context

| Property | Value |
|----------|-------|
| Framework | Next.js 14+ (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| State | Zustand / React Context |
| Auth | NextAuth.js |

---

## HARD RULES - Always Flag

### RULE 1: Server vs Client Component Boundaries

**Violation Examples:**

❌ **Using hooks in Server Component:**
```tsx
// app/dashboard/page.tsx
export default function DashboardPage() {
  const [data, setData] = useState([])  // VIOLATION
  useEffect(() => { /* ... */ }, [])    // VIOLATION
}
```

✅ **Correct - Async Server Component:**
```tsx
export default async function DashboardPage() {
  const data = await fetchDashboardData()
  return <DashboardView data={data} />
}
```

❌ **Missing 'use client' directive:**
```tsx
// components/Counter.tsx
export function Counter() {
  const [count, setCount] = useState(0)  // VIOLATION: hooks without 'use client'
}
```

✅ **Correct - Add directive:**
```tsx
'use client'
export function Counter() {
  const [count, setCount] = useState(0)
}
```

---

### RULE 2: Data Fetching Anti-Patterns

❌ **Using useEffect for data load:**
```tsx
'use client'
function Products() {
  const [products, setProducts] = useState([])
  useEffect(() => {
    fetch('/api/products').then(r => r.json()).then(setProducts)
  }, [])
}
```

✅ **Correct - Server Component:**
```tsx
async function Products() {
  const products = await fetch('/api/products').then(r => r.json())
  return <ProductList products={products} />
}
```

---

### RULE 3: Missing Metadata for SEO

❌ **Page without metadata:**
```tsx
// app/products/page.tsx
export default function ProductsPage() {
  return <div>Products</div>
}
```

✅ **Correct - Export metadata:**
```tsx
import { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Products | MyStore',
  description: 'Browse our product catalog',
}

export default function ProductsPage() {
  return <div>Products</div>
}
```

---

### RULE 4: Image/Font Optimization

❌ **Raw img tags:**
```tsx
<img src="/logo.png" alt="Logo" />
```

✅ **Use next/image:**
```tsx
import Image from 'next/image'
<Image src="/logo.png" alt="Logo" width={120} height={40} />
```

❌ **Raw font import:**
```tsx
@import url('https://fonts.googleapis.com/css2?family=Inter');
```

✅ **Use next/font:**
```tsx
import { Inter } from 'next/font/google'
const inter = Inter({ subsets: ['latin'] })
```

---

### RULE 5: API Route Security

❌ **No input validation:**
```tsx
export async function POST(request: Request) {
  const body = await request.json()
  await db.users.create(body)  // VIOLATION: No validation
}
```

✅ **Validate with Zod:**
```tsx
import { z } from 'zod'

const schema = z.object({
  email: z.string().email(),
  name: z.string().min(1)
})

export async function POST(request: Request) {
  const body = await request.json()
  const data = schema.parse(body)  // Throws if invalid
  await db.users.create(data)
}
```

---

## What NOT to Flag

- Using 'use client' when necessary (not a violation)
- Wrapping Server Components with Suspense (correct pattern)
- Using loading.tsx and error.tsx (best practice)
- Client Components in /components/ directory (intentional)

---

## Output Format

```json
{
  "event": "REQUEST_CHANGES",
  "summary": "Found 3 violations: server/client boundary issues and missing metadata",
  "comments": [
    {
      "path": "app/dashboard/page.tsx",
      "line": 12,
      "body": "Using useState in Server Component. Mark with 'use client' or convert to async Server Component."
    }
  ]
}
```
```

---

### Step 3: Update Configuration

```yaml
# config/projects.yaml
projects:
  - name: ecommerce-nextjs
    repo: myorg/ecommerce-platform
    frameworks:
      - nextjs
      - typescript
    llm:
      provider: anthropic
      model: claude-sonnet-4
      api_key: ${ANTHROPIC_API_KEY}
    review:
      max_comments: 10
      auto_approve_on_resolution: false
    guides_dir: ./guides/nextjs
```

---

### Step 4: Register in Reviewer Factory

```python
# src/pr_review_bot/core/factory.py
from ..reviewers.django_reviewer import DjangoReviewer
from ..reviewers.nextjs_reviewer import NextJSReviewer
from ..reviewers.react_reviewer import ReactReviewer

class ReviewerFactory:
    """Factory for creating framework-specific reviewers."""
    
    _REVIEWERS = {
        "django": DjangoReviewer,
        "nextjs": NextJSReviewer,
        "react": ReactReviewer,
    }
    
    @classmethod
    def create(cls, framework: str, config, llm):
        """Create a reviewer for the given framework."""
        reviewer_class = cls._REVIEWERS.get(framework)
        if not reviewer_class:
            raise ValueError(f"No reviewer found for framework: {framework}")
        return reviewer_class(config, llm)
    
    @classmethod
    def register(cls, framework: str, reviewer_class):
        """Register a custom reviewer (for plugins)."""
        cls._REVIEWERS[framework] = reviewer_class
```

---

## Example: Adding React Support

```python
# src/pr_review_bot/reviewers/react_reviewer.py
class ReactReviewer(BaseReviewer):
    """Reviewer for React projects (CRA, Vite, etc.)."""
    
    PATTERNS = [
        "src/**/*.tsx",
        "src/**/*.jsx",
        "src/**/*.ts",
        "src/**/*.js",
        "components/**/*.tsx",
        "hooks/**/*.ts",
    ]
    
    def can_review(self, file: File) -> bool:
        return any(fnmatch(file.path, p) for p in self.PATTERNS)
    
    def classify_pr(self, files: List[File]) -> str:
        """Classify React PR."""
        hook_files = [f for f in files if "/hooks/" in f.path or f.path.startswith("use")]
        component_files = [f for f in files if "/components/" in f.path]
        store_files = [f for f in files if "/store/" in f.path or "/redux/" in f.path]
        
        if hook_files:
            return "hooks"
        if store_files:
            return "state-management"
        if component_files:
            return "components"
        return "mixed"
    
    def get_rules(self) -> List[str]:
        return [
            "no-inline-styles",
            "proper-key-prop",
            "no-array-index-as-key",
            "missing-alt-text",
            "unused-state-variables",
            "dependency-array-issues",
            "prop-types-or-typescript",
        ]
    
    def _load_guide(self) -> str:
        guide_path = Path(self.config.guides_dir or "guides/react") / "CODE_REVIEW.md"
        if not guide_path.exists():
            return self._get_default_guide()
        return guide_path.read_text()
    
    def _get_default_guide(self) -> str:
        return """
# React Code Review Guide

## HARD RULES

### 1. Keys in Lists
- NEVER use array index as key
- Keys must be stable and unique

VIOLATION:
```tsx
items.map((item, index) => <div key={index}>{item}</div>)
```

CORRECT:
```tsx
items.map(item => <div key={item.id}>{item}</div>)
```

### 2. Hooks Rules
- Hooks only at top level (not in loops/conditions)
- Dependency arrays must be complete

VIOLATION:
```tsx
useEffect(() => {
  doSomething(userId)
}, [])  // Missing userId dependency
```

CORRECT:
```tsx
useEffect(() => {
  doSomething(userId)
}, [userId])
```

### 3. Accessibility
- All images must have alt text
- Buttons must have accessible labels
- Forms must have proper labels

VIOLATION:
```tsx
<img src="/logo.png" />
<button><Icon /></button>
```

CORRECT:
```tsx
<img src="/logo.png" alt="Company Logo" />
<button aria-label="Delete item"><Icon /></button>
```
"""
```

---

## Testing Your New Reviewer

### Unit Tests

```python
# tests/unit/reviewers/test_nextjs_reviewer.py
import pytest
from pr_review_bot.reviewers.nextjs_reviewer import NextJSReviewer
from pr_review_bot.models.pr import File

class TestNextJSReviewer:
    
    @pytest.fixture
    def reviewer(self, mock_config, mock_llm):
        return NextJSReviewer(mock_config, mock_llm)
    
    def test_can_review_app_router_page(self, reviewer):
        file = File(path="app/dashboard/page.tsx")
        assert reviewer.can_review(file) is True
    
    def test_can_review_api_route(self, reviewer):
        file = File(path="app/api/users/route.ts")
        assert reviewer.can_review(file) is True
    
    def test_cannot_review_python_file(self, reviewer):
        file = File(path="backend/views.py")
        assert reviewer.can_review(file) is False
    
    def test_classify_api_pr(self, reviewer):
        files = [
            File(path="app/api/products/route.ts", additions=50),
            File(path="lib/utils.ts", additions=10),
        ]
        result = reviewer.classify_pr(files)
        assert result == "api"
    
    def test_classify_pages_pr(self, reviewer):
        files = [
            File(path="app/products/page.tsx", additions=100),
            File(path="app/products/layout.tsx", additions=20),
        ]
        result = reviewer.classify_pr(files)
        assert result == "pages"
```

### Integration Test

```python
# tests/integration/test_nextjs_review.py
import pytest
from pr_review_bot.core.orchestrator import ReviewOrchestrator

class TestNextJSReviewIntegration:
    
    @pytest.fixture
    def orchestrator(self, nextjs_config):
        return ReviewOrchestrator(nextjs_config)
    
    def test_review_nextjs_pr_with_server_component_violation(
        self, orchestrator, mock_github_pr
    ):
        # Given a PR with server component using hooks
        diff = """
--- a/app/products/page.tsx
+++ b/app/products/page.tsx
@@ -1,5 +1,8 @@
+import { useState } from 'react'
+
 export default function ProductsPage() {
+  const [count, setCount] = useState(0)
   return <div>Products</div>
 }
"""
        mock_github_pr.files = [File(path="app/products/page.tsx", patch=diff)]
        
        # When reviewing
        review = orchestrator.review_pr(mock_github_pr)
        
        # Then should flag the violation
        assert review.event == "REQUEST_CHANGES"
        assert len(review.comments) >= 1
        assert any("use client" in c.body.lower() for c in review.comments)
```

---

## Deploying Your New Reviewer

### 1. Update Configuration
```yaml
# config/projects.yaml
projects:
  - name: new-nextjs-project
    repo: myorg/new-project
    frameworks:
      - nextjs  # Will use NextJSReviewer automatically
```

### 2. Test Locally
```bash
pr-review-bot review --project new-nextjs-project --pr 42
```

### 3. Deploy
```bash
# Update the bot server/cron job
git push
# Restart service
systemctl restart pr-review-bot
```

---

## Framework Reviewer Checklist

When adding a new framework, ensure you have:

- [ ] Created `src/pr_review_bot/reviewers/{framework}_reviewer.py`
- [ ] Implemented `can_review()` method with file patterns
- [ ] Implemented `classify_pr()` method for PR categorization
- [ ] Implemented `get_rules()` method listing enforce-able rules
- [ ] Created `guides/{framework}/CODE_REVIEW.md` with detailed rules
- [ ] Registered reviewer in `ReviewerFactory`
- [ ] Written unit tests for file matching and classification
- [ ] Written integration tests with sample diffs
- [ ] Updated documentation
- [ ] Added example configuration

---

## Common Patterns Across Frameworks

All reviewers should check for:

1. **Security Issues**
   - SQL injection vulnerabilities
   - XSS vulnerabilities
   - Exposed secrets/credentials
   - Missing input validation

2. **Performance**
   - N+1 queries
   - Missing indexes
   - Inefficient algorithms
   - Memory leaks

3. **Code Quality**
   - Missing error handling
   - Unused imports
   - Dead code
   - Complex functions (>50 lines)

4. **Testing**
   - Missing tests for new features
   - Tests without assertions
   - Flaky tests

---

**With this template, you can add support for any framework in under 2 hours!**
