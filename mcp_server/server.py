"""
RenderDoc MCP Server
FastMCP 2.0 server providing access to RenderDoc capture data.
"""

from typing import Literal

from fastmcp import FastMCP

from .bridge.client import RenderDocBridge, RenderDocBridgeError
from .config import settings
from .shader_compiler import ShaderPerformanceAnalyzer, ShaderCompilerError

# Initialize FastMCP server
mcp = FastMCP(
    name="RenderDoc MCP Server",
)

# RenderDoc bridge client
bridge = RenderDocBridge(host=settings.renderdoc_host, port=settings.renderdoc_port)

# Shader performance analyzer (lazy init to avoid startup errors if compilers missing)
_analyzer: ShaderPerformanceAnalyzer | None = None


def _get_analyzer() -> ShaderPerformanceAnalyzer:
    """Get or create the shader performance analyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = ShaderPerformanceAnalyzer(
            malioc_path=settings.malioc_path,
            aoc_path=settings.aoc_path,
            mali_default_core=settings.mali_default_core,
            adreno_default_arch=settings.adreno_default_arch,
        )
    return _analyzer


@mcp.tool
def get_capture_status() -> dict:
    """
    Check if a capture is currently loaded in RenderDoc.
    Returns the capture status and API type if loaded.
    """
    return bridge.call("get_capture_status")


@mcp.tool
def get_draw_calls(
    include_children: bool = True,
    marker_filter: str | None = None,
    exclude_markers: list[str] | None = None,
    event_id_min: int | None = None,
    event_id_max: int | None = None,
    only_actions: bool = False,
    flags_filter: list[str] | None = None,
) -> dict:
    """
    Get the list of all draw calls and actions in the current capture.

    Args:
        include_children: Include child actions in the hierarchy (default: True)
        marker_filter: Only include actions under markers containing this string (partial match)
        exclude_markers: Exclude actions under markers containing these strings (list of partial matches)
        event_id_min: Only include actions with event_id >= this value
        event_id_max: Only include actions with event_id <= this value
        only_actions: If True, exclude marker actions (PushMarker/PopMarker/SetMarker)
        flags_filter: Only include actions with these flags (list of flag names, e.g. ["Drawcall", "Dispatch"])

    Returns a hierarchical tree of actions including markers, draw calls,
    dispatches, and other GPU events.
    """
    params: dict[str, object] = {"include_children": include_children}
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    if exclude_markers is not None:
        params["exclude_markers"] = exclude_markers
    if event_id_min is not None:
        params["event_id_min"] = event_id_min
    if event_id_max is not None:
        params["event_id_max"] = event_id_max
    if only_actions:
        params["only_actions"] = only_actions
    if flags_filter is not None:
        params["flags_filter"] = flags_filter
    return bridge.call("get_draw_calls", params)


@mcp.tool
def get_frame_summary() -> dict:
    """
    Get a summary of the current capture frame.

    Returns statistics about the frame including:
    - API type (D3D11, D3D12, Vulkan, etc.)
    - Total action count
    - Statistics: draw calls, dispatches, clears, copies, presents, markers
    - Top-level markers with event IDs and child counts
    - Resource counts: textures, buffers
    """
    return bridge.call("get_frame_summary")


@mcp.tool
def find_draws_by_shader(
    shader_name: str,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"] | None = None,
) -> dict:
    """
    Find all draw calls using a shader with the given name (partial match).

    Args:
        shader_name: Partial name to search for in shader names or entry points
        stage: Optional shader stage to search (if not specified, searches all stages)

    Returns a list of matching draw calls with event IDs and match reasons.
    """
    params: dict[str, object] = {"shader_name": shader_name}
    if stage is not None:
        params["stage"] = stage
    return bridge.call("find_draws_by_shader", params)


@mcp.tool
def find_draws_by_texture(texture_name: str) -> dict:
    """
    Find all draw calls using a texture with the given name (partial match).

    Args:
        texture_name: Partial name to search for in texture resource names

    Returns a list of matching draw calls with event IDs and match reasons.
    Searches SRVs, UAVs, and render targets.
    """
    return bridge.call("find_draws_by_texture", {"texture_name": texture_name})


@mcp.tool
def find_draws_by_resource(resource_id: str) -> dict:
    """
    Find all draw calls using a specific resource ID (exact match).

    Args:
        resource_id: Resource ID to search for (e.g. "ResourceId::12345" or "12345")

    Returns a list of matching draw calls with event IDs and match reasons.
    Searches shaders, SRVs, UAVs, render targets, and depth targets.
    """
    return bridge.call("find_draws_by_resource", {"resource_id": resource_id})


@mcp.tool
def get_draw_call_details(event_id: int) -> dict:
    """
    Get detailed information about a specific draw call.

    Args:
        event_id: The event ID of the draw call to inspect

    Includes vertex/index counts, resource outputs, and other metadata.
    """
    return bridge.call("get_draw_call_details", {"event_id": event_id})


@mcp.tool
def get_action_timings(
    event_ids: list[int] | None = None,
    marker_filter: str | None = None,
    exclude_markers: list[str] | None = None,
) -> dict:
    """
    Get GPU timing information for actions (draw calls, dispatches, etc.).

    Args:
        event_ids: Optional list of specific event IDs to get timings for.
                   If not specified, returns timings for all actions.
        marker_filter: Only include actions under markers containing this string (partial match).
        exclude_markers: Exclude actions under markers containing these strings.

    Returns timing data including:
    - available: Whether GPU timing counters are supported
    - unit: Time unit (typically "seconds")
    - timings: List of {event_id, name, duration_seconds, duration_ms}
    - total_duration_ms: Sum of all durations
    - count: Number of timing entries

    Note: GPU timing counters may not be available on all hardware/drivers.
    """
    params: dict[str, object] = {}
    if event_ids is not None:
        params["event_ids"] = event_ids
    if marker_filter is not None:
        params["marker_filter"] = marker_filter
    if exclude_markers is not None:
        params["exclude_markers"] = exclude_markers
    return bridge.call("get_action_timings", params)


@mcp.tool
def get_shader_info(
    event_id: int,
    stage: Literal["vertex", "hull", "domain", "geometry", "pixel", "compute"],
) -> dict:
    """
    Get shader information for a specific stage at a given event.

    Args:
        event_id: The event ID to inspect the shader at
        stage: The shader stage (vertex, hull, domain, geometry, pixel, compute)

    Returns shader disassembly, constant buffer values, and resource bindings.
    """
    return bridge.call("get_shader_info", {"event_id": event_id, "stage": stage})


@mcp.tool
def get_buffer_contents(
    resource_id: str,
    offset: int = 0,
    length: int = 0,
) -> dict:
    """
    Read the contents of a buffer resource.

    Args:
        resource_id: The resource ID of the buffer to read
        offset: Byte offset to start reading from (default: 0)
        length: Number of bytes to read, 0 for entire buffer (default: 0)

    Returns buffer data as base64-encoded bytes along with metadata.
    """
    return bridge.call(
        "get_buffer_contents",
        {"resource_id": resource_id, "offset": offset, "length": length},
    )


@mcp.tool
def get_texture_info(resource_id: str) -> dict:
    """
    Get metadata about a texture resource.

    Args:
        resource_id: The resource ID of the texture

    Includes dimensions, format, mip levels, and other properties.
    """
    return bridge.call("get_texture_info", {"resource_id": resource_id})


@mcp.tool
def get_texture_data(
    resource_id: str,
    mip: int = 0,
    slice: int = 0,
    sample: int = 0,
    depth_slice: int | None = None,
) -> dict:
    """
    Read the pixel data of a texture resource.

    Args:
        resource_id: The resource ID of the texture to read
        mip: Mip level to retrieve (default: 0)
        slice: Array slice or cube face index (default: 0)
               For cube maps: 0=X+, 1=X-, 2=Y+, 3=Y-, 4=Z+, 5=Z-
        sample: MSAA sample index (default: 0)
        depth_slice: For 3D textures only, extract a specific depth slice (default: None = full volume)
                     When specified, returns only the 2D slice at that depth index

    Returns texture pixel data as base64-encoded bytes along with metadata
    including dimensions at the requested mip level and format information.
    """
    params = {"resource_id": resource_id, "mip": mip, "slice": slice, "sample": sample}
    if depth_slice is not None:
        params["depth_slice"] = depth_slice
    return bridge.call("get_texture_data", params)


@mcp.tool
def get_pipeline_state(event_id: int) -> dict:
    """
    Get the full graphics pipeline state at a specific event.

    Args:
        event_id: The event ID to get pipeline state at

    Returns detailed pipeline state including:
    - Bound shaders with entry points for each stage
    - Shader resources (SRVs): textures and buffers with dimensions, format, slot, name
    - UAVs (RWTextures/RWBuffers): resource details with dimensions and format
    - Samplers: addressing modes, filter settings, LOD parameters
    - Constant buffers: slot, size, variable count
    - Render targets and depth target
    - Viewports and input assembly state
    """
    return bridge.call("get_pipeline_state", {"event_id": event_id})


@mcp.tool
def list_captures(directory: str) -> dict:
    """
    List all RenderDoc capture files (.rdc) in the specified directory.

    Args:
        directory: The directory path to search for capture files

    Returns a list of capture files with their metadata including:
    - filename: The capture file name
    - path: Full path to the file
    - size_bytes: File size in bytes
    - modified_time: Last modified timestamp (ISO format)
    """
    return bridge.call("list_captures", {"directory": directory})


@mcp.tool
def open_capture(capture_path: str) -> dict:
    """
    Open a RenderDoc capture file (.rdc).

    Args:
        capture_path: Full path to the capture file to open

    Returns success status and information about the opened capture.
    Note: This will close any currently open capture.
    """
    return bridge.call("open_capture", {"capture_path": capture_path})


@mcp.tool
def analyze_shader_performance(
    event_id: int,
    stage: Literal["vertex", "fragment", "pixel", "compute"],
    compiler: Literal["mali", "adreno", "both"] = "both",
    mali_core: str | None = None,
    adreno_arch: str | None = None,
) -> dict:
    """
    Analyze shader performance using mobile GPU offline compilers.

    Compiles the shader from the specified draw call through Mali Offline Compiler
    (malioc) and/or Adreno Offline Compiler (aoc), returning detailed performance
    metrics including instruction counts, cycle counts, register usage, and
    thread/fiber occupancy.

    Only works with OpenGL ES (GLSL) captures. The shader source is extracted
    from the loaded RenderDoc capture via disassembly or embedded debug info.

    Args:
        event_id: The event ID of the draw call to analyze
        stage: Shader stage - "vertex", "fragment" (or "pixel"), "compute"
        compiler: Which compiler to use - "mali", "adreno", or "both" (default)
        mali_core: Mali GPU core target (e.g. "Mali-G78", "Mali-G720").
                   Uses config default if not specified.
        adreno_arch: Adreno architecture target (e.g. "a650", "a740").
                     Uses config default if not specified.

    Returns:
        Performance analysis results from the requested compiler(s), including:
        - Mali: cycle counts per pipeline (arithmetic, load/store, texture, varying),
          work/uniform registers, thread occupancy, FP16 arithmetic %, stack spilling
        - Adreno: instruction counts (ALU 32/16-bit, texture, memory, flow control),
          register footprint (full/half precision), fiber occupancy
    """
    # Normalize stage name: bridge expects "pixel" not "fragment"
    bridge_stage = "pixel" if stage in ("fragment", "pixel") else stage

    source = None
    resource_id = ""
    entry_point = ""
    selected_target = ""
    available_targets = []

    # Try to get shader source from capture, with fallback strategies
    export_error = None

    # Strategy 1: Try export_shader_source (auto-selects best target,
    # also checks reflection.debugInfo.files for embedded GLSL)
    try:
        shader_data = bridge.call("export_shader_source", {"event_id": event_id, "stage": bridge_stage})
        if shader_data and isinstance(shader_data, dict):
            source = shader_data.get("source")
            resource_id = shader_data.get("resource_id", "")
            entry_point = shader_data.get("entry_point", "")
            selected_target = shader_data.get("selected_target", "")
            available_targets = shader_data.get("available_targets", [])
    except Exception as e:
        export_error = str(e)

    # Strategy 2: Fallback to get_shader_info disassembly
    if not source:
        try:
            shader_info = bridge.call("get_shader_info", {"event_id": event_id, "stage": bridge_stage})
            if shader_info and isinstance(shader_info, dict):
                source = shader_info.get("disassembly")
                resource_id = shader_info.get("resource_id", "")
                entry_point = shader_info.get("entry_point", "")
                selected_target = "get_shader_info fallback"
        except Exception as e:
            raise ValueError(
                f"Cannot get shader source for event {event_id} stage '{stage}': {e}"
            )

    # Validate it looks like GLSL (not SPIR-V disassembly)
    if source and (source.strip().startswith("SPIR-V") or source.strip().startswith("; SPIR-V")):
        raise ValueError(
            f"The shader source is SPIR-V disassembly (target: '{selected_target}'), "
            "which cannot be compiled by mobile offline compilers. "
            f"Available targets: {available_targets}. "
            "This tool requires compilable GLSL source code."
        )

    if not source:
        diag = f"export_shader_source error: {export_error}" if export_error else "export_shader_source returned no source"
        raise ValueError(
            f"Cannot get shader source for event {event_id} stage '{stage}'. "
            f"Diagnostics: {diag}. "
            f"Available disassembly targets: {available_targets}. "
            "This tool requires compilable GLSL source code "
            "(typically available in OpenGL ES captures with debug info)."
        )

    # Run offline compiler analysis
    analyzer = _get_analyzer()
    result = analyzer.analyze(
        shader_source=source,
        stage=stage,
        compiler=compiler,
        mali_core=mali_core,
        adreno_arch=adreno_arch,
    )

    # Add context info
    result["event_id"] = event_id
    result["shader_resource_id"] = resource_id
    result["entry_point"] = entry_point
    result["disassembly_target"] = selected_target
    result["available_targets"] = available_targets

    return result


def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
