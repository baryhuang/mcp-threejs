# mcp-threejs

# MCP Threejs: Online 3D Resource Connector for Three.js
[![Docker Hub](https://img.shields.io/docker/v/buryhuang/mcp-server-threejs?label=Docker%20Hub)](https://hub.docker.com/r/buryhuang/mcp-server-threejs)

## Overview
This MCP server enables AI assistants like Claude to efficiently find and utilize pre-built 3D models for Three.js scenes. It solves the scalability challenge of coding Three.js applications from scratch by providing direct access to downloadable 3D resources via natural language search. Currently integrated with Sketchfab, it returns only models available for download along with their format details, making it easy to incorporate existing assets into your Three.js projects.

## Purpose
The primary purpose of this tool is to provide directly usable online 3D resources that are compatible with Three.js. By leveraging pre-built 3D models as building blocks, this tool significantly reduces the computational overhead and token consumption that would otherwise be required for coding complex Three.js scenes from scratch. AI assistants can find the most relevant models through natural language queries, enabling rapid prototyping and development of 3D web applications.

## Features

- 🔍 Direct search for Three.js-compatible 3D models via Sketchfab API
- 🚀 FastAPI-based server with async support
- ⚡ Fast response times with lightweight implementation
- ✅ Automatic filtering for downloadable models only
- 📊 Format information with file sizes for each model
- 🔐 OAuth2 authentication for Sketchfab API
- 🔄 Automatic token refresh when access tokens expire
- 💾 Credential persistence between sessions

## Roadmap

The project aims to expand support for additional 3D model repositories and enhance functionality:

### Todo List
- [ ] Integrate with TurboSquid marketplace
- [ ] Support for CGTrader API
- [ ] Integration with Free3D repository
- [ ] Add functionality to preview models directly in Claude
- [ ] Create a unified API across all supported 3D repositories

## Installation

### Using pip

```bash
pip install mcp-server-threejs
```

## Configuration

Customize through environment variables:

- OAuth2 credentials (required for getting download links):
  ```bash
  # All credentials are needed for full functionality
  docker run \
    -e SKETCHFAB_ACCESS_TOKEN=your_access_token \
    -e SKETCHFAB_REFRESH_TOKEN=your_refresh_token \
    -e SKETCHFAB_CLIENT_ID=your_client_id \
    -e SKETCHFAB_CLIENT_SECRET=your_client_secret \
    ...
  ```

## Authentication

This tool uses OAuth2 for Sketchfab authentication, which provides several benefits:

1. **Better Security**: OAuth2 is more secure than API key authentication
2. **Token Refresh**: Access tokens can be automatically refreshed when they expire
3. **Limited Permissions**: OAuth2 allows for more granular permission scopes

### Obtaining OAuth2 Credentials

To use the link retrieval functionality, you'll need OAuth2 credentials from Sketchfab:

1. Register an application at https://sketchfab.com/developers/apps
2. Set the OAuth redirect URI to a valid endpoint where you can capture the authorization code
3. Use the authorization code flow to obtain access and refresh tokens

### Credential Storage

The tool can store OAuth2 credentials locally in `~/.sketchfab_credentials.json` for persistence between sessions. This file contains:

- Access token
- Refresh token
- Client ID
- Client secret
- Token expiry timestamp

## Available Tools

The server provides the following tools:

### threejs_search_models
Search for downloadable 3D models on Sketchfab that match your query.

**Input Schema:**
```json
{
    "query": {
        "type": "string",
        "description": "Search term for 3D models (e.g., 'car', 'house', 'character')"
    }
}
```

**Response Format:**
```json
{
    "downloadable_models": [
        {
            "uid": "model-id",
            "name": "Model Name",
            "description": "Model description",
            "viewerUrl": "https://sketchfab.com/...",
            "embedUrl": "https://sketchfab.com/...",
            "thumbnailUrl": "https://media.sketchfab.com/...",
            "user": "creator_username",
            "formats": {
                "glb": 12345678,
                "gltf": 23456789,
                "usdz": 34567890
            }
        }
    ]
}
```

### threejs_get_gltf_model_url
Get direct URL of a GLTF file for a Sketchfab model without downloading it (requires OAuth2 authentication).

**Input Schema:**
```json
{
    "model_id": {
        "type": "string", 
        "description": "The uid of the model returned in the Sketchfab search response."
    }
}
```

**Response Format:**
```json
{
    "model_name": "Example Model",
    "model_id": "abc123",
    "gltf_url": "https://download.sketchfab.com/models/abc123/gltf/example.gltf"
}
```

## Docker Support

### Multi-Architecture Builds
Official images support 2 platforms:
```bash
# Build and push using buildx
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 \
  -t buryhuang/mcp-server-threejs:latest \
  --push .
```

### Supported Platforms
- linux/amd64
- linux/arm64

### Option 1: Use Prebuilt Image (Docker Hub)

```bash
docker pull buryhuang/mcp-server-threejs:latest
```

### Option 2: Local Development Build

```bash
docker build -t mcp-server-threejs .
```

### Running the Container

```bash
docker run \
  -e SKETCHFAB_ACCESS_TOKEN=your_access_token \
  -e SKETCHFAB_REFRESH_TOKEN=your_refresh_token \
  -e SKETCHFAB_CLIENT_ID=your_client_id \
  -e SKETCHFAB_CLIENT_SECRET=your_client_secret \
  buryhuang/mcp-server-threejs:latest
```

### Persistent Credentials

To use persistent credentials storage with Docker:

```bash
docker run \
  -v ~/.sketchfab_credentials.json:/root/.sketchfab_credentials.json \
  buryhuang/mcp-server-threejs:latest
```

## Integration with Claude Desktop

Configure the MCP server in your Claude Desktop settings:

```json
{
  "mcpServers": {
    "threejs": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "SKETCHFAB_ACCESS_TOKEN=your_access_token",
        "-e",
        "SKETCHFAB_REFRESH_TOKEN=your_refresh_token",
        "-e",
        "SKETCHFAB_CLIENT_ID=your_client_id",
        "-e",
        "SKETCHFAB_CLIENT_SECRET=your_client_secret",
        "-v",
        "~/.sketchfab_credentials.json:/root/.sketchfab_credentials.json",
        "buryhuang/mcp-server-threejs:latest"
      ]
    }
  }
}
```

## Using in Claude Desktop

Example prompts:
- "Find me downloadable car models"
- "Search for realistic human character models"
- "Find low-poly animal models I can download"
- "Get the GLTF URL for the spaceship model with ID abc123"

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the terms included in the LICENSE file.