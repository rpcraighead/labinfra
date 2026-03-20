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
        # Fallback: simple mapping
        action_to_agent = {
            'provision_vm': 'superintendent',
            'list_vms': 'superintendent',
            'list_nodes': 'superintendent',
            'vm_status': 'superintendent',
            'node_status': 'superintendent',
            'system_status': 'superintendent',
            'start_vm': 'superintendent',
            'stop_vm': 'superintendent',
            'create_vm': 'superintendent',
            'deploy_container': 'mercury',
            'apply_config': 'davinci',
            'configure_network': 'sapper',
        }
        agent = action_to_agent.get(intent.action)
        if agent:
            return [{"agent": agent, "task": intent.action, "depends_on": []}]
        return []

    async def submit_intent(self, intent: UserIntent, user_id: str) -> IntentResponse:
        """Accept a user intent, broadcast it, and dispatch tasks."""
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

        # Plan and dispatch tasks
        planned = self.plan_tasks(intent)
        dispatched = []

        for step in planned:
            task_id = str(uuid.uuid4())
            agent = step['agent']
            operation = step['task']

            task_body = {
                "operation": operation,
                "priority": "normal",
                "target_agent": agent,
                "parameters": intent.resource.model_dump(),
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

            # Track task state
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
            dispatched.append({
                "task_id": task_id,
                "agent": agent,
                "operation": operation,
            })
            logger.info(f"Task {task_id} dispatched to {agent}: {operation}")

        # Log to audit exchange
        audit_msg = make_envelope(
            message_type="INTENT_ACCEPTED",
            sender="conductor",
            body={
                "intent": intent.model_dump(),
                "user_id": user_id,
                "tasks_dispatched": len(dispatched),
            },
            correlation_id=correlation_id,
            intent_id=intent_id,
        )
        await publish(self.exchanges['agent.audit'], 'audit.intent', audit_msg)

        return IntentResponse(
            status="accepted",
            intent_id=intent_id,
            action=intent.action,
            planned_tasks=dispatched,
            message=f"Intent broadcast, {len(dispatched)} task(s) dispatched",
        )

    async def handle_event(self, event: dict):
        """Handle events from subagents."""
        msg_type = event.get('message_type')
        task_id = event.get('task_id')
        sender = event.get('sender')

        if msg_type == 'TASK_COMPLETED':
            ACTIVE_TASKS.labels(agent=sender).dec()
            await self._update_task(task_id, 'completed')
            logger.info(f"Task {task_id} completed by {sender}")

        elif msg_type == 'TASK_FAILED':
            ACTIVE_TASKS.labels(agent=sender).dec()
            error = event.get('body', {}).get('error', 'unknown')
            await self._update_task(task_id, 'failed', error=str(error))
            logger.warning(f"Task {task_id} failed ({sender}): {error}")

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

    async def _update_task(self, task_id: str, status: str, error: str = None):
        """Update task state in Redis."""
        if not task_id:
            return
        raw = await self.redis.get(f"task:{task_id}")
        if raw:
            data = json.loads(raw)
            data['status'] = status
            if error:
                data['error'] = error
            data['updated_at'] = datetime.now(timezone.utc).isoformat()
            await self.redis.setex(f"task:{task_id}", 3600, json.dumps(data))

    # ==================== LLM CHAT ====================

    def _build_system_prompt(self) -> str:
        """Build a system prompt describing available agents and actions."""
        agents_desc = []
        for sa in self.config.get('agents', {}).get('subagents', []):
            caps = ', '.join(sa.get('capabilities', []))
            agents_desc.append(f"- {sa['name']}: {caps}")

        routes = list(self.task_routing.keys())

        return f"""You are the Conductor, an AI orchestrator for the CyberFlight Lab infrastructure.
Your job is to translate natural language requests into structured intent JSON.

AVAILABLE AGENTS:
{chr(10).join(agents_desc)}

KNOWN ACTIONS (taskRouting):
{', '.join(routes)}

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
1. If the user's request maps to a known action, use it. Otherwise, pick the closest match or suggest a new action name.
2. Always include "approver": "ron" unless the user specifies otherwise.
3. If the request is ambiguous, ask a clarifying question instead of guessing. Prefix your reply with "CLARIFY:" when asking.
4. If you can form an intent, respond with ONLY the JSON block wrapped in ```json``` fences. Add a one-line summary BEFORE the JSON.
5. For multi-step workflows, use the most appropriate single top-level action. The Conductor will decompose it via taskRouting.
6. Keep responses concise — you are an infrastructure operator, not a chatbot."""

    async def chat(self, conversation_id: str, user_message: str) -> dict:
        """Process a chat message through Ollama and return a response with optional plan."""
        ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        ollama_model = os.getenv('OLLAMA_MODEL', 'qwen3:8b-nothink')

        # Load or create conversation history
        history_key = f"chat:{conversation_id}"
        raw_history = await self.redis.get(history_key)
        history = json.loads(raw_history) if raw_history else []

        # Append user message
        history.append({"role": "user", "content": user_message})

        # Build messages for Ollama
        messages = [{"role": "system", "content": self._build_system_prompt()}] + history

        # Call Ollama chat API
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f'{ollama_url}/api/chat', json={
                    'model': ollama_model,
                    'messages': messages,
                    'stream': False,
                })
                if resp.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"Ollama returned {resp.status_code}")
                llm_reply = resp.json().get('message', {}).get('content', '')
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Cannot reach Ollama LLM service")

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
        return await self.submit_intent(intent, user_id)

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
    version="0.2.0",
    lifespan=lifespan,
)

# Mount Prometheus metrics at /metrics
metrics_app = make_asgi_app(registry=METRICS_REGISTRY)
app.mount("/metrics", metrics_app)


# ==================== ENDPOINTS ====================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "conductor",
        "version": "0.2.0",
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
