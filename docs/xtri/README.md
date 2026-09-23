# Xtri-pondus background

This folder holds **copies of documentation** from your Xtri repository so the training coach agent can align plans with the real project—without mixing training data into the app repo.

## Sync from your Xtri repo

From the repo root:

```bash
export XTRI_REPO_URL='https://github.com/<you>/<xtri-repo>.git'
# optional: export XTRI_DOC_PATHS='docs README.md planning'
./scripts/sync_xtri_docs.sh
```

The script clones or updates a shallow copy under `.cache/xtri-repo` and copies markdown/text files into `docs/xtri/synced/`.

## If sync is not set up yet

Paste or commit key files here manually, for example:

- Phase overview (pondus / load progression)
- Sport-specific constraints from the Xtri project
- Any physiology or testing notes you already wrote for Xtri

The agent is instructed **not** to invent Xtri-specific content when this folder is empty.
