# Push this project to GitHub (one-time)

The repo **Hookshot** is already created at https://github.com/BattleBadger-rpg/Hookshot

## 1. Install Git (if you don't have it)

- Download: https://git-scm.com/download/win
- Run the installer (defaults are fine). Restart Cursor after installing.

## 2. Open terminal in this folder and run

In Cursor: **Terminal → New Terminal** (or Ctrl+`). Make sure you're in the "Snapchat Text on Screen" folder, then run:

```powershell
git init
git add .
git commit -m "Initial commit: SnapText + HookShot"
git branch -M main
git remote add origin https://github.com/BattleBadger-rpg/Hookshot.git
git push -u origin main
```

If it asks for credentials, use your GitHub username and your **Personal Access Token** (not your GitHub password) when it asks for a password.

## 3. Add VPS secrets on GitHub

- Go to https://github.com/BattleBadger-rpg/Hookshot/settings/secrets/actions
- **New repository secret** for each:
  - `VPS_HOST` = `5.223.69.224`
  - `VPS_USER` = `root`
  - `VPS_PASSWORD` = your VPS root password

After that, every push to `main` will trigger the deploy workflow and update the live site (once the server has been set up per HookShot/HOOKSHOT_DEPLOY.md).
