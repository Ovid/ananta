# Ananta arXiv Explorer

Ananta lets you ask plain-English questions across dozens of arXiv papers at once. Add papers to a topic, type a question, and Ananta writes and runs code to dig through your documents — iterating until it finds a real answer, with citations you can verify against the source.

## First Research Session

1. **Create a topic** — Click the `+` button in the left sidebar and name it (e.g., "Abiogenesis")
2. **Search for papers** — Click the search icon in the header and search arXiv (e.g., "origin of life RNA world")
3. **Add papers** — Select papers from the results and click "Add". Papers download in the background (there's a 3-second delay between downloads to respect arXiv's rate limits)
4. **Ask a question** — Once papers are downloaded, type a question like "What are the main theories for the origin of life?"
5. **Wait for the answer** — The status bar shows the current phase and token count. Queries typically take 1-3 minutes, but complex queries might be longer.
6. **Inspect the trace** — Click "View trace" at the bottom of any answer to see the step-by-step reasoning
7. **Check citations** — Click the checkmark icon in the header to verify citations against the source documents (experimental!)

## Prerequisites

- **Docker** — see [Installing Docker](#installing-docker) below if you don't have it
- An **LLM API key** — see [Getting an API Key](#getting-an-api-key) below
- **Model selection** — set `ANANTA_MODEL` (see [Choosing a Model](#choosing-a-model) below)

## Setup

If you're comfortable with software development, you can run `./arxiv-explorer/arxiv-explorer.sh` to launch this quickly. It still requires Docker because the Python code runs in a locked-down Docker container. Otherwise, you `cd arxiv-explorer; docker compose up`, after ensuring the prerequisites are satisfied. Note, the docker and shell script solutions share different data storage, so using one means it won't see what you put in the other.

### Installing Docker

Docker runs the code sandbox that Ananta uses to safely execute LLM-generated code. If you already have Docker installed, skip to [Quick Start](#quick-start).

**macOS**

1. Download [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Open the downloaded `.dmg` file and drag Docker to your Applications folder
3. Launch Docker from Applications — you'll see a whale icon in your menu bar when it's running

**Windows**

1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Run the installer and follow the prompts (enable WSL 2 when asked)
3. Restart your computer if prompted
4. Launch Docker Desktop from the Start menu — you'll see a whale icon in your system tray when it's running
5. Open **PowerShell** or **Command Prompt** to run the commands below

**Linux (Ubuntu/Debian)**

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Allow your user to run Docker without sudo
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker run hello-world
```

For other Linux distributions, see the [official Docker docs](https://docs.docker.com/engine/install/).

**Verify Docker is working**

Open a terminal and run:

```bash
docker --version
```

You should see something like `Docker version 27.x.x`. If you get "command not found", Docker isn't installed or isn't in your PATH.

### Getting an API Key

You need an API key from one of the supported LLM providers. Pick whichever you prefer:

**OpenAI**

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and sign in (or create an account)
2. Click "Create new secret key" and copy it
3. Set it: `export ANANTA_API_KEY="sk-..."`

**Anthropic (Claude)**

1. Go to [console.anthropic.com](https://console.anthropic.com/) and sign in (or create an account)
2. Go to Settings > API Keys, click "Create Key", and copy it
3. Set it: `export ANANTA_API_KEY="sk-ant-..."`

**Google (Gemini)**

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in with your Google account
2. Click "Create API Key", select a project, and copy the key
3. Set it: `export ANANTA_API_KEY="your-key-here"`

All three providers require billing to be set up for production use, though Google offers a free tier with up to 1,000 daily requests.

### Choosing a Model

Set `ANANTA_MODEL` to tell Ananta which LLM to use. These are good budget-friendly options that work well for paper exploration:

| Provider | Model | `ANANTA_MODEL` value | Approximate cost |
|----------|-------|---------------------|-----------------|
| OpenAI | GPT-5 mini | `gpt-5-mini` | $0.25 / $2.00 per 1M tokens |
| Anthropic | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | $1.00 / $5.00 per 1M tokens |
| Google | Gemini 2.5 Flash | `gemini/gemini-2.5-flash` | $0.30 / $2.50 per 1M tokens |

Costs shown are input / output per million tokens. A typical research session uses roughly 100K–500K tokens.

For the best balance of cost and quality, we recommend **`gpt-5-mini`** (OpenAI) or **`gemini/gemini-2.5-flash`** (Google).

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/ananta.git
cd ananta/arxiv-explorer

# 2. Set your API key and model
export ANANTA_API_KEY="sk-..."
export ANANTA_MODEL="gpt-5-mini"   # recommended: inexpensive with great results

# 3. Run
docker compose up
```

Visit `http://localhost:8000` in your browser.

## Troubleshooting

**Docker not running**
Ananta needs Docker to run code in a sandbox. On macOS and Windows, open Docker Desktop from your Applications/Start menu and wait for the whale icon to appear. On Linux, run `sudo systemctl start docker`.

**API key not set**
Set `ANANTA_API_KEY` as an environment variable before running.

**Papers fail to download**
arXiv may be temporarily unavailable. Wait a minute and try again. Some papers with non-standard formats may fail to parse.

**Context budget at 80%+**
Your documents and conversation history are approaching the model's context limit. Consider clearing the conversation history or switching to a model with a larger context window.

**Port already in use**
Use `--port 8080` (or another port) if 8000 is taken.

## Notice

This is **experimental software**. The web interface is under active development. Some features may be incomplete or change without notice.
