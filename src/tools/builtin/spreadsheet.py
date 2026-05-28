from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


class SpreadsheetTool(ITool):
    """Excel/CSV spreadsheet read and write tool.

    Supports reading from and writing to CSV files (via csv module)
    and Excel files (via openpyxl, if available). Write operations
    targeting paths outside the project root are treated as dangerous.
    """

    def __init__(self) -> None:
        self._project_root = Path.cwd().resolve()
        self._spec = ToolSpec(
            name="spreadsheet",
            description=(
                "Read and write spreadsheet files (CSV and Excel .xlsx). "
                "Supports reading rows as a list of dicts and writing "
                "a list of dicts to file."
            ),
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action to perform: read or write",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type="string",
                    description="File path to the spreadsheet",
                    required=True,
                ),
                ToolParameter(
                    name="sheet_name",
                    type="string",
                    description="Sheet name for Excel files",
                    required=False,
                    default="Sheet1",
                ),
                ToolParameter(
                    name="data",
                    type="array",
                    description=(
                        "List of dicts representing rows. Required for write action. "
                        "Each dict key maps to a column header."
                    ),
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="headers",
                    type="boolean",
                    description=(
                        "If True, first row is treated as column headers "
                        "on read, or written as a header row on write"
                    ),
                    required=False,
                    default=True,
                ),
                ToolParameter(
                    name="encoding",
                    type="string",
                    description="File encoding for CSV files",
                    required=False,
                    default="utf-8",
                ),
            ],
        )

    def get_spec(self) -> ToolSpec:
        """Return the tool specification.

        Returns:
            ToolSpec instance describing this tool's interface.
        """

        return self._spec

    async def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters before execution.

        Args:
            params: Dictionary of tool parameters.

        Returns:
            List of validation error messages. Empty list means valid.
        """

        errors: list[str] = []
        action = params.get("action", "")
        if action not in ("read", "write"):
            errors.append(
                f"Invalid action: {action}. Must be 'read' or 'write'."
            )

        path_str = params.get("path", "")
        if not path_str:
            errors.append("path is required and must not be empty")
        else:
            ext = Path(path_str).suffix.lower()
            if ext not in (".csv", ".xlsx"):
                errors.append(
                    f"Unsupported file extension: {ext}. "
                    "Only .csv and .xlsx are supported."
                )

        if action == "write":
            data = params.get("data")
            if not data:
                errors.append(
                    "data parameter is required and must not be empty for write action"
                )
            elif not isinstance(data, list):
                errors.append("data parameter must be a list of dicts")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        """Execute the requested spreadsheet operation.

        Args:
            params: Dictionary of tool parameters.
            user_id: Identifier of the user making the request.

        Returns:
            ToolResult with operation outcome.
        """

        action = params.get("action", "")
        path_str = params.get("path", "")
        sheet_name = params.get("sheet_name", "Sheet1")
        headers = params.get("headers", True)
        encoding = params.get("encoding", "utf-8")

        resolved = self._resolve_path(path_str)

        if action == "read":
            return await self._read(resolved, sheet_name, headers, encoding)
        elif action == "write":
            data = params.get("data", [])
            if self._is_dangerous(resolved):
                return ToolResult(
                    success=False,
                    error=(
                        f"Write to '{resolved}' is dangerous because the path "
                        f"is outside the project root '{self._project_root}'. "
                        "Please use a path within the project directory."
                    ),
                )
            return await self._write(resolved, data, sheet_name, headers, encoding)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path string to an absolute Path.

        Relative paths are resolved against the project root directory.
        Absolute paths are used as-is after resolution.

        Args:
            path_str: File path string.

        Returns:
            Resolved absolute Path object.
        """

        p = Path(path_str)
        if p.is_absolute():
            return p.resolve()
        return (self._project_root / p).resolve()

    def _is_dangerous(self, path: Path) -> bool:
        """Determine if a write operation targets a path outside the project root.

        Args:
            path: The resolved absolute Path.

        Returns:
            True if the path is outside the project root.
        """

        try:
            path.relative_to(self._project_root)
            return False
        except ValueError:
            return True

    async def _read(
        self,
        path: Path,
        sheet_name: str,
        headers: bool,
        encoding: str,
    ) -> ToolResult:
        """Read a spreadsheet file and return rows as a list of dicts.

        Supports CSV files via the csv module and Excel .xlsx files
        via openpyxl (if available). Falls back gracefully if openpyxl
        is not installed.

        Args:
            path: Absolute path to the spreadsheet file.
            sheet_name: Sheet name for Excel files.
            headers: If True, use first row as dict keys.
            encoding: File encoding for CSV files.

        Returns:
            ToolResult with list of dicts in data.
        """

        if not path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: {path}",
            )
        if not path.is_file():
            return ToolResult(
                success=False,
                error=f"Path is not a file: {path}",
            )

        ext = path.suffix.lower()
        try:
            if ext == ".csv":
                return await self._read_csv(path, headers, encoding)
            elif ext == ".xlsx":
                return await self._read_xlsx(path, sheet_name, headers)
            else:
                return ToolResult(
                    success=False,
                    error=f"Unsupported file format: {ext}",
                )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to read spreadsheet: {e}",
            )

    async def _read_csv(
        self,
        path: Path,
        headers: bool,
        encoding: str,
    ) -> ToolResult:
        """Read a CSV file and return rows as a list of dicts.

        Args:
            path: Absolute path to the CSV file.
            headers: If True, use first row as dict keys.
            encoding: File encoding.

        Returns:
            ToolResult with list of dicts in data.
        """

        import asyncio

        def _read() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            with open(str(path), mode="r", encoding=encoding, newline="") as f:
                if headers:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(dict(row))
                else:
                    reader = csv.reader(f)
                    for row in reader:
                        rows.append(
                            {str(i): val for i, val in enumerate(row)}
                        )
            return rows

        data = await asyncio.to_thread(_read)
        return ToolResult(
            success=True,
            data={
                "rows": data,
                "count": len(data),
                "file": str(path),
            },
        )

    async def _read_xlsx(
        self,
        path: Path,
        sheet_name: str,
        headers: bool,
    ) -> ToolResult:
        """Read an Excel .xlsx file and return rows as a list of dicts.

        Args:
            path: Absolute path to the Excel file.
            sheet_name: Sheet name to read from.
            headers: If True, use first row as dict keys.

        Returns:
            ToolResult with list of dicts in data.

        Raises:
            ImportError: If openpyxl is not installed.
        """

        if not HAS_OPENPYXL:
            return ToolResult(
                success=False,
                error=(
                    "openpyxl is required to read .xlsx files. "
                    "Install it with: pip install openpyxl"
                ),
            )

        import asyncio

        def _read() -> list[dict[str, Any]]:
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            if sheet_name not in wb.sheetnames:
                available = ", ".join(wb.sheetnames)
                wb.close()
                raise ValueError(
                    f"Sheet '{sheet_name}' not found. Available sheets: {available}"
                )
            ws = wb[sheet_name]
            rows: list[dict[str, Any]] = []
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                wb.close()
                return rows
            if headers:
                header_row = [str(c) if c is not None else "" for c in all_rows[0]]
                for row_values in all_rows[1:]:
                    row_dict: dict[str, Any] = {}
                    for idx, val in enumerate(row_values):
                        key = header_row[idx] if idx < len(header_row) else f"col_{idx}"
                        row_dict[key] = val
                    rows.append(row_dict)
            else:
                for row_values in all_rows:
                    rows.append(
                        {str(i): val for i, val in enumerate(row_values)}
                    )
            wb.close()
            return rows

        data = await asyncio.to_thread(_read)
        return ToolResult(
            success=True,
            data={
                "rows": data,
                "count": len(data),
                "file": str(path),
                "sheet": sheet_name,
            },
        )

    async def _write(
        self,
        path: Path,
        data: list[dict[str, Any]],
        sheet_name: str,
        headers: bool,
        encoding: str,
    ) -> ToolResult:
        """Write a list of dicts to a spreadsheet file.

        Creates parent directories if they do not exist. The output
        format is determined by the file extension (.csv or .xlsx).

        Args:
            path: Absolute path to the output file.
            data: List of dicts representing rows.
            sheet_name: Sheet name for Excel files.
            headers: If True, write a header row.
            encoding: File encoding for CSV files.

        Returns:
            ToolResult with write status.
        """

        import asyncio

        ext = path.suffix.lower()
        try:
            parent = path.parent
            if not parent.exists():
                await asyncio.to_thread(parent.mkdir, parents=True, exist_ok=True)

            if ext == ".csv":
                result = await self._write_csv(path, data, headers, encoding)
            elif ext == ".xlsx":
                result = await self._write_xlsx(path, data, sheet_name, headers)
            else:
                return ToolResult(
                    success=False,
                    error=f"Unsupported file format: {ext}",
                )
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to write spreadsheet: {e}",
            )

    async def _write_csv(
        self,
        path: Path,
        data: list[dict[str, Any]],
        headers: bool,
        encoding: str,
    ) -> ToolResult:
        """Write data to a CSV file.

        Args:
            path: Absolute path to the output CSV file.
            data: List of dicts representing rows.
            headers: If True, write a header row.
            encoding: File encoding.

        Returns:
            ToolResult with write status.
        """

        import asyncio

        def _write() -> int:
            fieldnames: list[str] = []
            if data:
                fieldnames = list(data[0].keys())
            with open(str(path), mode="w", encoding=encoding, newline="") as f:
                if headers:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in data:
                        writer.writerow(row)
                else:
                    writer = csv.writer(f)
                    for row in data:
                        writer.writerow(list(row.values()))
            return len(data)

        count = await asyncio.to_thread(_write)
        return ToolResult(
            success=True,
            data={
                "file": str(path),
                "rows_written": count,
                "format": "csv",
            },
        )

    async def _write_xlsx(
        self,
        path: Path,
        data: list[dict[str, Any]],
        sheet_name: str,
        headers: bool,
    ) -> ToolResult:
        """Write data to an Excel .xlsx file.

        Args:
            path: Absolute path to the output Excel file.
            data: List of dicts representing rows.
            sheet_name: Sheet name.
            headers: If True, write a header row.

        Returns:
            ToolResult with write status.

        Raises:
            ImportError: If openpyxl is not installed.
        """

        if not HAS_OPENPYXL:
            return ToolResult(
                success=False,
                error=(
                    "openpyxl is required to write .xlsx files. "
                    "Install it with: pip install openpyxl"
                ),
            )

        import asyncio

        def _write() -> int:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_name
            if not data:
                wb.save(str(path))
                wb.close()
                return 0
            fieldnames = list(data[0].keys())
            if headers:
                ws.append(fieldnames)
            for row in data:
                ws.append([row.get(k, "") for k in fieldnames])
            wb.save(str(path))
            wb.close()
            return len(data)

        count = await asyncio.to_thread(_write)
        return ToolResult(
            success=True,
            data={
                "file": str(path),
                "rows_written": count,
                "sheet": sheet_name,
                "format": "xlsx",
            },
        )
