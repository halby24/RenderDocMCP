"""
Mobile GPU Offline Shader Compiler Integration.

Wraps Mali Offline Compiler (malioc) and Adreno Offline Compiler (aoc)
to provide shader performance analysis for mobile GPUs.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


# Stage name to file extension mapping
_STAGE_EXT_MAP = {
    "vertex": ".vert",
    "fragment": ".frag",
    "pixel": ".frag",
    "compute": ".comp",
    "geometry": ".geom",
    "hull": ".tesc",
    "domain": ".tese",
}

# Stage name to malioc flag mapping
_STAGE_MALIOC_FLAG = {
    "vertex": "--vertex",
    "fragment": "--fragment",
    "pixel": "--fragment",
    "compute": "--compute",
    "geometry": "--geometry",
    "hull": "--tessellation_control",
    "domain": "--tessellation_evaluation",
}


class ShaderCompilerError(Exception):
    """Error during shader compilation/analysis."""
    pass


class MaliCompiler:
    """Wrapper for Mali Offline Compiler (malioc)."""

    def __init__(self, malioc_path: str, default_core: str = "Mali-G78"):
        self.path = malioc_path
        self.default_core = default_core
        self._validate()

    def _validate(self):
        if not os.path.isfile(self.path):
            raise ShaderCompilerError(f"malioc not found at: {self.path}")

    def analyze(
        self,
        shader_source: str,
        stage: str,
        core: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze a GLSL shader using malioc.

        Args:
            shader_source: Complete GLSL source code
            stage: Shader stage (vertex, fragment, pixel, compute, etc.)
            core: Target Mali GPU core (e.g. "Mali-G78"). Uses default if None.

        Returns:
            Structured performance analysis result.
        """
        core = core or self.default_core
        ext = _STAGE_EXT_MAP.get(stage, ".frag")
        stage_flag = _STAGE_MALIOC_FLAG.get(stage, "--fragment")

        tmp_path = None
        try:
            # Write shader to temp file
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="rdmcp_mali_")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(shader_source)

            # Run malioc
            cmd = [
                self.path,
                "--format", "json",
                stage_flag,
                "--opengles",
                "-c", core,
                tmp_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise ShaderCompilerError(f"malioc failed (exit {result.returncode}): {error_msg}")

            # Parse JSON output
            raw = json.loads(result.stdout)
            return self._parse_output(raw, core)

        except json.JSONDecodeError as e:
            raise ShaderCompilerError(f"Failed to parse malioc JSON output: {e}")
        except subprocess.TimeoutExpired:
            raise ShaderCompilerError("malioc timed out after 30 seconds")
        except ShaderCompilerError:
            raise
        except Exception as e:
            raise ShaderCompilerError(f"malioc error: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _parse_output(self, raw: dict, core: str) -> dict[str, Any]:
        """Parse malioc JSON output into a clean structure."""
        result: dict[str, Any] = {
            "compiler": "mali",
            "compiler_version": ".".join(str(v) for v in raw.get("producer", {}).get("version", [])),
            "core": core,
        }

        shaders = raw.get("shaders", [])
        if not shaders:
            raise ShaderCompilerError("No shader analysis results from malioc")

        shader = shaders[0]
        hw = shader.get("hardware", {})
        result["architecture"] = hw.get("architecture", "")
        result["revision"] = hw.get("revision", "")

        shader_meta = shader.get("shader", {})
        result["api"] = shader_meta.get("api", "")
        result["shader_type"] = shader_meta.get("type", "")

        # Parse variants
        variants = []
        for variant in shader.get("variants", []):
            v_result: dict[str, Any] = {"name": variant.get("name", "")}

            # Performance cycles
            perf = variant.get("performance", {})
            total = perf.get("total_cycles", {})
            pipelines = perf.get("pipelines", [])
            cycles = total.get("cycle_count", [])
            bound = total.get("bound_pipelines", [])

            cycle_detail = {}
            for i, pipe_name in enumerate(pipelines):
                if i < len(cycles):
                    cycle_detail[pipe_name] = cycles[i]
            v_result["cycles"] = cycle_detail
            v_result["bound_pipelines"] = bound

            # Shortest / longest path
            shortest = perf.get("shortest_path_cycles", {})
            longest = perf.get("longest_path_cycles", {})
            if shortest.get("cycle_count"):
                s_cycles = {}
                for i, pipe_name in enumerate(pipelines):
                    if i < len(shortest["cycle_count"]):
                        s_cycles[pipe_name] = shortest["cycle_count"][i]
                v_result["shortest_path_cycles"] = s_cycles
            if longest.get("cycle_count"):
                l_cycles = {}
                for i, pipe_name in enumerate(pipelines):
                    if i < len(longest["cycle_count"]):
                        l_cycles[pipe_name] = longest["cycle_count"][i]
                v_result["longest_path_cycles"] = l_cycles

            # Properties
            props = {}
            for prop in variant.get("properties", []):
                props[prop["name"]] = prop.get("value")
            v_result["work_registers"] = props.get("work_registers_used")
            v_result["uniform_registers"] = props.get("uniform_registers_used")
            v_result["thread_occupancy"] = props.get("thread_occupancy")
            v_result["has_stack_spilling"] = props.get("has_stack_spilling", False)
            v_result["stack_spill_bytes"] = props.get("stack_spill_bytes", 0)
            v_result["fp16_arithmetic_pct"] = props.get("fp16_arithmetic")

            variants.append(v_result)

        result["variants"] = variants

        # Shader-level properties
        shader_props = {}
        for prop in shader.get("properties", []):
            shader_props[prop["name"]] = prop.get("value")
        result["has_uniform_computation"] = shader_props.get("has_uniform_computation", False)
        result["has_side_effects"] = shader_props.get("has_side_effects", False)
        result["modifies_coverage"] = shader_props.get("modifies_coverage", False)
        result["uses_late_zs_test"] = shader_props.get("uses_late_zs_test", False)
        result["uses_late_zs_update"] = shader_props.get("uses_late_zs_update", False)

        # Warnings
        warnings = shader.get("warnings", [])
        if warnings:
            result["warnings"] = warnings

        return result


class AdrenoCompiler:
    """Wrapper for Adreno Offline Compiler (aoc)."""

    def __init__(self, aoc_path: str, default_arch: str = "a650"):
        self.path = aoc_path
        self.default_arch = default_arch
        self._validate()

    def _validate(self):
        if not os.path.isfile(self.path):
            raise ShaderCompilerError(f"aoc not found at: {self.path}")

    def analyze(
        self,
        shader_source: str,
        stage: str,
        arch: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze a GLSL shader using aoc.

        Args:
            shader_source: Complete GLSL source code
            stage: Shader stage (vertex, fragment, pixel, compute, etc.)
            arch: Target Adreno architecture (e.g. "a650"). Uses default if None.

        Returns:
            Structured performance analysis result.
        """
        arch = arch or self.default_arch
        ext = _STAGE_EXT_MAP.get(stage, ".frag")

        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="rdmcp_aoc_")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(shader_source)

            cmd = [
                self.path,
                f"-arch={arch}",
                tmp_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise ShaderCompilerError(f"aoc failed (exit {result.returncode}): {error_msg}")

            # Check for compilation failure in stdout
            if "Compilation failed" in result.stdout:
                raise ShaderCompilerError(f"aoc compilation failed: {result.stdout.strip()}")

            return self._parse_output(result.stdout, arch, stage)

        except subprocess.TimeoutExpired:
            raise ShaderCompilerError("aoc timed out after 30 seconds")
        except ShaderCompilerError:
            raise
        except Exception as e:
            raise ShaderCompilerError(f"aoc error: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _parse_output(self, stdout: str, arch: str, stage: str) -> dict[str, Any]:
        """Parse aoc text output into a structured result."""
        # Extract version info
        version_match = re.search(r"AOC Version\s*:\s*([\d.]+)", stdout)
        compiler_ver_match = re.search(r"Compiler Version\s*:\s*(\S+)", stdout)

        result: dict[str, Any] = {
            "compiler": "adreno",
            "compiler_version": version_match.group(1) if version_match else "",
            "internal_compiler_version": compiler_ver_match.group(1) if compiler_ver_match else "",
            "arch": arch,
        }

        # Parse shader stats sections
        # AOC outputs one or more sections like "============ Shader Stats FS ============"
        section_pattern = r"={3,}\s*Shader Stats\s+(.+?)\s*={3,}(.*?)(?=={3,}\s*Shader Stats|Compilation succeeded|$)"
        sections = re.findall(section_pattern, stdout, re.DOTALL)

        shader_sections = []
        for section_name, section_body in sections:
            stats = self._parse_stats_section(section_body.strip())
            stats["section"] = section_name.strip()
            shader_sections.append(stats)

        if shader_sections:
            # Primary section is the first one (e.g. "FS", "VS")
            result["stats"] = shader_sections[0]
            if len(shader_sections) > 1:
                result["additional_sections"] = shader_sections[1:]

        return result

    def _parse_stats_section(self, body: str) -> dict[str, Any]:
        """Parse a single stats section from aoc output."""
        stats: dict[str, Any] = {}
        # Each line: "Key description    :   value"
        line_pattern = re.compile(r"^(.+?)\s*:\s*(\d+(?:\.\d+)?)\s*$", re.MULTILINE)
        for match in line_pattern.finditer(body):
            key = match.group(1).strip()
            value_str = match.group(2)
            # Convert to int or float
            value: int | float = int(value_str) if "." not in value_str else float(value_str)
            # Normalize key name
            norm_key = self._normalize_key(key)
            stats[norm_key] = value

        return stats

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Normalize an aoc stat key to snake_case."""
        key = key.strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", key)
        key = key.strip("_")
        return key


class ShaderPerformanceAnalyzer:
    """
    High-level analyzer that orchestrates Mali and Adreno offline compilers.
    """

    def __init__(
        self,
        malioc_path: str | None = None,
        aoc_path: str | None = None,
        mali_default_core: str = "Mali-G78",
        adreno_default_arch: str = "a650",
    ):
        self._mali: MaliCompiler | None = None
        self._adreno: AdrenoCompiler | None = None

        if malioc_path and os.path.isfile(malioc_path):
            self._mali = MaliCompiler(malioc_path, mali_default_core)

        if aoc_path and os.path.isfile(aoc_path):
            self._adreno = AdrenoCompiler(aoc_path, adreno_default_arch)

    @property
    def mali_available(self) -> bool:
        return self._mali is not None

    @property
    def adreno_available(self) -> bool:
        return self._adreno is not None

    def analyze(
        self,
        shader_source: str,
        stage: str,
        compiler: str = "both",
        mali_core: str | None = None,
        adreno_arch: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze shader performance using mobile offline compilers.

        Args:
            shader_source: Complete GLSL source code
            stage: Shader stage name
            compiler: "mali", "adreno", or "both"
            mali_core: Override Mali GPU core target
            adreno_arch: Override Adreno architecture target

        Returns:
            Combined analysis results from requested compilers.
        """
        result: dict[str, Any] = {"stage": stage}
        errors: list[str] = []

        run_mali = compiler in ("mali", "both")
        run_adreno = compiler in ("adreno", "both")

        if run_mali:
            if self._mali:
                try:
                    result["mali"] = self._mali.analyze(shader_source, stage, mali_core)
                except ShaderCompilerError as e:
                    errors.append(f"Mali: {e}")
                    result["mali"] = {"error": str(e)}
            else:
                errors.append("Mali offline compiler (malioc) not available")
                result["mali"] = {"error": "malioc not found"}

        if run_adreno:
            if self._adreno:
                try:
                    result["adreno"] = self._adreno.analyze(shader_source, stage, adreno_arch)
                except ShaderCompilerError as e:
                    errors.append(f"Adreno: {e}")
                    result["adreno"] = {"error": str(e)}
            else:
                errors.append("Adreno offline compiler (aoc) not available")
                result["adreno"] = {"error": "aoc not found"}

        if errors:
            result["errors"] = errors

        return result
