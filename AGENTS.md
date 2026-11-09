# Repository rules

- Never commit secrets, real `.env` files, keystores, or Apple/Google credentials.
- Provide a sanitized `.env.example` with placeholder or local-development values instead of committing a real environment file.
- Keep private keys, signing certificates, provisioning profiles, service-account keys, and credential files out of version control. Never put real credentials in source code, documentation, tests, or example files.
