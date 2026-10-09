# CI roadmap

`repository-policy.yml` is active immediately because it validates repository structure and Conventional Commit subjects without pretending the application exists.

After the frontend and backend scaffolds are committed, add required CI jobs in this order:

1. Frontend: locked install, lint, typecheck, test, build, then dependency cache.
2. Backend: locked install, ruff, pytest, coverage threshold, then dependency cache.
3. Docker: image build plus smoke test of the composed application.

The exact commands and dependency-tool versions must be taken from the committed frontend/backend configuration, then tested locally before making the checks required on `main`.
