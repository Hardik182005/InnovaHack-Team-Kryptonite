import subprocess
import time
import sys
import glob

AVI = "Avi36005 <2023.avinash.gehi@ves.ac.in>"
HARDIK = "Hardik182005 <148485624+Hardik182005@users.noreply.github.com>"

commits = [
    {
        "message": "refactor(frontend): implement AppShell component and navigation styles",
        "files": [
            "frontend/src/components/AppShell.tsx",
            "frontend/src/components/Icon.tsx",
            "frontend/src/styles/app-shell.css",
            "frontend/src/styles/base.css"
        ],
        "author": HARDIK
    },
    {
        "message": "feat(frontend): update pages layout, localization, and language switcher",
        "files": [
            "frontend/src/components/LanguageSwitcher.tsx",
            "frontend/src/components/VoiceExpense.tsx",
            "frontend/src/components/common.tsx",
            "frontend/src/i18n/strings.ts",
            "frontend/src/lib/format.ts",
            "frontend/src/main.tsx",
            "frontend/index.html"
        ],
        "author": HARDIK
    },
    {
        "message": "feat(frontend): refine SPA pages and charts",
        "files": [
            "frontend/src/pages/Coach.tsx",
            "frontend/src/pages/Confidence.tsx",
            "frontend/src/pages/Dashboard.tsx",
            "frontend/src/pages/Goals.tsx",
            "frontend/src/pages/Landing.tsx",
            "frontend/src/pages/LeakRadar.tsx",
            "frontend/src/pages/Privacy.tsx",
            "frontend/src/pages/Processing.tsx",
            "frontend/src/pages/Review.tsx",
            "frontend/src/pages/RoundUps.tsx",
            "frontend/src/pages/SafeSpare.tsx",
            "frontend/src/pages/Spending.tsx",
            "frontend/src/App.tsx",
            "frontend/src/api/fixtures.ts",
            "frontend/src/api/types.ts",
            "frontend/public/seed.html",
            "frontend/public/p2.html",
            "frontend/public/lang.html",
            "frontend/public/probe.html",
            "frontend/public/debug.html"
        ],
        "author": HARDIK
    },
    {
        "message": "feat(backend): add translation service and models updates",
        "files": [
            "backend/app/services/translation.py",
            "backend/app/models/entities.py",
            "backend/app/models/transaction.py"
        ],
        "author": AVI
    },
    {
        "message": "feat(backend): optimize transaction extraction and parser tests",
        "files": [
            "backend/app/services/extraction.py",
            "backend/requirements.txt",
            "backend/tests/test_extraction.py"
        ],
        "author": AVI
    },
    {
        "message": "chore: regenerate synthetic demo statement and datasets",
        "files": [
            "demo_data/demo_statement.csv",
            "demo_data/demo_statement.pdf",
            "scripts/generate_demo_statement.py"
        ],
        "author": AVI
    }
]

def main():
    print("Verifying base commits... currently at:")
    subprocess.run(["git", "log", "-n", "3", "--oneline"])
    
    # Iterate through the 6 commits (Commit 21 to 26)
    for i, commit in enumerate(commits):
        num = i + 21
        print(f"\n--- Staging Commit {num}/26: {commit['message']} ---")
        
        # Add files
        for file in commit["files"]:
            subprocess.run(["git", "add", file])
        
        # Commit with explicit author override
        res = subprocess.run([
            "git", "commit",
            f"--author={commit['author']}",
            "-m", commit["message"]
        ], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Commit failed: {res.stderr}")
            sys.exit(1)
        print(res.stdout)
        
        # Push
        print(f"Pushing commit {num}/26 to origin main...")
        push_res = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
        if push_res.returncode != 0:
            print(f"Push failed: {push_res.stderr}")
            sys.exit(1)
        print(push_res.stdout)
        
        # Sleep for 10 seconds if not the last commit
        if num < 26:
            print("Sleeping for 10 seconds before the next commit...")
            time.sleep(10)

if __name__ == "__main__":
    main()
