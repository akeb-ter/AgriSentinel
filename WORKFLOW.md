# AgriSentinel - Git Workflow & Branching Strategy

## Branch Structure

- **`main`**: Production / stable release branch.
- **`dev`**: Primary integration and testing branch.
- **`feature/*`**, **`fix/*`**, **`bug/*`**: Topic branches for new development work, always created from `dev`.

---

## Developer Workflow

### 1. Starting a New Task
Always switch to `dev` first and pull the latest changes, then create your feature or fix branch:
```bash
git checkout dev
git checkout -b feature/<feature-name>   # For new features
# OR
git checkout -b fix/<bug-name>           # For bug fixes
```

### 2. Developing & Committing
Implement your changes, run local tests, and commit to your topic branch:
```bash
git add .
git commit -m "feat: <description>"
```

### 3. Merging to `dev` for Testing
Once work is ready for integration, merge your feature/fix branch into `dev`:
```bash
git checkout dev
git merge feature/<feature-name>
```

### 4. Releasing to `main`
After testing is verified on `dev`, merge `dev` into `main`:
```bash
git checkout main
git merge dev
```
