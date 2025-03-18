import json
import logging
from typing import Any, Dict, List, Optional
import requests
import os
import tempfile
import zipfile
import io
import shutil
import argparse
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI
import time

from mcp.server import Server
import mcp.types as types
import mcp.server.stdio
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_threejs")

class SketchfabClient:
    @classmethod
    def load_from_file(cls, credentials_file: Optional[str] = None):
        """Load credentials from file and create a new client instance"""
        if not credentials_file:
            # Use default location in user's home directory
            home_dir = os.path.expanduser("~")
            credentials_file = os.path.join(home_dir, ".sketchfab_credentials.json")
            
        try:
            if not os.path.exists(credentials_file):
                logger.warning(f"Credentials file not found: {credentials_file}")
                return None
                
            with open(credentials_file, 'r') as f:
                credentials = json.load(f)
                
            logger.info(f"Loaded credentials from {credentials_file}")
            
            # Create new client with loaded credentials
            client = cls(
                access_token=credentials.get("access_token", ""),
                refresh_token=credentials.get("refresh_token", ""),
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", "")
            )
            
            # Set expiry if available
            if "token_expiry" in credentials and credentials["token_expiry"]:
                client.token_expiry = credentials["token_expiry"]
                
            return client
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {str(e)}")
            return None
        
    def __init__(self, access_token: Optional[str] = None, refresh_token: Optional[str] = None, 
                 client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.api_url = "https://api.sketchfab.com/v3"
        self.oauth_url = "https://sketchfab.com/oauth2/token/"
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_expiry = None
        
        # Set default expiry if access token exists (30 days from now)
        if self.access_token and not self.token_expiry:
            self.token_expiry = time.time() + (30 * 24 * 60 * 60)  # 30 days in seconds
        
    def store_updated_credentials(self, credentials_file: Optional[str] = None) -> bool:
        """Store updated credentials to file"""
        if not credentials_file:
            # Use default location in user's home directory
            home_dir = os.path.expanduser("~")
            credentials_file = os.path.join(home_dir, ".sketchfab_credentials.json")
            
        try:
            # Store only sensitive data if it exists
            credentials = {
                "access_token": self.access_token if self.access_token else "",
                "refresh_token": self.refresh_token if self.refresh_token else "",
                "client_id": self.client_id if self.client_id else "",
                "client_secret": self.client_secret if self.client_secret else "",
                "token_expiry": self.token_expiry if self.token_expiry else 0
            }
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(credentials_file), exist_ok=True)
            
            with open(credentials_file, 'w') as f:
                json.dump(credentials, f)
                
            logger.info(f"Stored updated credentials to {credentials_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store credentials: {str(e)}")
            return False
        
    def refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token"""
        if not all([self.refresh_token, self.client_id, self.client_secret]):
            logger.warning("Cannot refresh token: missing refresh_token, client_id, or client_secret")
            return False
            
        try:
            logger.info("Attempting to refresh access token")
            
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': self.refresh_token
            }
            
            response = requests.post(self.oauth_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            
            # Update refresh token if a new one is provided
            if 'refresh_token' in token_data:
                self.refresh_token = token_data.get('refresh_token')
                
            # Update expiry if provided
            if 'expires_in' in token_data:
                self.token_expiry = time.time() + token_data.get('expires_in')
            else:
                # Default to 30 days if not specified
                self.token_expiry = time.time() + (30 * 24 * 60 * 60)
                
            logger.info("Successfully refreshed access token")
            
            # Store updated credentials
            self.store_updated_credentials()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh access token: {str(e)}")
            return False
        
    def ensure_valid_token(self):
        """Check if token needs refresh and refresh if needed"""
        if not self.access_token:
            return False
            
        if self.token_expiry and time.time() > self.token_expiry - 300:  # Refresh 5 minutes before expiry
            logger.info("Access token is about to expire, refreshing")
            return self.refresh_access_token()
            
        return True
        
    def get_auth_headers(self):
        """Return authorization headers if access token is available"""
        headers = {}
        
        # Try to refresh token if needed
        self.ensure_valid_token()
        
        if self.access_token:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            logger.info(f"Using OAuth2 authentication header")
        else:
            logger.info("No access token available, making unauthenticated request")
        return headers
        
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for downloadable models on Sketchfab API"""
        try:
            params = {"q": query}
            if limit:
                params["count"] = min(limit, 24)  # API limit is 24
            
            logger.info(f"Search request params: {params}")
                
            response = requests.get(
                f"{self.api_url}/search",
                params=params
            )
            response.raise_for_status()
            
            logger.info(f"Search response status: {response.status_code}")
            data = response.json()
            
            # Extract only downloadable models from the results
            downloadable_models = []
            if "results" in data and "models" in data["results"]:
                for model in data["results"]["models"]:
                    isDownloadable = model.get("isDownloadable", False)
                    if not isDownloadable:
                        logger.info(f"Skipping model {model.get('name', model.get('uid', ''))} because it is not downloadable")
                        continue
                    model_data = {
                        "uid": model.get("uid", ""),
                        "name": model.get("name", ""),
                        "description": model.get("description", ""),
                        "viewerUrl": model.get("viewerUrl", ""),
                        "embedUrl": model.get("embedUrl", ""),
                        "thumbnailUrl": model.get("thumbnails", {}).get("images", [{}])[0].get("url", "") if model.get("thumbnails") else "",
                        "user": model.get("user", {}).get("username", "") if model.get("user") else "",
                        "isDownloadable": isDownloadable,
                        "formats": {
                            format_name: format_data.get("size", 0) 
                            for format_name, format_data in model.get("archives", {}).items()
                            if format_data
                        }
                    }
                    downloadable_models.append(model_data)
            
            return downloadable_models
            
        except Exception as e:
            logger.error(f"Failed to search Sketchfab: {str(e)}")
            return []
    
    def get_model(self, model_id: str) -> Dict:
        """Get detailed information about a model by ID"""
        try:
            headers = self.get_auth_headers()
            logger.info(f"Get model request for ID: {model_id}")
            
            response = requests.get(
                f"{self.api_url}/models/{model_id}",
                headers=headers
            )
            response.raise_for_status()
            
            logger.info(f"Get model response status: {response.status_code}")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get model details: {str(e)}")
            raise ValueError(f"Failed to get model details: {str(e)}")
            
    def get_download_link(self, model_id: str) -> Dict:
        """Get download links for a model"""
        try:
            if not self.access_token:
                raise ValueError("OAuth2 access token is required for downloading models")
            
            headers = self.get_auth_headers()
            logger.info(f"Get download link request for ID: {model_id}")
                
            response = requests.get(
                f"{self.api_url}/models/{model_id}/download",
                headers=headers
            )
            response.raise_for_status()
            
            logger.info(f"Get download link response status: {response.status_code}")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get download link: {str(e)}")
            raise ValueError(f"Failed to get download link: {str(e)}")
            
    def download_model(self, download_url: str, output_path: Optional[str] = None) -> Dict:
        """Download a model file from the given URL"""
        try:
            # Download the file
            logger.info(f"Downloading model from URL: {download_url}")
            
            response = requests.get(download_url, stream=True, timeout=300)  # 5 minute timeout
            response.raise_for_status()
            
            logger.info(f"Download response status: {response.status_code}")
            logger.info(f"Download content type: {response.headers.get('Content-Type')}")
            logger.info(f"Download content length: {response.headers.get('Content-Length')}")
            # Determine if it's a ZIP file
            is_zip = False
            content = response.content
            if len(content) >= 4 and content[0:4] == b'PK\x03\x04':
                is_zip = True
                
            # Determine filename and path
            if not output_path:
                # Create a temporary file
                if is_zip:
                    temp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
                else:
                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                output_path = temp_file.name
                temp_file.close()
                
            # Save the file
            with open(output_path, 'wb') as f:
                f.write(content)
                
            # Handle ZIP extraction
            extracted_files = []
            if is_zip:
                # Create extraction directory
                extract_dir = output_path + "_extracted"
                os.makedirs(extract_dir, exist_ok=True)
                
                # Extract the ZIP file
                with zipfile.ZipFile(output_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                    extracted_files = zip_ref.namelist()
                    
            return {
                "output_path": output_path,
                "is_zip": is_zip,
                "extract_dir": extract_dir if is_zip else None,
                "extracted_files": extracted_files
            }
                
        except Exception as e:
            logger.error(f"Failed to download model: {str(e)}")
            raise ValueError(f"Failed to download model: {str(e)}")


def get_oauth_credentials():
    """Get Sketchfab OAuth2 credentials from environment variables, command-line arguments or saved file"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Threejs Server for Sketchfab model search')
    parser.add_argument('--sketchfab_access_token', type=str, help='Sketchfab OAuth2 access token for authentication')
    parser.add_argument('--sketchfab_refresh_token', type=str, help='Sketchfab OAuth2 refresh token for renewing access')
    parser.add_argument('--sketchfab_client_id', type=str, help='Sketchfab OAuth2 client ID')
    parser.add_argument('--sketchfab_client_secret', type=str, help='Sketchfab OAuth2 client secret')
    parser.add_argument('--credentials_file', type=str, help='Path to file with stored OAuth2 credentials')
    args, _ = parser.parse_known_args()
    
    # Try to load from credentials file first
    credentials_file = args.credentials_file
    if not credentials_file:
        home_dir = os.path.expanduser("~")
        credentials_file = os.path.join(home_dir, ".sketchfab_credentials.json")
    
    # Initialize with empty values
    access_token = ""
    refresh_token = ""
    client_id = ""
    client_secret = ""
    token_expiry = 0
    
    # Try to load from file first
    try:
        if os.path.exists(credentials_file):
            logger.info(f"Loading credentials from file: {credentials_file}")
            with open(credentials_file, 'r') as f:
                file_credentials = json.load(f)
                access_token = file_credentials.get("access_token", "")
                refresh_token = file_credentials.get("refresh_token", "")
                client_id = file_credentials.get("client_id", "")
                client_secret = file_credentials.get("client_secret", "")
                token_expiry = file_credentials.get("token_expiry", 0)
    except Exception as e:
        logger.error(f"Error loading credentials from file: {str(e)}")
    
    # Override with command line args or environment variables if provided
    access_token = args.sketchfab_access_token or os.getenv('SKETCHFAB_ACCESS_TOKEN', '') or access_token
    refresh_token = args.sketchfab_refresh_token or os.getenv('SKETCHFAB_REFRESH_TOKEN', '') or refresh_token
    client_id = args.sketchfab_client_id or os.getenv('SKETCHFAB_CLIENT_ID', '') or client_id
    client_secret = args.sketchfab_client_secret or os.getenv('SKETCHFAB_CLIENT_SECRET', '') or client_secret
    
    # Log status of credentials (securely)
    if access_token:
        logger.info("OAuth2 access token found")
        
        # Check if token is expired
        if token_expiry and time.time() > token_expiry:
            logger.warning("Access token is expired and will need to be refreshed")
    else:
        logger.warning("No access token found")
        
    if refresh_token:
        logger.info("OAuth2 refresh token found")
    else:
        logger.warning("No refresh token found - automatic token refresh will not be available")
        
    if client_id:
        logger.info("OAuth2 client ID found")
    else:
        logger.warning("No client ID found - automatic token refresh will not be available")
        
    if client_secret:
        logger.info("OAuth2 client secret found")
    else:
        logger.warning("No client secret found - automatic token refresh will not be available")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_expiry": token_expiry
    }


async def main():
    """Run the Threejs Server for Sketchfab model search"""
    logger.info("Threejs Server starting")
    
    # Log all environment variables for debugging (excluding sensitive values)
    env_vars = {k: v if not ('key' in k.lower() or 'token' in k.lower() or 'secret' in k.lower()) else '***' 
                for k, v in os.environ.items()}
    logger.info(f"Environment variables: {env_vars}")
    
    # Get Sketchfab OAuth credentials
    oauth_credentials = get_oauth_credentials()
    access_token = oauth_credentials["access_token"]
    refresh_token = oauth_credentials["refresh_token"]
    client_id = oauth_credentials["client_id"]
    client_secret = oauth_credentials["client_secret"]
    token_expiry = oauth_credentials.get("token_expiry", 0)
    
    if access_token:
        logger.info("Sketchfab OAuth2 access token provided and will be used for authentication")
        
        # Check if refresh is possible
        can_refresh = all([refresh_token, client_id, client_secret])
        if can_refresh:
            logger.info("Automatic token refresh is available")
        else:
            logger.warning("Some credentials for automatic token refresh are missing")
            
        # Check if token is expired or about to expire
        if token_expiry and time.time() > token_expiry - 300:  # 5 minutes before expiry
            logger.warning("Access token is expired or about to expire - will attempt to refresh on first use")
    else:
        logger.warning("No Sketchfab access token provided. Download functionality will be DISABLED.")
    
    server = Server("threejs")
    sketchfab_client = SketchfabClient(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret
    )
    
    # Set token expiry if available
    if token_expiry:
        sketchfab_client.token_expiry = token_expiry

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available tools"""
        tools = [
            types.Tool(
                name="threejs_search_models",
                description="Search for 3D models on Sketchfab that match your query.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term for 3D models (e.g., 'car', 'house', 'character')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (1-24, default: 10)"
                        }
                    },
                    "required": ["query"]
                },
            )
        ]
        
        # Add the download tool if access token is available
        if access_token:
            tools.append(
                types.Tool(
                    name="threejs_get_gltf_model_url",
                    description="Get direct url of a GLTF file for a Sketchfab model without downloading it",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "model_id": {
                                "type": "string",
                                "description": "The uid of the model returned in the Sketchfab search response."
                            }
                        },
                        "required": ["model_id"]
                    },
                )
            )
        
        return tools

    @server.call_tool()
    async def handle_invoke_tool(name: str, inputs: Dict[str, Any]) -> List[types.TextContent]:
        """Handle tool invocations"""
        try:
            search_tool_name = "threejs_search_models"
            get_gltf_url_tool_name = "threejs_get_gltf_model_url"

            if name == search_tool_name:
                query = inputs["query"]
                limit = inputs.get("limit", 10)
                results = sketchfab_client.search(query, limit)
                
                return [types.TextContent(type="text", text=json.dumps({
                    "models": results
                }, indent=2))]
                
            elif name == get_gltf_url_tool_name and access_token:
                model_id = inputs["model_id"]
                
                # Get model details first
                model = sketchfab_client.get_model(model_id)
                
                # Check if model is downloadable
                if not model.get("isDownloadable", False):
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": f"Model '{model.get('name', model_id)}' is not downloadable."
                    }, indent=2))]
                
                # Get download links
                download_links = sketchfab_client.get_download_link(model_id)
                
                # Check if gltf format is available
                if "gltf" not in download_links:
                    return [types.TextContent(type="text", text=json.dumps({
                        "error": f"GLTF format is not available for model '{model.get('name', model_id)}'.",
                        "available_formats": list(download_links.keys())
                    }, indent=2))]
                    
                gltf_url = download_links["gltf"]["url"]
                
                return [types.TextContent(type="text", text=json.dumps({
                    "model_name": model.get("name", model_id),
                    "model_id": model_id,
                    "gltf_url": gltf_url
                }, indent=2))]
                
            else:
                raise ValueError(f"Unknown tool: {name}")
                
        except Exception as e:
            logger.error(f"Error invoking tool {name}: {str(e)}")
            return [types.TextContent(type="text", text=json.dumps({
                "error": str(e)
            }, indent=2))]

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server running with stdio transport")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="threejs",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
