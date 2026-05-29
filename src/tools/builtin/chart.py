from __future__ import annotations

import base64
import io
import time
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False


class ChartTool(ITool):
    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="chart",
            description="Chart generation tool supporting bar, line, pie, scatter, "
            "and Mermaid.js diagrams.",
            category="extension",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Chart type: bar / line / pie / scatter / mermaid",
                    required=True,
                ),
                ToolParameter(
                    name="data",
                    type="array",
                    description="List of data dictionaries for the chart",
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Chart title",
                    required=False,
                    default="Chart",
                ),
                ToolParameter(
                    name="x_field",
                    type="string",
                    description="Field name for x-axis values",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="y_field",
                    type="string",
                    description="Field name for y-axis values",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="output_format",
                    type="string",
                    description="Output format: base64 / text",
                    required=False,
                    default="base64",
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Operation timeout in seconds",
                    required=False,
                    default=30,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        action: str = params.get("action", "")
        valid_actions = {"bar", "line", "pie", "scatter", "mermaid"}
        if action not in valid_actions:
            errors.append(f"action must be one of: {', '.join(sorted(valid_actions))}")
            return errors
        data = params.get("data")
        if not data or not isinstance(data, list) or len(data) == 0:
            errors.append("data parameter must be a non-empty list of dictionaries")
            return errors
        if action in ("bar", "line", "scatter"):
            if not params.get("x_field"):
                errors.append(f"{action} chart requires x_field parameter")
            if not params.get("y_field"):
                errors.append(f"{action} chart requires y_field parameter")
        if action == "pie":
            if not params.get("x_field"):
                errors.append("pie chart requires x_field parameter (labels)")
            if not params.get("y_field"):
                errors.append("pie chart requires y_field parameter (values)")
        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        action: str = params["action"]
        start = time.time()

        if action == "mermaid":
            return await self._generate_mermaid(
                params["data"],
                params.get("title", "Chart"),
                start,
            )

        if not _HAS_MATPLOTLIB:
            return ToolResult(
                success=False,
                error="matplotlib is not installed. Install it with: pip install matplotlib",
                duration_ms=(time.time() - start) * 1000,
            )

        if action == "bar":
            return await self._generate_bar(params, start)
        elif action == "line":
            return await self._generate_line(params, start)
        elif action == "pie":
            return await self._generate_pie(params, start)
        else:
            return await self._generate_scatter(params, start)

    async def _generate_bar(
        self,
        params: dict[str, Any],
        start: float,
    ) -> ToolResult:
        try:
            data: list[dict[str, Any]] = params["data"]
            x_field: str = params["x_field"]
            y_field: str = params["y_field"]
            title: str = params.get("title", "Chart")

            labels = [str(d[x_field]) for d in data]
            values = [float(d[y_field]) for d in data]

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.bar(labels, values)
            ax.set_title(title)
            ax.set_xlabel(x_field)
            ax.set_ylabel(y_field)
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            img_base64 = self._fig_to_base64(fig)
            plt.close(fig)

            return ToolResult(
                success=True,
                data={"image": img_base64, "format": "base64", "type": "bar"},
                duration_ms=(time.time() - start) * 1000,
            )
        except (KeyError, ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Failed to generate bar chart: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _generate_line(
        self,
        params: dict[str, Any],
        start: float,
    ) -> ToolResult:
        try:
            data: list[dict[str, Any]] = params["data"]
            x_field: str = params["x_field"]
            y_field: str = params["y_field"]
            title: str = params.get("title", "Chart")

            labels = [str(d[x_field]) for d in data]
            values = [float(d[y_field]) for d in data]

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(labels, values, marker="o", linestyle="-")
            ax.set_title(title)
            ax.set_xlabel(x_field)
            ax.set_ylabel(y_field)
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            img_base64 = self._fig_to_base64(fig)
            plt.close(fig)

            return ToolResult(
                success=True,
                data={"image": img_base64, "format": "base64", "type": "line"},
                duration_ms=(time.time() - start) * 1000,
            )
        except (KeyError, ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Failed to generate line chart: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _generate_pie(
        self,
        params: dict[str, Any],
        start: float,
    ) -> ToolResult:
        try:
            data: list[dict[str, Any]] = params["data"]
            x_field: str = params["x_field"]
            y_field: str = params["y_field"]
            title: str = params.get("title", "Chart")

            labels = [str(d[x_field]) for d in data]
            values = [float(d[y_field]) for d in data]

            fig, ax = plt.subplots(figsize=(8, 8))
            ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.set_title(title)
            ax.axis("equal")
            plt.tight_layout()

            img_base64 = self._fig_to_base64(fig)
            plt.close(fig)

            return ToolResult(
                success=True,
                data={"image": img_base64, "format": "base64", "type": "pie"},
                duration_ms=(time.time() - start) * 1000,
            )
        except (KeyError, ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Failed to generate pie chart: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _generate_scatter(
        self,
        params: dict[str, Any],
        start: float,
    ) -> ToolResult:
        try:
            data: list[dict[str, Any]] = params["data"]
            x_field: str = params["x_field"]
            y_field: str = params["y_field"]
            title: str = params.get("title", "Chart")

            x_vals = [float(d[x_field]) for d in data]
            y_vals = [float(d[y_field]) for d in data]

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.scatter(x_vals, y_vals, alpha=0.6)
            ax.set_title(title)
            ax.set_xlabel(x_field)
            ax.set_ylabel(y_field)
            plt.tight_layout()

            img_base64 = self._fig_to_base64(fig)
            plt.close(fig)

            return ToolResult(
                success=True,
                data={"image": img_base64, "format": "base64", "type": "scatter"},
                duration_ms=(time.time() - start) * 1000,
            )
        except (KeyError, ValueError, TypeError) as e:
            return ToolResult(
                success=False,
                error=f"Failed to generate scatter plot: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    async def _generate_mermaid(
        self,
        data: list[dict[str, Any]],
        title: str,
        start: float,
    ) -> ToolResult:
        try:
            mermaid_lines: list[str] = []
            chart_type_str: str = data[0].get("type", "flowchart") if data else "flowchart"

            if chart_type_str == "flowchart" or chart_type_str == "graph":
                mermaid_lines.append("graph TD")
                for item in data:
                    if "from" in item and "to" in item:
                        label = item.get("label", "")
                        if label:
                            mermaid_lines.append(f"    {item['from']} -->|{label}| {item['to']}")
                        else:
                            mermaid_lines.append(f"    {item['from']} --> {item['to']}")
            elif chart_type_str == "sequence":
                mermaid_lines.append("sequenceDiagram")
                for item in data:
                    participant = item.get("participant", "")
                    if participant:
                        mermaid_lines.append(f"    participant {participant}")
                for item in data:
                    if "from" in item and "to" in item and "message" in item:
                        mermaid_lines.append(
                            f"    {item['from']}->>{item['to']}: {item['message']}"
                        )
            elif chart_type_str == "gantt":
                mermaid_lines.append("gantt")
                mermaid_lines.append(f"    title {title}")
                mermaid_lines.append("    dateFormat  YYYY-MM-DD")
                for item in data:
                    if "task" in item and "start" in item and "end" in item:
                        mermaid_lines.append(f"    section {item.get('section', 'Default')}")
                        mermaid_lines.append(f"    {item['task']} : {item['start']}, {item['end']}")
            else:
                mermaid_lines.append("graph TD")
                mermaid_lines.append(f"    A[{chart_type_str}]")

            mermaid_code = "\n".join(mermaid_lines)
            return ToolResult(
                success=True,
                data={
                    "code": mermaid_code,
                    "format": "text",
                    "type": "mermaid",
                    "title": title,
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except (KeyError, IndexError) as e:
            return ToolResult(
                success=False,
                error=f"Failed to generate Mermaid diagram: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    @staticmethod
    def _fig_to_base64(fig: Any) -> str:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        buf.close()
        return img_base64
