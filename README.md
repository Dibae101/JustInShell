
# MCP-Orchestrator: Terminal-Based Linux Fleet Manager

A powerful Django-based Model Context Protocol (MCP) Orchestrator for managing and controlling Linux-based agents in distributed environments. This application provides advanced terminal management, secure agent communication, and configuration deployment capabilities with intelligent features for enhanced security, automation, and observability.

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Features](#features)
  - [Phase 1: SSH Terminal + Endpoint UI](#phase-1-ssh-terminal--endpoint-ui)
  - [Phase 2: MCP Server + Agent Communication](#phase-2-mcp-server--agent-communication)
  - [Phase 3: Command Broadcast + Config Push](#phase-3-command-broadcast--config-push)
  - [Smart Add-Ons](#smart-add-ons)
- [Technical Implementation](#technical-implementation)
  - [Backend (Django)](#backend-django)
  - [Frontend (Django Templates + Tailwind CSS)](#frontend-django-templates--tailwind-css)
  - [Agent Component](#agent-component)
- [API Endpoints](#api-endpoints)
- [Security Considerations](#security-considerations)
- [Development Roadmap](#development-roadmap)
- [Installation and Setup](#installation-and-setup)
- [Contributing](#contributing)
- [License](#license)

## Project Overview

MCP-Orchestrator allows centralized control of remote Linux-based endpoints using secure SSH access, real-time context-aware agent communication (via gRPC), and push-based configuration or command execution. It uses Django and Tailwind CSS for full-stack development with modern UI features and secure, scalable backend logic.

## Architecture

```
MCP Orchestrator
├── SSH Terminal Manager
├── MCP gRPC Server
├── Command & Config Manager
└── Smart Add-Ons
      ├── JIT Access
      ├── Audit Logs
      ├── Endpoint Map
      └── AI Suggestions

Clients:
├── SSH Connections
├── gRPC Clients (Agents)
└── WebSocket Dashboards

Managed Endpoints:
├── Linux Host + Agent
├── Linux Host + Agent
└── ...
```

## Features

### Phase 1: SSH Terminal + Endpoint UI
- Multi-protocol SSH support
- Group and tag endpoints
- Session tracking and monitoring
- Credential management and secure storage

### Phase 2: MCP Server + Agent Communication
- Secure registration with heartbeat
- Metadata reporting (CPU, memory, disk)
- Agent lifecycle handling and updates

### Phase 3: Command Broadcast + Config Push
- Push scripts and files to nodes
- Track execution with logs and status
- Backup/rollback support

## Smart Add-Ons
- Just-in-Time SSH keys for temporary access
- Full audit logs of commands and access
- Live endpoint mapping dashboard
- AI-powered command suggestions (Gemini/OpenAI)
- Drift detection between baseline and runtime

## Technical Implementation

### Backend (Django)
- Django apps: endpoints, agents, deployment, addons
- PostgreSQL, Redis, gRPC server

### Frontend (Django Templates + Tailwind CSS)
- Tailwind CSS + HTMX + Alpine.js
- xterm.js integration for SSH terminal
- WebSocket support for real-time updates

### Agent Component
- Go/Python agent with gRPC TLS client
- Resource monitoring, command execution
- Secure update mechanism

## Sample API Endpoints

Sample endpoints:
- `POST /api/auth/login/`
- `GET /api/endpoints/`
- `POST /api/agents/register/`
- `POST /api/deployment/commands/`
- `GET /api/addons/drift/`

WebSocket:
- `/ws/terminal/{endpoint_id}/`
- `/ws/agent-events/`

## Security Considerations

- JWT-based auth with RBAC
- TLS for all comms
- Encrypted secrets, signed commands
- Full auditing and session recording

## Development Roadmap

1. ✅ SSH terminal & endpoint UI
2. ✅ Agent communication via gRPC
3. ✅ Command/config broadcast
4. 🔜 Smart Add-ons (AI, JIT, Drift)
5. 🔜 Multi-tenant support

## Installation and Setup

### Backend
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend (Tailwind Templates)
- Link Tailwind CDN or build via PostCSS
- Use HTMX and Alpine.js in templates

### Agent
```bash
curl -sSL https://orchestrator/install-agent.sh | sudo bash
sudo mcp-agent register --server=https://orchestrator --token=<TOKEN>
```

## Contributing

See `CONTRIBUTING.md` for guidelines. We welcome features, fixes, and ideas.

## License

MIT License
