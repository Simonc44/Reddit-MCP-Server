# Security Policy

We are committed to maintaining a secure and reliable platform for our users. This security policy details supported versions, best practices for secure execution, and how to report potential vulnerabilities.

## Supported Versions

Only the latest release version on the `main` branch is actively supported and patched.

| Version | Supported | Notes |
|---------|-----------|-------|
| Latest (main branch) | :white_check_mark: Yes | Active development and patch branch. |
| <= 1.0.0 | :x: No | Please upgrade to the latest commit. |

---

## Secure Deployment & Best Practices

To ensure maximum security while running the Reddit MCP server, we recommend adhering to the following best practices:

1. **Local Execution Environment:** Run this MCP server inside an isolated virtual environment (using `venv` or `conda`) to minimize package interaction and dependencies conflicts with global system packages.
2. **Access Control:** Do not expose the standard I/O (stdin/stdout) of this server directly to public network endpoints. The server should ideally run locally on the same host machine as your LLM client (e.g., Claude Desktop).
3. **Containerization (Optional):** If running in highly sensitive environments, consider running the MCP client and server inside a containerized setup (like Docker) to sandbox file system access and system resources.
4. **Scraping Compliance:** This server operates solely on publicly accessible Reddit endpoints and does not handle user passwords, access tokens, or private user data. Do not modify the server to circumvent authenticated pages unless you are implementing secure OAuth protocols.

---

## Reporting a Vulnerability

If you find a security-related bug or vulnerability, please **do not** open a public issue. Public issues expose vulnerabilities before they can be successfully patched, putting other users at risk.

### Process to Report:
1. Send a detailed report to the repository owner or core maintainers (refer to the repository contact page).
2. In your report, please include:
   - A description of the vulnerability and its potential impact.
   - Detailed, step-by-step instructions to reproduce the behavior (proof of concept code, configuration, etc.).
   - Any suggested mitigations or patches.

### Response Time & Resolution:
- We aim to acknowledge receipt of security reports within **48 hours**.
- We will work closely with you to verify, investigate, and formulate a patch for the issue.
- Once a patch is fully tested and deployed, credit will be given to the reporter (unless they prefer to remain anonymous).
