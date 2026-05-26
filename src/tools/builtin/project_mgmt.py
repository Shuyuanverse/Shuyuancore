from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

from src.security.approval import get_approval_manager
from src.security.audit import get_audit_logger
from src.tools.interfaces import ITool, ToolParameter, ToolResult, ToolSpec


class ProjectMgmtTool(ITool):

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="project_mgmt",
            description="Project management tool for GitHub Issues and "
            "Jira. Supports listing, creating, updating, and closing issues.",
            category="office",
            dangerous=False,
            parameters=[
                ToolParameter(
                    name="provider",
                    type="string",
                    description="Provider: github or jira",
                    required=True,
                ),
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: list_issues / create_issue / "
                    "update_issue / close_issue",
                    required=True,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Issue title, required for create_issue",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="Issue body / description",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="issue_id",
                    type="string",
                    description="Issue number or ID, required for "
                    "update_issue and close_issue",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="assignee",
                    type="string",
                    description="Issue assignee username",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="labels",
                    type="array",
                    description="List of labels",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="repo",
                    type="string",
                    description="GitHub repository (owner/repo)",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="project",
                    type="string",
                    description="Jira project key",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="HTTP request timeout in seconds",
                    required=False,
                    default=30,
                ),
            ],
        )

    async def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        provider: str = params.get("provider", "")
        action: str = params.get("action", "")

        valid_providers = {"github", "jira"}
        if provider not in valid_providers:
            errors.append(
                f"provider must be one of: {', '.join(sorted(valid_providers))}"
            )

        valid_actions = {
            "list_issues", "create_issue", "update_issue", "close_issue",
        }
        if action not in valid_actions:
            errors.append(
                f"action must be one of: {', '.join(sorted(valid_actions))}"
            )

        if errors:
            return errors

        if action in ("create_issue",) and not params.get("title"):
            errors.append(f"{action} requires title parameter")

        if action in ("update_issue", "close_issue") and not params.get("issue_id"):
            errors.append(f"{action} requires issue_id parameter")

        if provider == "github" and action != "list_issues" and not params.get("repo"):
            errors.append(f"github {action} requires repo parameter (owner/repo)")

        if provider == "jira" and not params.get("project"):
            errors.append(f"jira {action} requires project parameter")

        return errors

    async def execute(
        self,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> ToolResult:
        provider: str = params["provider"]
        action: str = params["action"]
        start = time.time()

        is_dangerous = action != "list_issues"
        if is_dangerous:
            approval_mgr = get_approval_manager()
            req = await approval_mgr.request(
                tool_name="project_mgmt",
                params=params,
                user_id=user_id,
                timeout=300,
            )
            approved = await approval_mgr.wait(req.approval_id, timeout=300)
            if not approved:
                audit = get_audit_logger()
                audit.log(
                    user_id=user_id,
                    action=f"project_mgmt.{action}",
                    resource=provider,
                    params={"action": action},
                    result="rejected",
                    duration_ms=(time.time() - start) * 1000,
                )
                return ToolResult(
                    success=False,
                    error=f"{action} was not approved",
                    duration_ms=(time.time() - start) * 1000,
                    approval_id=req.approval_id,
                )

        if provider == "github":
            return await self._execute_github(params, user_id, start)
        else:
            return await self._execute_jira(params, user_id, start)

    async def _execute_github(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
    ) -> ToolResult:
        action: str = params["action"]
        repo: str = params.get("repo", "")
        timeout: int = params.get("timeout", 30)
        token = os.environ.get("GITHUB_TOKEN", "")
        audit = get_audit_logger()

        if not token:
            return ToolResult(
                success=False,
                error="GITHUB_TOKEN environment variable not set",
                duration_ms=(time.time() - start) * 1000,
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            import httpx

            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "list_issues":
                    url = f"https://api.github.com/repos/{repo}/issues"
                    params_dict: dict[str, str] = {"state": "open"}
                    response = await client.get(url, headers=headers, params=params_dict)
                    response.raise_for_status()
                    issues = response.json()

                    result_data = [
                        {
                            "number": issue["number"],
                            "title": issue["title"],
                            "state": issue["state"],
                            "user": issue["user"]["login"] if issue.get("user") else None,
                            "labels": [lb["name"] for lb in issue.get("labels", [])],
                            "created_at": issue["created_at"],
                            "html_url": issue["html_url"],
                        }
                        for issue in issues
                    ]

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.github.list_issues",
                        resource=repo,
                        params={},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={"issues": result_data, "count": len(result_data)},
                        duration_ms=duration_ms,
                    )

                elif action == "create_issue":
                    url = f"https://api.github.com/repos/{repo}/issues"
                    payload: dict[str, Any] = {
                        "title": params["title"],
                    }
                    body = params.get("body")
                    if body:
                        payload["body"] = body
                    assignee = params.get("assignee")
                    if assignee:
                        payload["assignee"] = assignee
                    labels = params.get("labels")
                    if labels:
                        payload["labels"] = labels

                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    issue = response.json()

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.github.create_issue",
                        resource=repo,
                        params={"title": params["title"]},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={
                            "number": issue["number"],
                            "title": issue["title"],
                            "html_url": issue["html_url"],
                        },
                        duration_ms=duration_ms,
                    )

                elif action == "update_issue":
                    url = f"https://api.github.com/repos/{repo}/issues/{params['issue_id']}"
                    payload = {}
                    title = params.get("title")
                    if title:
                        payload["title"] = title
                    body = params.get("body")
                    if body:
                        payload["body"] = body
                    assignee = params.get("assignee")
                    if assignee:
                        payload["assignee"] = assignee
                    labels = params.get("labels")
                    if labels:
                        payload["labels"] = labels

                    response = await client.patch(url, headers=headers, json=payload)
                    response.raise_for_status()
                    issue = response.json()

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.github.update_issue",
                        resource=repo,
                        params={"issue_id": params["issue_id"]},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={
                            "number": issue["number"],
                            "title": issue["title"],
                            "state": issue["state"],
                        },
                        duration_ms=duration_ms,
                    )

                else:
                    url = f"https://api.github.com/repos/{repo}/issues/{params['issue_id']}"
                    payload = {"state": "closed"}
                    response = await client.patch(url, headers=headers, json=payload)
                    response.raise_for_status()
                    issue = response.json()

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.github.close_issue",
                        resource=repo,
                        params={"issue_id": params["issue_id"]},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={
                            "number": issue["number"],
                            "title": issue["title"],
                            "state": issue["state"],
                        },
                        duration_ms=duration_ms,
                    )

        except ImportError:
            fallback = await self._github_via_cli(
                params, user_id, start, token,
            )
            return fallback
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action=f"project_mgmt.github.{action}",
                resource=repo,
                params={"action": action},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"GitHub API error: {e.response.status_code} {e.response.text}",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action=f"project_mgmt.github.{action}",
                resource=repo,
                params={"action": action},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def _github_via_cli(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
        token: str,
    ) -> ToolResult:
        action: str = params["action"]
        repo: str = params.get("repo", "")
        audit = get_audit_logger()

        env = os.environ.copy()
        env["GH_TOKEN"] = token

        try:
            if action == "list_issues":
                cmd = ["gh", "issue", "list", "--repo", repo,
                       "--state", "open", "--json", "number,title,state,labels,createdAt,url"]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                )
                if result.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=result.stderr,
                        duration_ms=(time.time() - start) * 1000,
                    )
                issues = json.loads(result.stdout)

                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="project_mgmt.github.list_issues",
                    resource=repo,
                    params={},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={
                        "issues": [
                            {
                                "number": i["number"],
                                "title": i["title"],
                                "state": i["state"],
                                "labels": [lb["name"] for lb in i.get("labels", [])],
                                "created_at": i.get("createdAt"),
                                "html_url": i.get("url"),
                            }
                            for i in issues
                        ],
                        "count": len(issues),
                    },
                    duration_ms=duration_ms,
                )

            elif action == "create_issue":
                cmd = ["gh", "issue", "create", "--repo", repo,
                       "--title", params["title"]]
                body = params.get("body")
                if body:
                    cmd.extend(["--body", body])
                assignee = params.get("assignee")
                if assignee:
                    cmd.extend(["--assignee", assignee])
                labels = params.get("labels")
                if labels:
                    for label in labels:
                        cmd.extend(["--label", label])

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                )
                if result.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=result.stderr,
                        duration_ms=(time.time() - start) * 1000,
                    )

                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="project_mgmt.github.create_issue",
                    resource=repo,
                    params={"title": params["title"]},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={"url": result.stdout.strip()},
                    duration_ms=duration_ms,
                )

            elif action == "close_issue":
                issue_id: str = params["issue_id"]
                cmd = ["gh", "issue", "close", issue_id, "--repo", repo]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                )
                if result.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=result.stderr,
                        duration_ms=(time.time() - start) * 1000,
                    )

                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="project_mgmt.github.close_issue",
                    resource=repo,
                    params={"issue_id": issue_id},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={"closed": issue_id},
                    duration_ms=duration_ms,
                )

            else:
                issue_id = params["issue_id"]
                cmd = ["gh", "issue", "edit", issue_id, "--repo", repo]
                title = params.get("title")
                if title:
                    cmd.extend(["--title", title])
                body = params.get("body")
                if body:
                    cmd.extend(["--body", body])
                labels = params.get("labels")
                if labels:
                    cmd.extend(["--add-label", ",".join(labels)])

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60, env=env,
                )
                if result.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=result.stderr,
                        duration_ms=(time.time() - start) * 1000,
                    )

                duration_ms = (time.time() - start) * 1000
                audit.log(
                    user_id=user_id,
                    action="project_mgmt.github.update_issue",
                    resource=repo,
                    params={"issue_id": issue_id},
                    result="success",
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    success=True,
                    data={"updated": issue_id},
                    duration_ms=duration_ms,
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error="GitHub CLI command timed out",
                duration_ms=(time.time() - start) * 1000,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                error="gh CLI not found and httpx not available. "
                "Install gh CLI or httpx.",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _execute_jira(
        self,
        params: dict[str, Any],
        user_id: str,
        start: float,
    ) -> ToolResult:
        action: str = params["action"]
        project: str = params["project"]
        timeout: int = params.get("timeout", 30)
        audit = get_audit_logger()

        jira_url = os.environ.get("JIRA_URL", "")
        jira_email = os.environ.get("JIRA_EMAIL", "")
        jira_token = os.environ.get("JIRA_API_TOKEN", "")

        if not all([jira_url, jira_email, jira_token]):
            return ToolResult(
                success=False,
                error="JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN "
                "environment variables must be set",
                duration_ms=(time.time() - start) * 1000,
            )

        jira_url = jira_url.rstrip("/")
        auth_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            import base64

            auth_str = f"{jira_email}:{jira_token}"
            auth_bytes = auth_str.encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
            auth_headers["Authorization"] = f"Basic {auth_b64}"
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to encode Jira auth: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "list_issues":
                    jql = f"project={project} AND status!=Closed ORDER BY created DESC"
                    url = f"{jira_url}/rest/api/2/search"
                    response = await client.get(
                        url, headers=auth_headers,
                        params={"jql": jql, "maxResults": 50},
                    )
                    response.raise_for_status()
                    data = response.json()

                    issues = [
                        {
                            "id": issue["id"],
                            "key": issue["key"],
                            "summary": issue["fields"].get("summary", ""),
                            "status": issue["fields"].get("status", {}).get("name", ""),
                            "assignee": (
                                issue["fields"].get("assignee", {}).get("displayName")
                                if issue["fields"].get("assignee")
                                else None
                            ),
                            "created": issue["fields"].get("created", ""),
                        }
                        for issue in data.get("issues", [])
                    ]

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.jira.list_issues",
                        resource=project,
                        params={},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={"issues": issues, "count": len(issues)},
                        duration_ms=duration_ms,
                    )

                elif action == "create_issue":
                    url = f"{jira_url}/rest/api/2/issue"
                    payload: dict[str, Any] = {
                        "fields": {
                            "project": {"key": project},
                            "summary": params["title"],
                            "issuetype": {"name": "Task"},
                        },
                    }
                    body = params.get("body")
                    if body:
                        payload["fields"]["description"] = {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": body},
                                    ],
                                },
                            ],
                        }
                    assignee = params.get("assignee")
                    if assignee:
                        payload["fields"]["assignee"] = {"name": assignee}

                    response = await client.post(url, headers=auth_headers, json=payload)
                    response.raise_for_status()
                    issue = response.json()

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.jira.create_issue",
                        resource=project,
                        params={"title": params["title"]},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={
                            "id": issue["id"],
                            "key": issue["key"],
                            "self": issue.get("self"),
                        },
                        duration_ms=duration_ms,
                    )

                elif action == "update_issue":
                    issue_id: str = params["issue_id"]
                    url = f"{jira_url}/rest/api/2/issue/{issue_id}"
                    payload = {}
                    fields: dict[str, Any] = {}
                    title = params.get("title")
                    if title:
                        fields["summary"] = title
                    body = params.get("body")
                    if body:
                        fields["description"] = {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": body},
                                    ],
                                },
                            ],
                        }
                    if fields:
                        payload["fields"] = fields

                    response = await client.put(url, headers=auth_headers, json=payload)
                    response.raise_for_status()

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.jira.update_issue",
                        resource=project,
                        params={"issue_id": issue_id},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={"updated": issue_id},
                        duration_ms=duration_ms,
                    )

                else:
                    issue_id = params["issue_id"]
                    url = f"{jira_url}/rest/api/2/issue/{issue_id}/transitions"
                    payload = {
                        "transition": {"id": "31"},
                    }

                    transitions_url = f"{jira_url}/rest/api/2/issue/{issue_id}/transitions"
                    trans_response = await client.get(
                        transitions_url, headers=auth_headers,
                    )
                    if trans_response.status_code == 200:
                        transitions = trans_response.json().get("transitions", [])
                        close_id = None
                        for t in transitions:
                            name_lower = t["name"].lower()
                            if "close" in name_lower:
                                close_id = t["id"]
                                break
                        if close_id:
                            payload["transition"]["id"] = close_id

                    response = await client.post(url, headers=auth_headers, json=payload)
                    response.raise_for_status()

                    duration_ms = (time.time() - start) * 1000
                    audit.log(
                        user_id=user_id,
                        action="project_mgmt.jira.close_issue",
                        resource=project,
                        params={"issue_id": issue_id},
                        result="success",
                        duration_ms=duration_ms,
                    )
                    return ToolResult(
                        success=True,
                        data={"closed": issue_id},
                        duration_ms=duration_ms,
                    )

        except ImportError:
            return ToolResult(
                success=False,
                error="httpx library is required for Jira API calls. "
                "Install it with: pip install httpx",
                duration_ms=(time.time() - start) * 1000,
            )
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action=f"project_mgmt.jira.{action}",
                resource=project,
                params={"action": action},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=f"Jira API error: {e.response.status_code} {e.response.text[:500]}",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            audit.log(
                user_id=user_id,
                action=f"project_mgmt.jira.{action}",
                resource=project,
                params={"action": action},
                result="error",
                error=str(e),
                duration_ms=duration_ms,
            )
            return ToolResult(
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )
