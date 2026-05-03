# Publishing this repo to GitHub (personal / learning)

Use a **new repository under your personal GitHub account** (or an org clearly labeled as personal side projects) so it is obvious this is **not** corporate IP.

## 1. Before you push

- Read **`DISCLAIMER.md`** at the repo root; keep it linked from **`README.md`** (already done in this tree).
- Search for anything you do not want public: real API keys, customer hostnames, internal URLs, employee names. **`grep -R`**, then fix or remove.
- Confirm **`.gitignore`** excludes `.env`, secrets, and local tunnel configs (this repo already ignores typical paths).

## 2. Create the GitHub repo and push

From the machine that has the clone:

```bash
cd /path/to/ollama-cursor-aliases
gh auth login
gh repo create ollama-cursor-aliases --public --source=. --remote=origin --description "Personal learning: Cursor + LiteLLM + Ollama notes and configs (not employer work)" --push
```

Or create an **empty** repo on github.com, then:

```bash
git remote add origin https://github.com/<your-username>/ollama-cursor-aliases.git
git branch -M main
git push -u origin main
```

## 3. GitHub UI (optional)

- **Repository description:** e.g. *Personal learning — Cursor IDE + local LLM proxy experiments; not affiliated with any employer.*
- **Topics:** `cursor`, `ollama`, `litellm`, `learning`, `homelab`
- **About:** link to **`docs/CURSOR_LITELLM_OLLAMA_EXPERIENCE.md`** as the main “why read this” doc.

## 4. If someone at work asks

Point them to **`DISCLAIMER.md`** and the README opening paragraph: **personal experimentation**, **no company systems or secrets**, **educational only**.
