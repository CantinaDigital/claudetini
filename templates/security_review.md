Security review for {{project_name}}.

Changed files:
{{changed_files}}

Review focus:
- Exposed credentials or secrets
- Input validation and injection risk
- Authn/authz flaws
- Unsafe subprocess/file/network patterns

Respond in JSON:
{
  "status": "pass|warn|fail",
  "summary": "...",
  "findings": [
    {"severity":"low|medium|high","description":"...","file":"...","line":123}
  ]
}
