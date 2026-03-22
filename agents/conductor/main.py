# Conductor - Agent Swarm Orchestrator
# Receives user intent, broadcasts to all agents, dispatches tasks to subagents.

import os
import re
import asyncio
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
import httpx
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import aio_pika
import redis.asyncio as aioredis
import psycopg
from prometheus_client import Counter, Gauge, make_asgi_app, CollectorRegistry

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('conductor')

# ==================== API KEY AUTH ====================

API_KEY = os.getenv('CONDUCTOR_API_KEY', '')
api_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


async def require_api_key(key: str = Security(api_key_header)):
    """Validate API key from X-API-Key header. Disabled when CONDUCTOR_API_KEY is unset."""
    if not API_KEY:
        return  # auth disabled — no key configured
    if not key or key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Prometheus metrics — use a dedicated registry to avoid conflicts
METRICS_REGISTRY = CollectorRegistry()
INTENTS_TOTAL = Counter('conductor_intents_total', 'Total intents received', registry=METRICS_REGISTRY)
TASKS_TOTAL = Counter('conductor_tasks_total', 'Total tasks dispatched', ['agent'], registry=METRICS_REGISTRY)
ACTIVE_TASKS = Gauge('conductor_active_tasks', 'Currently active tasks', ['agent'], registry=METRICS_REGISTRY)


# ==================== CONFIGURATION ====================

def load_config(path: str) -> dict:
    """Load conductor config from YAML."""
    config_path = Path(path)
    if not config_path.exists():
        logger.warning(f"Config not found at {path}, using defaults")
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f)


# ==================== DATA MODELS ====================

class ResourceSpec(BaseModel):
    model_config = {"extra": "allow"}
    type: str
    name: str = ""


class Constraint(BaseModel):
    name: str
    description: str = ""
    value: Optional[Any] = None


class UserIntent(BaseModel):
    action: str
    resource: ResourceSpec
    constraints: List[Constraint] = []
    expected_duration_seconds: int = 300
    rollback_on_error: bool = True
    approver: str


class IntentResponse(BaseModel):
    status: str
    intent_id: str
    action: str
    planned_tasks: List[Dict[str, Any]]
    message: str


class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    plan: Optional[Dict[str, Any]] = None
    status: str  # "planning", "awaiting_approval", "approved", "rejected", "clarifying"


# ==================== MESSAGE HELPERS ====================

def make_envelope(
    message_type: str,
    sender: str,
    body: Dict[str, Any],
    correlation_id: str = None,
    intent_id: str = None,
    recipient: str = None,
    task_id: str = None,
    priority: str = "normal"
) -> Dict[str, Any]:
    msg = {
        "message_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_type": message_type,
        "sender": sender,
        "sender_version": "1.0",
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "intent_id": intent_id or str(uuid.uuid4()),
        "priority": priority,
        "body": body,
    }
    if recipient:
        msg["recipient"] = recipient
    if task_id:
        msg["task_id"] = task_id
    return msg


async def publish(exchange: aio_pika.Exchange, routing_key: str, message: dict):
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(message).encode(),
            content_type='application/json',
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=routing_key,
    )


# ==================== CONDUCTOR SERVICE ====================

class ConductorService:
    def __init__(self, config: dict):
        self.config = config
        self.task_routing = config.get('taskRouting', {})
        self.gatekeeper_actions = set(
            config.get('gatekeeper', {}).get('requiredFor', [])
        )

        # Connections (initialized in connect())
        self.amqp_connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        self.redis: Optional[aioredis.Redis] = None
        self.pg_conn = None

    async def connect(self):
        """Connect to RabbitMQ, Redis, and PostgreSQL."""
        broker_url = os.getenv('INTENT_BROKER_URL')
        redis_url = os.getenv('REDIS_URL')
        pg_url = os.getenv('AUDIT_DB_URL')

        # RabbitMQ
        self.amqp_connection = await aio_pika.connect_robust(broker_url)
        self.channel = await self.amqp_connection.channel()
        await self.channel.set_qos(prefetch_count=10)
        await self._setup_exchanges()
        await self._setup_queues()
        logger.info("RabbitMQ connected, exchanges and queues ready")

        # Redis
        self.redis = await aioredis.from_url(redis_url, decode_responses=True)
        logger.info("Redis connected")

        # PostgreSQL
        try:
            self.pg_conn = await psycopg.AsyncConnection.connect(pg_url)
            logger.info("PostgreSQL connected")
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed (non-fatal): {e}")

    async def _setup_exchanges(self):
        """Declare all RabbitMQ exchanges."""
        exchange_defs = [
            ('agent.intent', aio_pika.ExchangeType.FANOUT),
            ('agent.task', aio_pika.ExchangeType.TOPIC),
            ('agent.event', aio_pika.ExchangeType.TOPIC),
            ('agent.alert', aio_pika.ExchangeType.TOPIC),
            ('agent.audit', aio_pika.ExchangeType.TOPIC),
        ]
        for name, ex_type in exchange_defs:
            self.exchanges[name] = await self.channel.declare_exchange(
                name, ex_type, durable=True
            )
        logger.info(f"Exchanges declared: {list(self.exchanges.keys())}")

    async def _setup_queues(self):
        """Declare queues and bind them to exchanges based on config."""
        task_ex = self.exchanges['agent.task']
        event_ex = self.exchanges['agent.event']
        alert_ex = self.exchanges['agent.alert']

        # Subagent task queues
        for agent_def in self.config.get('agents', {}).get('subagents', []):
            name = agent_def['name']
            queue = await self.channel.declare_queue(f'{name}.tasks', durable=True)
            await queue.bind(task_ex, routing_key=f'{name}.*')
            logger.info(f"Queue '{name}.tasks' bound to agent.task/{name}.*")

        # Observer queues
        for obs_def in self.config.get('observers', []):
            name = obs_def['name']
            subs = obs_def.get('subscriptions', [])
            queue = await self.channel.declare_queue(f'{name}.events', durable=True)
            for sub in subs:
                routing_key = f'agent.event.{sub}'
                await queue.bind(event_ex, routing_key=routing_key)
            if name == 'judge':
                await queue.bind(alert_ex, routing_key='agent.alert.*')
            logger.info(f"Queue '{name}.events' bound to {len(subs)} routing keys")

        # Conductor's own event listener queue
        conductor_q = await self.channel.declare_queue('conductor.events', durable=True)
        await conductor_q.bind(event_ex, routing_key='agent.event.#')
        await conductor_q.bind(alert_ex, routing_key='agent.alert.#')

        # Audit queue (captures everything)
        audit_q = await self.channel.declare_queue('audit.log', durable=True)
        audit_ex = self.exchanges['agent.audit']
        await audit_q.bind(audit_ex, routing_key='#')

    def plan_tasks(self, intent: UserIntent) -> List[Dict[str, Any]]:
        """Use config-driven task routing to plan tasks for an intent."""
        route = self.task_routing.get(intent.action)
        if route:
            return [
                {
                    "agent": step['agent'],
                    "task": step['task'],
                    "depends_on": step.get('dependsOn', []),
                }
                for step in route
            ]
        # Fallback: prefix-based routing for actions not in config
        action = intent.action
        prefix_to_agent = {
            'fw_': 'sapper',
            'network_': 'sapper',
            'ping_': 'sapper',
            'list_vm': 'superintendent',
            'list_node': 'superintendent',
            'vm_': 'superintendent',
            'node_': 'superintendent',
            'system_': 'superintendent',
            'start_vm': 'superintendent',
            'stop_vm': 'superintendent',
            'create_vm': 'superintendent',
            'deploy_': 'mercury',
            'docker_': 'mercury',
            'list_container': 'mercury',
            'stop_container': 'mercury',
            'remove_container': 'mercury',
            'pull_image': 'mercury',
            'scale_': 'mercury',
            'container_': 'mercury',
            'generate_': 'davinci',
            'apply_config': 'davinci',
            'create_iac': 'davinci',
            'git_': 'davinci',
        }
        for prefix, agent in prefix_to_agent.items():
            if action.startswith(prefix) or action == prefix:
                return [{"agent": agent, "task": action, "depends_on": []}]
        return []

    async def _dispatch_task(
        self, agent: str, operation: str, intent: UserIntent,
        intent_id: str, correlation_id: str,
    ) -> dict:
        """Dispatch a single task to an agent via RabbitMQ."""
        task_id = str(uuid.uuid4())
        task_body = {
            "operation": operation,
            "priority": "normal",
            "target_agent": agent,
            "parameters": {
                **intent.resource.model_dump(),
                **{c.name: c.value for c in intent.constraints if c.value is not None},
            },
            "gatekeeper_required": operation in self.gatekeeper_actions,
            "timeout_seconds": intent.expected_duration_seconds,
            "retry_policy": {"max_retries": 3, "backoff_seconds": 10},
        }
        task_msg = make_envelope(
            message_type="TASK_ASSIGNMENT",
            sender="conductor",
            body=task_body,
            correlation_id=correlation_id,
            intent_id=intent_id,
            recipient=agent,
            task_id=task_id,
        )
        routing_key = f"{agent}.{operation}"
        await publish(self.exchanges['agent.task'], routing_key, task_msg)

        await self.redis.setex(
            f"task:{task_id}", 3600,
            json.dumps({
                "status": "dispatched",
                "agent": agent,
                "operation": operation,
                "intent_id": intent_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        )
        TASKS_TOTAL.labels(agent=agent).inc()
        ACTIVE_TASKS.labels(agent=agent).inc()
        logger.info(f"Task {task_id} dispatched to {agent}: {operation}")
        return {"task_id": task_id, "agent": agent, "operation": operation}

    async def submit_intent(self, intent: UserIntent, user_id: str) -> IntentResponse:
        """Accept a user intent, broadcast it, and dispatch tasks with dependency ordering."""
        intent_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        # Store intent in Redis
        await self.redis.setex(
            f"intent:{intent_id}", 86400,
            json.dumps(intent.model_dump())
        )

        # Broadcast intent to all agents
        intent_msg = make_envelope(
            message_type="USER_INTENT",
            sender="conductor",
            body=intent.model_dump(),
            correlation_id=correlation_id,
            intent_id=intent_id,
            priority="high",
        )
        intent_msg["user_id"] = user_id
        await publish(self.exchanges['agent.intent'], '', intent_msg)
        INTENTS_TOTAL.inc()
        logger.info(f"Intent {intent_id} broadcast: {intent.action}")

        # Plan tasks
        planned = self.plan_tasks(intent)
        dispatched = []

        # Build a lookup: "agent.task" -> task_id for dependency resolution
        # Separate tasks into ready (no deps) and pending (has deps)
        for step in planned:
            step_key = f"{step['agent']}.{step['task']}"
            deps = step.get('depends_on', [])

            if not deps:
                # No dependencies — dispatch immediately
                info = await self._dispatch_task(
                    step['agent'], step['task'], intent, intent_id, correlation_id,
                )
                dispatched.append(info)
            else:
                # Has dependencies — store as pending, dispatch when deps complete
                task_id = str(uuid.uuid4())
                await self.redis.setex(
                    f"task:{task_id}", 3600,
                    json.dumps({
                        "status": "pending",
                        "agent": step['agent'],
                        "operation": step['task'],
                        "intent_id": intent_id,
                        "correlation_id": correlation_id,
                        "depends_on": deps,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                )
                # Index pending task by intent for lookup during event handling
                await self.redis.sadd(f"pending_tasks:{intent_id}", task_id)
                dispatched.append({
                    "task_id": task_id,
                    "agent": step['agent'],
                    "operation": step['task'],
                    "status": "pending",
                    "depends_on": deps,
                })
                logger.info(
                    f"Task {task_id} pending for {step['agent']}: {step['task']} "
                    f"(waiting on {deps})"
                )

        # Log to audit exchange
        audit_msg = make_envelope(
            message_type="INTENT_ACCEPTED",
            sender="conductor",
            body={
                "intent": intent.model_dump(),
                "user_id": user_id,
                "tasks_dispatched": sum(1 for d in dispatched if d.get('status') != 'pending'),
                "tasks_pending": sum(1 for d in dispatched if d.get('status') == 'pending'),
            },
            correlation_id=correlation_id,
            intent_id=intent_id,
        )
        await publish(self.exchanges['agent.audit'], 'audit.intent', audit_msg)

        pending_count = sum(1 for d in dispatched if d.get('status') == 'pending')
        immediate = len(dispatched) - pending_count
        return IntentResponse(
            status="accepted",
            intent_id=intent_id,
            action=intent.action,
            planned_tasks=dispatched,
            message=f"Intent broadcast, {immediate} task(s) dispatched, {pending_count} pending on dependencies",
        )

    async def handle_event(self, event: dict):
        """Handle events from subagents, including dependency-aware dispatch."""
        msg_type = event.get('message_type')
        task_id = event.get('task_id')
        sender = event.get('sender')
        body = event.get('body', {})

        if msg_type == 'TASK_COMPLETED':
            ACTIVE_TASKS.labels(agent=sender).dec()
            await self._update_task(task_id, 'completed', result=body.get('result'))
            logger.info(f"Task {task_id} completed by {sender}")
            # Store result for chat polling
            await self._store_task_result(task_id, sender, body)
            # Check if any pending tasks are now unblocked
            await self._check_pending_deps(task_id)

        elif msg_type == 'TASK_FAILED':
            ACTIVE_TASKS.labels(agent=sender).dec()
            error = body.get('error', 'unknown')
            await self._update_task(task_id, 'failed', error=str(error))
            logger.warning(f"Task {task_id} failed ({sender}): {error}")
            await self._store_task_result(task_id, sender, body, failed=True)
            # Cascade failure to dependent tasks
            await self._cascade_failure(task_id)

        elif msg_type == 'TASK_STARTED':
            await self._update_task(task_id, 'running')
            logger.info(f"Task {task_id} started by {sender}")

        elif msg_type == 'ANOMALY_DETECTED':
            logger.warning(f"Anomaly from {sender}: {event.get('body')}")
            # Route to Judge
            await publish(
                self.exchanges['agent.alert'],
                'agent.alert.anomaly',
                make_envelope(
                    message_type="INTENT_VERIFICATION_REQUEST",
                    sender="conductor",
                    body=event.get('body', {}),
                    intent_id=event.get('intent_id'),
                    recipient="judge",
                )
            )

    async def _check_pending_deps(self, completed_task_id: str):
        """When a task completes, check if any pending tasks in the same intent are now ready."""
        raw = await self.redis.get(f"task:{completed_task_id}")
        if not raw:
            return
        completed_task = json.loads(raw)
        intent_id = completed_task.get('intent_id')
        if not intent_id:
            return

        # Build set of completed "agent.operation" keys for this intent
        completed_keys = await self._get_completed_keys(intent_id)

        # Check each pending task for this intent
        pending_ids = await self.redis.smembers(f"pending_tasks:{intent_id}")
        for pending_id in pending_ids:
            pending_raw = await self.redis.get(f"task:{pending_id}")
            if not pending_raw:
                await self.redis.srem(f"pending_tasks:{intent_id}", pending_id)
                continue

            pending_task = json.loads(pending_raw)
            if pending_task.get('status') != 'pending':
                continue

            deps = pending_task.get('depends_on', [])
            if all(dep in completed_keys for dep in deps):
                # All dependencies satisfied — dispatch this task
                logger.info(f"Dependencies met for task {pending_id}, dispatching")

                # Recover the original intent for parameters
                intent_raw = await self.redis.get(f"intent:{intent_id}")
                intent = UserIntent(**json.loads(intent_raw)) if intent_raw else None

                if intent:
                    info = await self._dispatch_task(
                        pending_task['agent'],
                        pending_task['operation'],
                        intent,
                        intent_id,
                        pending_task.get('correlation_id', str(uuid.uuid4())),
                    )
                    # Remove from pending set
                    await self.redis.srem(f"pending_tasks:{intent_id}", pending_id)
                    # Delete the old pending record (dispatch_task creates a new one)
                    await self.redis.delete(f"task:{pending_id}")
                    logger.info(
                        f"Pending task {pending_id} dispatched as {info['task_id']} "
                        f"to {info['agent']}: {info['operation']}"
                    )
                else:
                    logger.error(f"Cannot dispatch pending task {pending_id}: intent {intent_id} not found")

    async def _cascade_failure(self, failed_task_id: str):
        """When a task fails, mark all tasks that depend on it as blocked."""
        raw = await self.redis.get(f"task:{failed_task_id}")
        if not raw:
            return
        failed_task = json.loads(raw)
        intent_id = failed_task.get('intent_id')
        if not intent_id:
            return

        failed_key = f"{failed_task.get('agent')}.{failed_task.get('operation')}"

        pending_ids = await self.redis.smembers(f"pending_tasks:{intent_id}")
        for pending_id in pending_ids:
            pending_raw = await self.redis.get(f"task:{pending_id}")
            if not pending_raw:
                continue
            pending_task = json.loads(pending_raw)
            deps = pending_task.get('depends_on', [])
            if failed_key in deps:
                await self._update_task(pending_id, 'blocked',
                                        error=f"Dependency {failed_key} failed")
                await self.redis.srem(f"pending_tasks:{intent_id}", pending_id)
                logger.warning(
                    f"Task {pending_id} ({pending_task['agent']}.{pending_task['operation']}) "
                    f"blocked: dependency {failed_key} failed"
                )

    async def _get_completed_keys(self, intent_id: str) -> set:
        """Get all completed 'agent.operation' keys for an intent."""
        completed = set()
        async for key in self.redis.scan_iter(match="task:*"):
            task_raw = await self.redis.get(key)
            if not task_raw:
                continue
            task = json.loads(task_raw)
            if task.get('intent_id') == intent_id and task.get('status') == 'completed':
                completed.add(f"{task.get('agent')}.{task.get('operation')}")
        return completed

    async def _update_task(self, task_id: str, status: str, error: str = None, result: Any = None):
        """Update task state in Redis."""
        if not task_id:
            return
        raw = await self.redis.get(f"task:{task_id}")
        if raw:
            data = json.loads(raw)
            data['status'] = status
            if error:
                data['error'] = error
            if result is not None:
                data['result'] = result
            data['updated_at'] = datetime.now(timezone.utc).isoformat()
            await self.redis.setex(f"task:{task_id}", 3600, json.dumps(data))

    async def _store_task_result(self, task_id: str, agent: str, body: dict, failed: bool = False):
        """Store task result keyed by intent_id for chat result polling."""
        raw = await self.redis.get(f"task:{task_id}")
        if not raw:
            return
        task = json.loads(raw)
        intent_id = task.get('intent_id')
        if not intent_id:
            return

        entry = {
            "task_id": task_id,
            "agent": agent,
            "operation": task.get('operation', ''),
            "status": "failed" if failed else "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if failed:
            entry["error"] = body.get('error', 'unknown')
        else:
            entry["result"] = body.get('result', {})

        # Append to a list of results for this intent
        await self.redis.rpush(f"intent_results:{intent_id}", json.dumps(entry))
        await self.redis.expire(f"intent_results:{intent_id}", 3600)

    # ==================== LLM CHAT ====================

    async def _get_live_inventory(self) -> str:
        """Query agents for live infrastructure inventory."""
        inventory_parts = []
        agents_urls = {
            'superintendent': os.getenv('SUPERINTENDENT_URL', 'http://superintendent:8001'),
            'mercury': os.getenv('MERCURY_URL', 'http://mercury:8002'),
        }

        async with httpx.AsyncClient(timeout=10) as client:
            # Get VMs from Superintendent
            try:
                resp = await client.get(f"{agents_urls['superintendent']}/vms")
                if resp.status_code == 200:
                    vms = resp.json().get('vms', [])
                    if vms:
                        lines = ["LIVE VM INVENTORY (from Proxmox):"]
                        lines.append("| VMID | Name | Node | Status | CPUs | RAM (GB) |")
                        lines.append("|------|------|------|--------|------|----------|")
                        for vm in vms:
                            lines.append(
                                f"| {vm['vmid']} | {vm['name']} | {vm['node']} "
                                f"| {vm['status']} | {vm['cpus']} | {vm['mem_max_gb']} |"
                            )
                        inventory_parts.append('\n'.join(lines))
            except Exception as e:
                logger.debug(f"Failed to get VM inventory: {e}")

            # Get containers from Mercury
            try:
                resp = await client.get(f"{agents_urls['mercury']}/containers")
                if resp.status_code == 200:
                    containers = resp.json().get('containers', [])
                    if containers:
                        lines = ["LIVE CONTAINER INVENTORY (from Docker on cainfra02):"]
                        for c in containers[:20]:  # Limit to 20
                            lines.append(f"- {c.get('name', 'unknown')}: {c.get('status', '?')}")
                        inventory_parts.append('\n'.join(lines))
            except Exception as e:
                logger.debug(f"Failed to get container inventory: {e}")

        return '\n\n'.join(inventory_parts) if inventory_parts else ''

    def _load_project_context(self) -> str:
        """Load static project context from mounted file."""
        context_path = Path('/etc/conductor/context.md')
        if context_path.exists():
            text = context_path.read_text()
            # Truncate if too long (keep under 4K tokens approx)
            if len(text) > 8000:
                text = text[:8000] + '\n... (truncated)'
            return text
        return ''

    async def _build_system_prompt(self) -> str:
        """Build a system prompt with agents, actions, live inventory, and project context."""
        agents_desc = []
        for sa in self.config.get('agents', {}).get('subagents', []):
            caps = ', '.join(sa.get('capabilities', []))
            agents_desc.append(f"- {sa['name']}: {caps}")

        routes = list(self.task_routing.keys())

        # Gather dynamic context
        live_inventory = await self._get_live_inventory()
        project_context = self._load_project_context()

        context_block = ''
        if project_context:
            context_block += f"\nPROJECT CONTEXT (CyberFlight Lab):\n{project_context}\n"
        if live_inventory:
            context_block += f"\n{live_inventory}\n"

        return f"""You are the Conductor, an AI orchestrator for the CyberFlight Lab infrastructure.
Your job is to translate natural language requests into structured intent JSON.

AVAILABLE AGENTS:
{chr(10).join(agents_desc)}

KNOWN ACTIONS (taskRouting):
{', '.join(routes)}

ACTION GUIDE (Sapper / OpenWrt router):
- fw_list_rules, fw_list_zones, fw_list_redirects, fw_list_forwarding: read firewall config
- fw_status: full firewall overview (zones + rules + redirects + forwarding + iptables)
- fw_add_rule: create a new firewall traffic rule
- fw_delete_rule: delete a firewall rule by name or section
- fw_edit_rule: modify an existing rule (change target, port, source, etc.)
- fw_move_rule: reorder a rule to a different position (params: name, position)
- fw_add_redirect / fw_delete_redirect: manage port forwards (DNAT)
- fw_add_forwarding: add zone-to-zone forwarding
- fw_dhcp_leases: list active and static DHCP clients on the router
- fw_logs: read router system/firewall logs (params: lines, filter)
- ping_test: ping a target from the router (params: target)
- network_status: show interfaces and routes on the router or a host
- configure_network: configure IP on a LINUX HOST (NOT the router — use fw_* for OpenWrt)
{context_block}
INTENT JSON FORMAT:
{{
  "action": "<action_name>",
  "resource": {{"type": "<resource_type>", "name": "<resource_name>", ...extra fields as needed}},
  "constraints": [{{"name": "<constraint>", "value": <value>}}],
  "expected_duration_seconds": 300,
  "rollback_on_error": true,
  "approver": "ron"
}}

RULES:
1. ALWAYS use exact names from the inventory above (e.g., "BethClaw" not "bethclaw", VMID 101 not "vm101").
2. If the user's request maps to a known action, use it. Otherwise, pick the closest match.
3. Always include "approver": "ron" unless the user specifies otherwise.
4. If the request is ambiguous, ask a clarifying question instead of guessing. Prefix your reply with "CLARIFY:" when asking.
5. If you can form an intent, respond with ONLY the JSON block wrapped in ```json``` fences. Add a one-line summary BEFORE the JSON.
6. For multi-step workflows, use the most appropriate single top-level action. The Conductor will decompose it via taskRouting.
7. Keep responses concise — you are an infrastructure operator, not a chatbot.
8. The "name" field in resource should be the VM name, container name, or target as the user refers to it."""

    async def _call_llm(self, messages: list) -> str:
        """Call the configured LLM provider (Ollama or OpenAI-compatible)."""
        provider = os.getenv('LLM_PROVIDER', 'ollama').lower()

        if provider == 'openai':
            return await self._call_openai(messages)
        else:
            return await self._call_ollama(messages)

    async def _call_ollama(self, messages: list) -> str:
        """Call Ollama chat API."""
        ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        ollama_model = os.getenv('OLLAMA_MODEL', 'qwen3:8b-nothink')

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f'{ollama_url}/api/chat', json={
                'model': ollama_model,
                'messages': messages,
                'stream': False,
            })
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Ollama returned {resp.status_code}")
            return resp.json().get('message', {}).get('content', '')

    async def _call_openai(self, messages: list) -> str:
        """Call OpenAI-compatible API (Kimi, GPT, DeepSeek, etc.)."""
        base_url = os.getenv('OPENAI_BASE_URL', 'https://api.moonshot.cn/v1')
        api_key = os.getenv('OPENAI_API_KEY', '')
        model = os.getenv('OPENAI_MODEL', 'moonshot-v1-8k')

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.3,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f'{base_url}/chat/completions',
                headers=headers,
                json=payload,
            )
            if resp.status_code != 200:
                detail = resp.text[:200]
                raise HTTPException(status_code=502, detail=f"OpenAI API returned {resp.status_code}: {detail}")
            choices = resp.json().get('choices', [])
            if not choices:
                raise HTTPException(status_code=502, detail="OpenAI API returned no choices")
            return choices[0].get('message', {}).get('content', '')

    def _fixup_action(self, plan: dict, user_message: str) -> dict:
        """Correct common LLM misrouting. The LLM often picks configure_network
        as a catch-all for router queries that should use specific fw_* actions."""
        action = plan.get('action', '')
        msg = user_message.lower()

        if action == 'configure_network':
            # Map to the right fw_* action based on keywords in the user message
            keyword_map = [
                (['dhcp', 'lease', 'client'], 'fw_dhcp_leases'),
                (['log', 'syslog', 'logread', 'dmesg'], 'fw_logs'),
                (['move', 'reorder', 'position', 'priority'], 'fw_move_rule'),
                (['edit', 'modify', 'change', 'update'], 'fw_edit_rule'),
                (['rule', 'traffic', 'block', 'allow', 'drop', 'reject'], 'fw_list_rules'),
                (['zone'], 'fw_list_zones'),
                (['redirect', 'port forward', 'dnat'], 'fw_list_redirects'),
                (['forward'], 'fw_list_forwarding'),
                (['status', 'overview', 'firewall'], 'fw_status'),
                (['ping'], 'ping_test'),
                (['interface', 'route', 'ip addr'], 'network_status'),
            ]
            for keywords, new_action in keyword_map:
                if any(kw in msg for kw in keywords):
                    logger.info(f"Action fixup: {action} -> {new_action} (matched: {keywords})")
                    plan['action'] = new_action
                    break

        return plan

    async def chat(self, conversation_id: str, user_message: str) -> dict:
        """Process a chat message through the configured LLM and return a response with optional plan."""
        # Load or create conversation history
        history_key = f"chat:{conversation_id}"
        raw_history = await self.redis.get(history_key)
        history = json.loads(raw_history) if raw_history else []

        # Append user message
        history.append({"role": "user", "content": user_message})

        # Build messages with dynamic context
        system_prompt = await self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}] + history

        # Call configured LLM
        try:
            llm_reply = await self._call_llm(messages)
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Cannot reach LLM service")

        # Strip think tags from qwen3
        llm_reply = re.sub(r'<think>.*?</think>', '', llm_reply, flags=re.DOTALL).strip()

        # Append assistant reply to history
        history.append({"role": "assistant", "content": llm_reply})
        await self.redis.setex(history_key, 3600, json.dumps(history))

        # Try to extract JSON intent from the reply
        plan = None
        status = "clarifying"
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_reply, re.DOTALL)
        if json_match:
            try:
                plan = json.loads(json_match.group(1))
                # Fix LLM misrouting: configure_network is for Linux hosts only
                plan = self._fixup_action(plan, user_message)
                status = "awaiting_approval"
                # Store the pending plan
                await self.redis.setex(
                    f"chat_plan:{conversation_id}", 3600, json.dumps(plan)
                )
            except json.JSONDecodeError:
                pass

        return {
            "conversation_id": conversation_id,
            "reply": llm_reply,
            "plan": plan,
            "status": status,
        }

    async def approve_plan(self, conversation_id: str, user_id: str) -> IntentResponse:
        """Approve and execute a pending chat plan."""
        raw_plan = await self.redis.get(f"chat_plan:{conversation_id}")
        if not raw_plan:
            raise HTTPException(status_code=404, detail="No pending plan for this conversation")

        plan = json.loads(raw_plan)

        # Validate and convert to UserIntent
        intent = UserIntent(
            action=plan.get('action', ''),
            resource=ResourceSpec(**plan.get('resource', {'type': 'unknown', 'name': 'unknown'})),
            constraints=[Constraint(**c) for c in plan.get('constraints', [])],
            expected_duration_seconds=plan.get('expected_duration_seconds', 300),
            rollback_on_error=plan.get('rollback_on_error', True),
            approver=plan.get('approver', user_id),
        )

        # Clear the pending plan
        await self.redis.delete(f"chat_plan:{conversation_id}")

        # Append approval to chat history
        history_key = f"chat:{conversation_id}"
        raw_history = await self.redis.get(history_key)
        history = json.loads(raw_history) if raw_history else []
        history.append({"role": "user", "content": "[APPROVED]"})
        history.append({"role": "assistant", "content": f"Plan approved. Dispatching intent: {intent.action}"})
        await self.redis.setex(history_key, 3600, json.dumps(history))

        # Execute via the normal intent pipeline
        response = await self.submit_intent(intent, user_id)

        # Link conversation to intent for result polling
        await self.redis.setex(
            f"chat_intent:{conversation_id}", 3600, response.intent_id
        )
        return response

    async def disconnect(self):
        if self.amqp_connection:
            await self.amqp_connection.close()
        if self.redis:
            await self.redis.close()
        if self.pg_conn:
            await self.pg_conn.close()
        logger.info("Conductor shutdown complete")


# ==================== APPLICATION ====================

config = load_config(os.getenv('AGENT_CONFIG', '/etc/conductor/config.yaml'))
conductor = ConductorService(config)


async def event_listener():
    """Background task: consume events from conductor.events queue."""
    channel = await conductor.amqp_connection.channel()
    queue = await channel.declare_queue('conductor.events', durable=True)

    async with queue.iterator() as stream:
        async for message in stream:
            async with message.process():
                try:
                    event = json.loads(message.body)
                    await conductor.handle_event(event)
                except Exception as e:
                    logger.error(f"Event handling error: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await conductor.connect()
    listener_task = asyncio.create_task(event_listener())
    logger.info("Conductor online")
    yield
    listener_task.cancel()
    await conductor.disconnect()


app = FastAPI(
    title="Conductor - Agent Swarm Orchestrator",
    description="Receives user intent, broadcasts to agents, dispatches tasks",
    version="0.3.0",
    lifespan=lifespan,
)

# Mount Prometheus metrics at /metrics
metrics_app = make_asgi_app(registry=METRICS_REGISTRY)
app.mount("/metrics", metrics_app)

# Serve web UI
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/ui")


@app.get("/ui")
async def ui_index():
    return FileResponse(STATIC_DIR / "index.html")


# ==================== ENDPOINTS ====================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "conductor",
        "version": "0.3.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/intent", response_model=IntentResponse, dependencies=[Depends(require_api_key)])
async def submit_intent(intent: UserIntent, user_id: str = "keymaster"):
    """Submit a user intent for orchestration."""
    try:
        return await conductor.submit_intent(intent, user_id)
    except Exception as e:
        logger.error(f"Intent submission failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/intent/{intent_id}", dependencies=[Depends(require_api_key)])
async def get_intent(intent_id: str):
    """Get the status of an intent and its tasks."""
    raw = await conductor.redis.get(f"intent:{intent_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Intent not found")

    # Scan for tasks belonging to this intent
    tasks = []
    async for key in conductor.redis.scan_iter(match="task:*"):
        task_raw = await conductor.redis.get(key)
        if task_raw:
            task = json.loads(task_raw)
            if task.get('intent_id') == intent_id:
                task['task_id'] = key.removeprefix('task:')
                tasks.append(task)

    return {
        "intent_id": intent_id,
        "intent": json.loads(raw),
        "tasks": tasks,
    }


@app.post("/task/{task_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel_task(task_id: str):
    """Cancel a running task."""
    raw = await conductor.redis.get(f"task:{task_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Task not found")

    task = json.loads(raw)
    cancel_msg = make_envelope(
        message_type="TASK_CANCEL",
        sender="conductor",
        body={"task_id": task_id, "reason": "user_requested"},
        recipient=task['agent'],
        task_id=task_id,
    )
    await publish(
        conductor.exchanges['agent.task'],
        f"{task['agent']}.cancel",
        cancel_msg,
    )
    await conductor._update_task(task_id, 'cancelled')
    return {"status": "cancelled", "task_id": task_id}


@app.get("/agents", dependencies=[Depends(require_api_key)])
async def list_agents():
    """List configured agents and their capabilities."""
    subagents = config.get('agents', {}).get('subagents', [])
    observers = config.get('observers', [])
    return {"subagents": subagents, "observers": observers}


# ==================== CHAT ENDPOINTS ====================

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(msg: ChatMessage):
    """Send a natural language message to Conductor. Returns a plan for approval."""
    conversation_id = msg.conversation_id or str(uuid.uuid4())
    result = await conductor.chat(conversation_id, msg.message)
    return ChatResponse(**result)


@app.post("/chat/{conversation_id}/approve", response_model=IntentResponse, dependencies=[Depends(require_api_key)])
async def approve_chat_plan(conversation_id: str, user_id: str = "ron"):
    """Approve a pending plan from a chat conversation and execute it."""
    return await conductor.approve_plan(conversation_id, user_id)


@app.post("/chat/{conversation_id}/reject", dependencies=[Depends(require_api_key)])
async def reject_chat_plan(conversation_id: str, reason: str = ""):
    """Reject a pending plan. Optionally provide a reason to refine."""
    await conductor.redis.delete(f"chat_plan:{conversation_id}")
    if reason:
        # Feed the rejection back into the conversation for refinement
        result = await conductor.chat(conversation_id, f"I rejected that plan. {reason}")
        return ChatResponse(**result)
    return {"status": "rejected", "conversation_id": conversation_id}


@app.get("/chat/{conversation_id}/results", dependencies=[Depends(require_api_key)])
async def get_chat_results(conversation_id: str):
    """Poll for task results from an approved plan."""
    intent_id = await conductor.redis.get(f"chat_intent:{conversation_id}")
    if not intent_id:
        return {"status": "no_intent", "results": []}

    # Get all results for this intent
    raw_results = await conductor.redis.lrange(f"intent_results:{intent_id}", 0, -1)
    results = [json.loads(r) for r in raw_results]

    # Count expected tasks
    tasks = []
    async for key in conductor.redis.scan_iter(match="task:*"):
        task_raw = await conductor.redis.get(key)
        if task_raw:
            task = json.loads(task_raw)
            if task.get('intent_id') == intent_id:
                tasks.append(task)

    total = len(tasks)
    done = sum(1 for t in tasks if t.get('status') in ('completed', 'failed', 'blocked'))

    return {
        "status": "complete" if done >= total and total > 0 else "pending",
        "tasks_total": total,
        "tasks_done": done,
        "results": results,
    }


@app.get("/chat/{conversation_id}", dependencies=[Depends(require_api_key)])
async def get_chat_history(conversation_id: str):
    """Get the conversation history for a chat session."""
    raw = await conductor.redis.get(f"chat:{conversation_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Conversation not found")
    plan_raw = await conductor.redis.get(f"chat_plan:{conversation_id}")
    return {
        "conversation_id": conversation_id,
        "messages": json.loads(raw),
        "pending_plan": json.loads(plan_raw) if plan_raw else None,
    }


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
