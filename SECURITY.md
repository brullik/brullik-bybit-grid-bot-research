# Security Policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability involving credentials, fund movement, authentication, order execution, risk bypass, or private account data. Contact the repository owner privately through GitHub instead.

## Secrets policy

The repository must never contain:

- Bybit API key or secret;
- Telegram bot token or chat identifiers;
- private keys or signing material;
- account exports;
- live runtime databases;
- private strategy releases;
- raw request/response logs containing authentication headers;
- cloud storage credentials.

Only redacted examples and `.env.example`-style names may be committed during implementation.

## Permission model

Separate credentials are required by runtime:

- `grid-data`: public market data; no trading permission;
- `grid-research`: offline; no Bybit key;
- `grid-release`: no trading permission;
- `grid-live`: read + trade only, no withdrawal permission;
- operator tooling: least privilege and explicit audit logging.

A dedicated trading subaccount is the preferred production design. Any use of a main account requires an explicit owner risk exception.

## Fail-closed requirements

Live must block new entries when:

- strategy release verification fails;
- data is stale or a candle gap is unresolved;
- exchange time synchronization is outside tolerance;
- reconciliation is incomplete;
- account or bot state conflicts with local state;
- risk limits cannot be computed exactly;
- Bybit validation fails or is unavailable beyond the configured deadline;
- emergency stop is active;
- required audit storage is unavailable.

## Dependency and supply-chain policy

- Pin implementation dependencies with hashes where practical.
- Review dependency license and maintenance status.
- Generate an SBOM before live release.
- Scan dependencies and containers before deployment.
- Do not execute untrusted notebooks, datasets, or downloaded archives without validation.
