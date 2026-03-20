# Base Agent — shared plumbing for all swarm agents
# Handles RabbitMQ connection, task consumption, event publishing, health endpoint, and email.

import os
import json
import uuid
import asyncio
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Awaitable
from contextlib import asynccontextmanager

import aiosmtplib
import aio_pika
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def make_envelope(
    message_type: str,
    sender: str,
    body: Dict[str, Any],
    correlation_id: str = None,
    intent_id: str = None,
    recipient: str = None,
    task_id: str = None,
) -> Dict[str, Any]:
    msg = {
        "message_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_type": message_type,
        "sender": sender,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "intent_id": intent_id or str(uuid.uuid4()),
        "body": body,
    }
    if recipient:
        msg["recipient"] = recipient
    if task_id:
        msg["task_id"] = task_id
    return msg


class BaseAgent:
    """
    Base class for swarm agents. Subclass and implement handle_task().

    Usage:
        class MyAgent(BaseAgent):
            async def handle_task(self, task_id, operation, params, msg):
                # do work
                return {"result": "done"}

        agent = MyAgent("myagent", port=8001)
        agent.run()
    """

    def __init__(self, name: str, port: int = 8080):
        self.name = name
        self.port = port
        self.broker_url = os.getenv('INTENT_BROKER_URL')

        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.task_exchange: Optional[aio_pika.Exchange] = None
        self.event_exchange: Optional[aio_pika.Exchange] = None
        self.intent_exchange: Optional[aio_pika.Exchange] = None

        # SMTP configuration
        self.smtp_host = os.getenv('SMTP_HOST', '')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.email_from = os.getenv('AGENT_EMAIL', f'{name}@rpc-cyberflight.com')
        self.notify_to = os.getenv('NOTIFY_EMAIL', '')
        self.email_enabled = bool(self.smtp_host and self.notify_to)

        self.logger = logging.getLogger(name)

    async def connect(self):
        """Connect to RabbitMQ and declare exchanges/queues."""
        self.connection = await aio_pika.connect_robust(self.broker_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=3)

        self.task_exchange = await self.channel.declare_exchange(
            'agent.task', aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.event_exchange = await self.channel.declare_exchange(
            'agent.event', aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.intent_exchange = await self.channel.declare_exchange(
            'agent.intent', aio_pika.ExchangeType.FANOUT, durable=True
        )

        # Bind task queue
        task_queue = await self.channel.declare_queue(
            f'{self.name}.tasks', durable=True
        )
        await task_queue.bind(self.task_exchange, routing_key=f'{self.name}.*')
        await task_queue.consume(self._on_task)

        # Bind intent queue (for visibility)
        intent_queue = await self.channel.declare_queue(
            f'{self.name}.intents', durable=True
        )
        await intent_queue.bind(self.intent_exchange)
        await intent_queue.consume(self._on_intent)

        self.logger.info(f"{self.name} connected to RabbitMQ, listening on {self.name}.tasks")

    async def _on_task(self, message: aio_pika.IncomingMessage):
        """Receive a task, run handle_task(), publish events."""
        async with message.process():
            msg = json.loads(message.body)
            task_id = msg.get('task_id', 'unknown')
            operation = msg.get('body', {}).get('operation', 'unknown')
            params = msg.get('body', {}).get('parameters', {})
            correlation_id = msg.get('correlation_id')
            intent_id = msg.get('intent_id')

            self.logger.info(f"TASK received: {operation} (task_id={task_id})")

            # Publish TASK_STARTED
            await self._publish_event('TASK_STARTED', {
                "status": "started", "agent": self.name, "action": operation,
            }, task_id=task_id, correlation_id=correlation_id, intent_id=intent_id)

            try:
                result = await self.handle_task(task_id, operation, params, msg)

                # Publish TASK_COMPLETED
                await self._publish_event('TASK_COMPLETED', {
                    "status": "completed", "agent": self.name,
                    "action": operation, "result": result or {},
                }, task_id=task_id, correlation_id=correlation_id, intent_id=intent_id)
                self.logger.info(f"TASK completed: {operation} (task_id={task_id})")

            except Exception as e:
                self.logger.error(f"TASK failed: {operation} — {e}", exc_info=True)
                await self._publish_event('TASK_FAILED', {
                    "status": "failed", "agent": self.name,
                    "action": operation,
                    "error": {"code": type(e).__name__, "message": str(e)},
                }, task_id=task_id, correlation_id=correlation_id, intent_id=intent_id)

    async def _on_intent(self, message: aio_pika.IncomingMessage):
        """Log intents for visibility."""
        async with message.process():
            msg = json.loads(message.body)
            action = msg.get('body', {}).get('action', '?')
            intent_id = msg.get('intent_id', '?')
            self.logger.info(f"INTENT observed: {action} (intent_id={intent_id})")

    async def _publish_event(self, message_type: str, body: dict, **kwargs):
        """Publish an event to the agent.event exchange."""
        envelope = make_envelope(
            message_type=message_type,
            sender=self.name,
            body=body,
            **kwargs,
        )
        await self.event_exchange.publish(
            aio_pika.Message(
                body=json.dumps(envelope).encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=f'agent.event.task.{body.get("status", "unknown")}',
        )

    async def send_email(self, subject: str, body: str, html: bool = False, to: str = None):
        """Send an email notification. Falls back silently if SMTP is not configured."""
        if not self.email_enabled:
            return
        recipient = to or self.notify_to
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_from
            msg['To'] = recipient
            msg['Subject'] = f"[{self.name.upper()}] {subject}"
            msg.attach(MIMEText(body, 'html' if html else 'plain'))

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user or None,
                password=self.smtp_password or None,
                start_tls=self.smtp_port == 587,
            )
            self.logger.info(f"Email sent to {recipient}: {subject}")
        except Exception as e:
            self.logger.warning(f"Email send failed: {e}")

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        """Override this in subclasses. Return a result dict or raise on failure."""
        raise NotImplementedError(f"{self.name} has no handler for {operation}")

    async def disconnect(self):
        if self.connection:
            await self.connection.close()

    def create_app(self) -> FastAPI:
        """Create a FastAPI app with health endpoint and lifespan management."""
        agent = self

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await agent.connect()
            yield
            await agent.disconnect()

        app = FastAPI(title=f"{self.name} agent", lifespan=lifespan)

        @app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "agent": agent.name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return app

    def run(self):
        """Start the agent with uvicorn."""
        import uvicorn
        app = self.create_app()
        uvicorn.run(app, host="0.0.0.0", port=self.port)
