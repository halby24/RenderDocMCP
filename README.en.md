# RenderDoc MCP Server

[日本語](README.md) | **[English]**

An MCP server that runs as a RenderDoc UI extension, enabling AI assistants to access RenderDoc capture data and assist with graphics debugging.

## Architecture

```
Claude/AI Client (stdio)
        │
        ▼
MCP Server Process (Python + FastMCP 2.0)
        │ File-based IPC (%TEMP%/renderdoc_mcp/)
        ▼
RenderDoc Process (Extension)
```

Communication is done via file-based IPC since RenderDoc's embedded Python doesn't have the socket module.

## Setup

### 1. Install RenderDoc Extension

```bash
python scripts/install_extension.py
```

The extension will be installed to `%APPDATA%\qrenderdoc\extensions\renderdoc_mcp_bridge`.

### 2. Enable Extension in RenderDoc

1. Launch RenderDoc
2. Tools > Manage Extensions
3. Enable "RenderDoc MCP Bridge"

### 3. Install MCP Server

```bash
uv tool install .
uv tool update-shell  # Add to PATH
```

After restarting your shell, the `renderdoc-mcp` command will be available.

> **Note**: Use `--editable` flag for development to apply source code changes immediately.
> For stable installation, use `uv tool install .`.

### 4. Configure MCP Client

#### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "renderdoc-mcp"
    }
  }
}
```

#### Claude Code (Cursor)

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "renderdoc-mcp"
    }
  }
}
```

## Usage

1. Launch RenderDoc and open a capture file (.rdc)
2. Access RenderDoc data from MCP clients (Claude, etc.)

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_capture_status` | Check capture load status |
| `get_draw_calls` | Get draw call list in hierarchical structure |
| `get_frame_summary` | Get frame statistics and top-level markers |
| `find_draws_by_shader` | Find draw calls using specific shader (partial match) |
| `find_draws_by_texture` | Find draw calls using specific texture (partial match) |
| `find_draws_by_resource` | Find draw calls using specific resource ID (exact match) |
| `get_draw_call_details` | Get detailed information about a specific draw call |
| `get_shader_info` | Get shader source code and constant buffer values |
| `get_buffer_contents` | Get buffer contents (Base64) |
| `get_texture_info` | Get texture metadata |
| `get_texture_data` | Get texture pixel data (Base64) |
| `get_pipeline_state` | Get pipeline state |
| `list_captures` | List all .rdc files in directory |
| `open_capture` | Open a capture file |

## Examples

### Get Draw Call List

```
get_draw_calls(include_children=true)
```

### Get Shader Information

```
get_shader_info(event_id=123, stage="pixel")
```

### Get Pipeline State

```
get_pipeline_state(event_id=123)
```

### Get Texture Data

```
# Get mip 0 of 2D texture
get_texture_data(resource_id="ResourceId::123")

# Get specific mip level
get_texture_data(resource_id="ResourceId::123", mip=2)

# Get specific cube map face (0=X+, 1=X-, 2=Y+, 3=Y-, 4=Z+, 5=Z-)
get_texture_data(resource_id="ResourceId::456", slice=3)

# Get specific depth slice of 3D texture
get_texture_data(resource_id="ResourceId::789", depth_slice=5)
```

### Get Partial Buffer Data

```
# Get entire buffer
get_buffer_contents(resource_id="ResourceId::123")

# Get 512 bytes from offset 256
get_buffer_contents(resource_id="ResourceId::123", offset=256, length=512)
```

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- RenderDoc 1.20+

> **Note**: Tested only on Windows + DirectX 11.
> May work on Linux/macOS + Vulkan/OpenGL but untested.

## License

MIT
