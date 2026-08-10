# GitHub setup (manual, safe path)

1. Create a **private** empty GitHub repository, e.g. `aic2026`.
2. Do not initialize it with large files/data.
3. In this local repository:

```bash
git init
git add .
git commit -m "chore: bootstrap reliability scaffold"
git branch -M main
git remote add origin <YOUR_PRIVATE_REPO_URL>
git push -u origin main
```

4. Keep raw BTC data out of Git. The included `.gitignore` blocks common media/ML artifacts.
5. For private clone on Colab/Kaggle, store credentials in their secret-management UI, never in notebook cells committed to Git.
6. Tag known-good milestones, e.g. `git tag m0-scaffold-stable`.
