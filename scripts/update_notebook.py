import json
import os

NOTEBOOK_PATH = 'backend/CloudLeecher.ipynb'
APP_PATH = 'backend/app.py'

def update_notebook():
    print(f"Reading notebook from {NOTEBOOK_PATH}...")
    with open(NOTEBOOK_PATH, 'r', encoding='utf-8') as f:
        nb = json.load(f)

    print(f"Reading app.py from {APP_PATH}...")
    with open(APP_PATH, 'r', encoding='utf-8') as f:
        app_content = f.read()

    # update app.py cell
    app_lines = app_content.splitlines(keepends=True)
    # Prefix with %%writefile app.py
    source_lines = ["%%writefile app.py\n"] + app_lines

    updated_app = False
    updated_launch = False

    for cell in nb['cells']:
        # Update Step 4: Create API Backend
        if cell.get('metadata', {}).get('id') == 'step4_code':
            print("Found 'step4_code' cell. Updating content...")
            cell['source'] = source_lines
            updated_app = True

        # Update Step 5: Launch Public Server
        if cell.get('metadata', {}).get('id') == 'step5_code':
            print("Found 'step5_code' cell. Updating launch logic...")

            # We construct the new launch code programmatically
            launch_code = [
                "from pyngrok import ngrok\n",
                "from google.colab import userdata\n",
                "import subprocess\n",
                "import sys\n",
                "import time\n",
                "import os\n",
                "import secrets\n",
                "\n",
                "# 1. Authenticate Ngrok\n",
                "try:\n",
                "    AUTH_TOKEN = userdata.get(\"NGROK-AUTHTOKEN\")\n",
                "    ngrok.set_auth_token(AUTH_TOKEN)\n",
                "except Exception as e:\n",
                "    print(\"❌ Error: Ngrok Auth Token not found! Please add 'NGROK-AUTHTOKEN' to Colab Secrets (Key icon on the left).\")\n",
                "    raise e\n",
                "\n",
                "# 2. Generate Secure API Key\n",
                "CL_API_KEY = secrets.token_hex(16)\n",
                "os.environ['CLOUDLEECHER_API_KEY'] = CL_API_KEY\n",
                "\n",
                "# 3. Cleanup Old Processes (Port 5000)\n",
                "ngrok.kill()\n",
                "os.system(\"fuser -k 5000/tcp > /dev/null 2>&1\")\n",
                "\n",
                "# 4. Start Flask App in Background\n",
                "log_file = open(\"flask.log\", \"w\")\n",
                "env = os.environ.copy()\n",
                "env['CLOUDLEECHER_API_KEY'] = CL_API_KEY\n",
                "subprocess.Popen([sys.executable, \"app.py\"], stdout=log_file, stderr=log_file, env=env)\n",
                "time.sleep(3)  # Allow Flask to initialize\n",
                "\n",
                "# 5. Open Ngrok Tunnel\n",
                "try:\n",
                "    public_url = ngrok.connect(5000).public_url\n",
                "    print(\"\\n\" + \"=\"*60)\n",
                "    print(f\"🔗 PUBLIC URL: {public_url}\")\n",
                "    print(f\"🔑 API KEY:    {CL_API_KEY}\")\n",
                "    print(\"=\"*60 + \"\\n\")\n",
                "    print(\"✅ CloudLeecher Backend is Online!\")\n",
                "    print(\"🌍 Frontend App: https://cloudleecher.web.app\")\n",
                "    print(\"📋 Copy the PUBLIC URL and API KEY into the CloudLeecher Frontend app.\")\n",
                "\n",
                "    # Keep cell running to keep thread alive\n",
                "    while True:\n",
                "        time.sleep(10)\n",
                "except Exception as e:\n",
                "    print(f\"❌ Failed to start Ngrok: {e}\")"
            ]
            cell['source'] = launch_code
            updated_launch = True

    if updated_app and updated_launch:
        print(f"Writing updated notebook to {NOTEBOOK_PATH}...")
        with open(NOTEBOOK_PATH, 'w', encoding='utf-8') as f:
            json.dump(nb, f, indent=2)
        print("Success.")
    else:
        print(f"Error: Could not find all cells to update. App: {updated_app}, Launch: {updated_launch}")

if __name__ == "__main__":
    update_notebook()
