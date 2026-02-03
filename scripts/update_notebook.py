import json
import os

NOTEBOOK_PATH = "backend/CloudLeecher.ipynb"
APP_PATH = "backend/app.py"

def update_notebook():
    if not os.path.exists(NOTEBOOK_PATH):
        print(f"Error: {NOTEBOOK_PATH} not found.")
        return

    if not os.path.exists(APP_PATH):
        print(f"Error: {APP_PATH} not found.")
        return

    with open(APP_PATH, "r") as f:
        app_code = f.read()

    with open(NOTEBOOK_PATH, "r") as f:
        notebook = json.load(f)

    # 1. Update step3_code (Start Aria2)
    step3_launch_code = [
        "import subprocess\n",
        "import os\n",
        "\n",
        "# Define Temp Directory for Initial Downloads\n",
        "TEMP_DIR = \"/content/temp_downloads\"\n",
        "os.makedirs(TEMP_DIR, exist_ok=True)\n",
        "\n",
        "# Start Aria2c as a daemon process\n",
        "cmd = [\n",
        "    \"aria2c\",\n",
        "    \"--enable-rpc\",\n",
        "    \"--rpc-listen-all=true\",\n",
        "    \"--rpc-allow-origin-all\",\n",
        "    f\"--dir={TEMP_DIR}\",\n",
        "    \"--file-allocation=none\",\n",
        "    \"--max-connection-per-server=16\",\n",
        "    \"--split=16\",\n",
        "    \"--min-split-size=1M\",\n",
        "    \"--seed-time=0\",\n",
        "    \"--daemon=true\"\n",
        "]\n",
        "\n",
        "subprocess.run(\n",
        "    cmd,\n",
        "    stdout=subprocess.DEVNULL,\n",
        "    stderr=subprocess.DEVNULL\n",
        ")\n",
        "\n",
        "print(\"✅ Aria2 Background Service Started (DIR: /content/temp_downloads).\")\n"
    ]

    step3_found = False
    for cell in notebook["cells"]:
        if cell.get("metadata", {}).get("id") == "step3_code":
            print("Found step3_code cell. Updating Aria2 launch logic...")
            cell["source"] = step3_launch_code
            step3_found = True
            break

    if not step3_found:
        print("Warning: step3_code cell not found!")

    # 2. Update step4_code (Write app.py)
    step4_found = False
    for cell in notebook["cells"]:
        if cell.get("metadata", {}).get("id") == "step4_code":
            print("Found step4_code cell. Updating app.py content...")
            # cell["source"] is a list of strings
            new_source = ["%%writefile app.py\n"] + [line + "\n" for line in app_code.splitlines()]
            # Clean up double newlines if any
            new_source = [s.replace("\n\n", "\n") if s.endswith("\n\n") else s for s in new_source]
            cell["source"] = new_source
            step4_found = True
            break

    if not step4_found:
        print("Warning: step4_code cell not found!")

    # 3. Update step5_code (Launch Logic)
    step5_launch_code = [
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
        "# 3. Generate Secure API Key\n",
        "api_key = str(uuid.uuid4())\n",
        "os.environ[\"CLOUDLEECHER_API_KEY\"] = api_key\n",
        "\n",
        "# 4. Start Flask App in Background\n",
        "log_file = open(\"flask.log\", \"w\")\n",
        "# Pass the environment with the API Key\n",
        "env = os.environ.copy()\n",
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
        "    print(\"📋 Copy the URL and API KEY above and paste them into the CloudLeecher Frontend app.\")\n",
        "\n",
        "    # Keep cell running to keep thread alive\n",
        "    while True:\n",
        "        time.sleep(10)\n",
        "except Exception as e:\n",
        "    print(f\"❌ Failed to start Ngrok: {e}\")\n"
    ]

    step5_found = False
    for cell in notebook["cells"]:
        if cell.get("metadata", {}).get("id") == "step5_code":
            print("Found step5_code cell. Updating launch logic...")
            cell["source"] = step5_launch_code
            step5_found = True
            break

    if not step5_found:
        print("Warning: step5_code cell not found!")

    with open(NOTEBOOK_PATH, "w") as f:
        json.dump(notebook, f, indent=2)

    print(f"Successfully updated {NOTEBOOK_PATH}")

if __name__ == "__main__":
    update_notebook()
