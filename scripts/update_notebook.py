import json
import secrets
import os

NOTEBOOK_PATH = 'backend/CloudLeecher.ipynb'
APP_PATH = 'backend/app.py'

def main():
    # Read the new app.py
    with open(APP_PATH, 'r') as f:
        app_code = f.read()

    # Load notebook
    with open(NOTEBOOK_PATH, 'r') as f:
        nb = json.load(f)

    # Find step 4 (Create API Backend) and step 5 (Launch Public Server)
    step4_cell = None
    step5_cell = None

    for cell in nb['cells']:
        if cell.get('metadata', {}).get('id') == 'step4_code':
            step4_cell = cell
        elif cell.get('metadata', {}).get('id') == 'step5_code':
            step5_cell = cell

    if not step4_cell:
        print("Error: Step 4 cell not found")
        return
    if not step5_cell:
        print("Error: Step 5 cell not found")
        return

    # Update Step 4: Write app.py
    # We need to prepend %%writefile app.py to the content
    # And handle line endings correctly for JSON list of strings
    app_lines = app_code.splitlines(keepends=True)
    step4_cell['source'] = ["%%writefile app.py\n"] + app_lines

    # Update Step 5: Launch logic
    # We want to generate a key and pass it to subprocess
    new_step5_code = [
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
        "api_key = secrets.token_urlsafe(16)\n",
        "\n",
        "# 3. Cleanup Old Processes (Port 5000)\n",
        "ngrok.kill()\n",
        "os.system(\"fuser -k 5000/tcp > /dev/null 2>&1\")\n",
        "\n",
        "# 4. Start Flask App in Background\n",
        "log_file = open(\"flask.log\", \"w\")\n",
        "env = os.environ.copy()\n",
        "env['CLOUDLEECHER_API_KEY'] = api_key\n",
        "subprocess.Popen([sys.executable, \"app.py\"], stdout=log_file, stderr=log_file, env=env)\n",
        "time.sleep(3)  # Allow Flask to initialize\n",
        "\n",
        "# 5. Open Ngrok Tunnel\n",
        "try:\n",
        "    public_url = ngrok.connect(5000).public_url\n",
        "    print(\"\\n\" + \"=\"*60)\n",
        "    print(f\"🔗 PUBLIC URL: {public_url}\")\n",
        "    print(f\"🔑 API KEY:    {api_key}\")\n",
        "    print(\"=\"*60 + \"\\n\")\n",
        "    print(\"✅ CloudLeecher Backend is Online!\")\n",
        "    print(\"🌍 Frontend App: https://cloudleecher.web.app\")\n",
        "    print(\"📋 Copy the PUBLIC URL and API KEY into the CloudLeecher Frontend settings.\")\n",
        "\n",
        "    # Keep cell running to keep thread alive\n",
        "    while True:\n",
        "        time.sleep(10)\n",
        "except Exception as e:\n",
        "    print(f\"❌ Failed to start Ngrok: {e}\")"
    ]

    step5_cell['source'] = new_step5_code

    # Save notebook
    with open(NOTEBOOK_PATH, 'w') as f:
        json.dump(nb, f, indent=2)

    print("Notebook updated successfully.")

if __name__ == '__main__':
    main()
