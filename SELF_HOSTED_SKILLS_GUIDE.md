# Self-Hosted Mem0 Server - Skills Guide for Platform-Client Approach

This guide documents all changes made to skills in the `skills/` directory to support using the Platform Client (`MemoryClient`/`AsyncMemoryClient`) approach with a self-hosted Mem0 server. 

These changes enable pointing the official Mem0 SDK clients to a locally/self-hosted Mem0 instance by specifying `MEM0_BASE_URL` in addition to `MEM0_API_KEY`.

## Overview

The key change is that both `MEM0_API_KEY` and `MEM0_BASE_URL` are now required for the Platform-client approach. The base URL for Mem0 Platform REST API endpoints is derived from `MEM0_BASE_URL`. When both environment variables are detected, agents will automatically use them with `MemoryClient` or `AsyncMemoryClient`.

For self-hosted servers, `MEM0_BASE_URL` should point to your self-hosted instance (e.g., `http://localhost:8888`), while `MEM0_API_KEY` is still required by the client.

## Changes by Skill

### 1. `skills/mem0` (Core Mem0 Skill)

The core skill already had extensive documentation of this pattern. Changes ensure consistency:

- **SKILL.md**: Already documents `MEM0_BASE_URL` requirement for Platform-client approach, showing how to pass `host` to `MemoryClient` and noting environment variable detection
- **client/python.md**: Documents `MemoryClient`/`AsyncMemoryClient` constructors requiring both `api_key` and `host`, with notes about environment variable detection
- **client/node.md**: Documents TypeScript client requiring both `apiKey` and `host`
- **All references**: Updated to reflect v3 API patterns and platform-client requirements

### 2. `skills/mem0-cli` (CLI Skill)

Updated to support self-hosted/base URL configuration:

- **SKILL.md**: Updated compatibility to mention both `MEM0_API_KEY` and `MEM0_BASE_URL`. Installation/auth examples now show setting both env vars.
- **README.md**: Added note about `MEM0_BASE_URL` being required for Platform-client approach
- **references/configuration.md**: Added `MEM0_BASE_URL` to environment variables table with description. Updated precedence order to include `MEM0_BASE_URL`.
- **references/command-reference.md**: Updated agent-rush commands to require both env vars
- **references/workflows.md**: Updated CI examples to pass `--base-url`, and added `MEM0_BASE_URL` to environment variable examples

### 3. `skills/mem0-self-improvement` (Self-Improvement Skill)

This skill was updated as part of the current changes:

- **SKILL.md**: 
  - Updated Python example to explicitly pass both `api_key` and `host` from environment variables
  - Added import for `os`
  - Changed comment to indicate reading both variables
- **README.md**:
  - Updated Prerequisites to state: "If the agent detects the environment variables `MEM0_API_KEY` and `MEM0_BASE_URL`, it will use these values; otherwise, it will prompt the user to set them."
  - Clarified that credentials can come from Platform, CLI, or self-hosted OSS stack

### 4. `skills/mem0-vercel-ai-sdk` (Vercel AI SDK Provider)

Updated for compatibility with self-hosted/base URL configuration:

- **SKILL.md**: Updated compatibility notes
- **README.md**: Updated to mention base URL configuration
- **references/provider-api.md**: Updated provider initialization to show `host`/base URL configuration
- **references/memory-utilities.md**: Updated utility functions to accept/pass base URL
- **references/usage-patterns.md**: Updated examples to include base URL configuration

### 5. `skills/mem0-oss-to-platform` (Migration Skill)

Updated migration guidance for platform-client approach:

- **references/api-mapping.md**: Updated examples to show passing both `api_key` and `host`. Added notes about both env vars being required.
- **references/gotchas.md**: Updated API key & secrets section to require both `MEM0_API_KEY` and `MEM0_BASE_URL`. Clarified TS client doesn't read env vars automatically.
- **references/plan-template.md**: Updated prerequisites and verification steps to include `MEM0_BASE_URL`

## Usage for Self-Hosted Servers

### Environment Setup

```bash
export MEM0_API_KEY="your-api-key"  # Still required by the client
export MEM0_BASE_URL="http://localhost:8888"  # Point to your self-hosted instance
```

### Python Example

```python
from mem0 import MemoryClient
import os

client = MemoryClient(
    api_key=os.environ.get("MEM0_API_KEY"),
    host=os.environ.get("MEM0_BASE_URL"),
)
```

### TypeScript Example

```typescript
import MemoryClient from 'mem0ai';

const client = new MemoryClient({
    apiKey: process.env.MEM0_API_KEY!,
    host: process.env.MEM0_BASE_URL!,
});
```

### CLI Usage

```bash
export MEM0_API_KEY="your-api-key"
export MEM0_BASE_URL="http://localhost:8888"
mem0 add "I prefer dark mode" --user-id alice
```

## Key Points

1. **Both variables required**: For the Platform-client approach (`MemoryClient`/`AsyncMemoryClient`), both `MEM0_API_KEY` and `MEM0_BASE_URL` must be provided and exported
2. **Base URL derived from MEM0_BASE_URL**: The base URL for REST API endpoints is derived from the `MEM0_BASE_URL` value
3. **Automatic detection**: If the agent detects both environment variables, it will use them automatically for Platform-client approach
4. **Self-hosted compatible**: Point `MEM0_BASE_URL` to your self-hosted Mem0 server (e.g., `http://localhost:8888`) instead of `https://api.mem0.ai`
5. **Fallback behavior**: If variables are not set, agents will prompt the user to provide them

## Migration Notes

When migrating from OSS `Memory` class to Platform-client approach with self-hosted server, follow the guidance in `skills/mem0-oss-to-platform/` with these updated requirements.

---

*This guide was generated from changes comparing the current branch against `main`. All skill files have been updated to support the platform-client approach with self-hosted Mem0 servers.*
