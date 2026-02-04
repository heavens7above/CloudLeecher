import json
import os

NOTEBOOK_PATH = 'backend/CloudLeecher.ipynb'
APP_PATH = 'backend/app.py'

def main():
    with open(APP_PATH, 'r') as f:
        app_code = f.read()

    with open(NOTEBOOK_PATH, 'r') as f:
        notebook = json.load(f)

    # Update step4_code (app.py generation)
    found_step4 = False
    for cell in notebook['cells']:
        if cell.get('metadata', {}).get('id') == 'step4_code':
            # Construct the source list properly
            source = ["%%writefile app.py\n"]
            # Split lines and keep newlines
            lines = app_code.splitlines(keepends=True)
            source.extend(lines)
            cell['source'] = source
            found_step4 = True
            print("✅ Updated step4_code (app.py)")
            break

    if not found_step4:
        print("❌ Could not find cell with id 'step4_code'")

    # Update step5_code (Launch logic)
    found_step5 = False
    launch_code = [
        "from pyngrok import ngrok\n",
        "from google.colab import userdata\n",
        "import subprocess\n",
        "import sys\n",
        "import time\n",
        "import os\n",
        "import uuid\n",
        "\n",
        "# 1. Authenticate Ngrok\n",
        "try:\n",
        "    AUTH_TOKEN = userdata.get(\"NGROK-AUTHTOKEN\")\n",
        "    ngrok.set_auth_token(AUTH_TOKEN)\n",
        "except Exception as e:\n",
        "    print(\"❌ Error: Ngrok Auth Token not found! Please add 'NGROK-AUTHTOKEN' to Colab Secrets (Key icon on the left).\")\n",
        "    raise e\n",
        "\n",
        "# 2. Cleanup Old Processes (Port 5000)\n",
        "ngrok.kill()\n",
        "os.system(\"fuser -k 5000/tcp > /dev/null 2>&1\")\n",
        "\n",
        "# 3. Generate API Key\n",
        "api_key = str(uuid.uuid4())\n",
        "print(f\"\\n🔑 GENERATED API KEY: {api_key}\")\n",
        "print(\"⚠️  Copy this key! You will need it to connect the Frontend.\")\n",
        "\n",
        "# 4. Start Flask App in Background\n",
        "log_file = open(\"flask.log\", \"w\")\n",
        "env = os.environ.copy()\n",
        "env[\"CLOUDLEECHER_API_KEY\"] = api_key\n",
        "\n",
        "subprocess.Popen([sys.executable, \"app.py\"], stdout=log_file, stderr=log_file, env=env)\n",
        "time.sleep(3)  # Allow Flask to initialize\n",
        "\n",
        "# 5. Open Ngrok Tunnel\n",
        "try:\n",
        "    public_url = ngrok.connect(5000).public_url\n",
        "    print(\"\\n\" + \"=\"*60)\n",
        "    print(f\"🔗 PUBLIC URL: {public_url}\")\n",
        "    print(\"=\"*60 + \"\\n\")\n",
        "    print(\"✅ CloudLeecher Backend is Online!\")\n",
        "    print(\"🌍 Frontend App: https://cloudleecher.web.app\")\n",
        "    print(\"📋 Copy the URL and API KEY above and paste them into the CloudLeecher Frontend app.\")\n",
        "\n",
        "    # Keep cell running to keep thread alive\n",
        "    while True:\n",
        "        time.sleep(10)\n",
        "except Exception as e:\n",
        "    print(f\"❌ Failed to start Ngrok: {e}\")"
    ]

    for cell in notebook['cells']:
        if cell.get('metadata', {}).get('id') == 'step5_code':
            cell['source'] = launch_code
            found_step5 = True
            print("✅ Updated step5_code (Launch logic)")
            break

    if not found_step5:
        print("❌ Could not find cell with id 'step5_code'")

    with open(NOTEBOOK_PATH, 'w') as f:
        json.dump(notebook, f, indent=2)

    print("Notebook update complete.")

if __name__ == '__main__':
    main()
