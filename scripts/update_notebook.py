import json
import os

NOTEBOOK_PATH = 'backend/CloudLeecher.ipynb'
APP_PY_PATH = 'backend/app.py'

def update_notebook():
    with open(NOTEBOOK_PATH, 'r') as f:
        nb = json.load(f)

    with open(APP_PY_PATH, 'r') as f:
        app_code = f.read()

    # 1. Update %%writefile app.py cell
    found_app_cell = False
    for cell in nb['cells']:
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])
            if '%%writefile app.py' in source:
                cell['source'] = ['%%writefile app.py\n', app_code]
                found_app_cell = True
                print("✅ Updated app.py cell")
                break

    if not found_app_cell:
        print("❌ Could not find app.py cell")
        return

    # 2. Update Launch Cell
    found_launch_cell = False
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
        "    print(\"❌ Error: Ngrok Auth Token not found! Please add 'NGROK-AUTHTOKEN' to Colab Secrets.\")\n",
        "    raise e\n",
        "\n",
        "# 2. Generate Secure API Key\n",
        "api_key = secrets.token_hex(16)\n",
        "print(\"\\n\" + \"=\"*60)\n",
        "print(f\"🔑 API KEY: {api_key}\")\n",
        "print(\"⚠️ COPY THIS KEY! You will need it to connect the frontend.\")\n",
        "print(\"=\"*60 + \"\\n\")\n",
        "\n",
        "# 3. Cleanup Old Processes\n",
        "ngrok.kill()\n",
        "os.system(\"fuser -k 5000/tcp > /dev/null 2>&1\")\n",
        "\n",
        "# 4. Start Flask App in Background\n",
        "log_file = open(\"flask.log\", \"w\")\n",
        "env = os.environ.copy()\n",
        "env[\"CLOUDLEECHER_API_KEY\"] = api_key\n",
        "subprocess.Popen([sys.executable, \"app.py\"], stdout=log_file, stderr=log_file, env=env)\n",
        "time.sleep(3)  # Allow Flask to initialize\n",
        "\n",
        "# 5. Open Ngrok Tunnel\n",
        "try:\n",
        "    public_url = ngrok.connect(5000).public_url\n",
        "    print(f\"🔗 PUBLIC URL: {public_url}\")\n",
        "    print(\"✅ CloudLeecher Backend is Online!\")\n",
        "    print(\"🌍 Frontend App: https://cloudleecher.web.app\")\n",
        "    print(\"📋 1. Copy the PUBLIC URL\")\n",
        "    print(\"📋 2. Copy the API KEY\")\n",
        "    print(\"📋 3. Paste them into the CloudLeecher Frontend settings.\")\n",
        "\n",
        "    # Keep cell running\n",
        "    while True:\n",
        "        time.sleep(10)\n",
        "except Exception as e:\n",
        "    print(f\"❌ Failed to start Ngrok: {e}\")\n"
    ]

    for cell in nb['cells']:
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])
            if 'ngrok.connect' in source and 'subprocess.Popen' in source:
                cell['source'] = launch_code
                found_launch_cell = True
                print("✅ Updated Launch cell")
                break

    if not found_launch_cell:
        print("❌ Could not find Launch cell")
        return

    with open(NOTEBOOK_PATH, 'w') as f:
        json.dump(nb, f, indent=2)
        # Add newline at end of file
        f.write('\n')

if __name__ == "__main__":
    update_notebook()
