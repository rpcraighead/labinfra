# Monitor — Observability & Anomaly Detection Agent
# Watches all task events, tracks timing/success rates, raises alerts.

import os
import json
import logging
import time
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import aio_pika
import httpx
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, make_asgi_app
from base import BaseAgent, make_envelope

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

# Prometheus metrics
METRICS = CollectorRegistry()
EVENTS_SEEN = Counter('monitor_events_total', 'Events observed', ['event_type'], registry=METRICS)
TASK_DURATION = Histogram('monitor_task_duration_seconds', 'Task execution time',
                          ['agent', 'operation'], registry=METRICS,
                          buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300])
ANOMALIES_RAISED = Counter('monitor_anomalies_total', 'Anomalies detected', ['kind'], registry=METRICS)
AGENTS_HEALTHY = Gauge('monitor_agents_healthy', 'Agent health status', ['agent'], registry=METRICS)


class MonitorAgent(BaseAgent):
    def __init__(self):
        super().__init__('monitor', port=8005)
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.2:1b')
        self.ollama_available = False

        # Tracking state
        self.task_starts = {}  # task_id -> timestamp
        self.agent_stats = defaultdict(lambda: {'completed': 0, 'failed': 0, 'total_time': 0.0})
        self.alert_exchange = None

        # Anomaly thresholds
        self.max_task_seconds = int(os.getenv('MAX_TASK_SECONDS', '120'))
        self.failure_rate_threshold = float(os.getenv('FAILURE_RATE_THRESHOLD', '0.5'))

    async def connect(self):
        await super().connect()

        # Subscribe to event exchange for all task events
        self.alert_exchange = await self.channel.declare_exchange(
            'agent.alert', aio_pika.ExchangeType.TOPIC, durable=True
        )
        event_exchange = await self.channel.declare_exchange(
            'agent.event', aio_pika.ExchangeType.TOPIC, durable=True
        )
        event_queue = await self.channel.declare_queue('monitor.events', durable=True)
        await event_queue.bind(event_exchange, routing_key='agent.event.#')
        await event_queue.consume(self._on_event)
        self.logger.info("Monitor subscribed to agent.event.# for observation")

        # Check Ollama
        await self._check_ollama()

    async def _check_ollama(self):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f'{self.ollama_url}/api/tags')
                if resp.status_code == 200:
                    self.ollama_available = True
                    models = [m['name'] for m in resp.json().get('models', [])]
                    self.logger.info(f"Ollama available, models: {models}")
                    return
        except Exception:
            pass
        self.ollama_available = False
        self.logger.info("Ollama not available — using rule-based anomaly detection only")

    async def _on_event(self, message: aio_pika.IncomingMessage):
        """Process task lifecycle events."""
        async with message.process():
            msg = json.loads(message.body)
            msg_type = msg.get('message_type', '')
            body = msg.get('body', {})
            task_id = msg.get('task_id', 'unknown')
            agent = body.get('agent', 'unknown')
            action = body.get('action', 'unknown')

            EVENTS_SEEN.labels(event_type=msg_type).inc()

            if msg_type == 'TASK_STARTED':
                self.task_starts[task_id] = time.monotonic()
                AGENTS_HEALTHY.labels(agent=agent).set(1)
                self.logger.info(f"OBSERVE: {agent} started {action} (task={task_id})")

            elif msg_type == 'TASK_COMPLETED':
                duration = self._record_duration(task_id, agent, action)
                self.agent_stats[agent]['completed'] += 1
                self.logger.info(
                    f"OBSERVE: {agent} completed {action} in {duration:.2f}s (task={task_id})"
                )
                # Check for slow tasks
                if duration > self.max_task_seconds:
                    await self._raise_anomaly('slow_task', {
                        'agent': agent, 'action': action, 'task_id': task_id,
                        'duration_seconds': round(duration, 2),
                        'threshold_seconds': self.max_task_seconds,
                    })

            elif msg_type == 'TASK_FAILED':
                duration = self._record_duration(task_id, agent, action)
                self.agent_stats[agent]['failed'] += 1
                error = body.get('error', {})
                self.logger.warning(
                    f"OBSERVE: {agent} FAILED {action} — {error.get('code')}: "
                    f"{error.get('message')} (task={task_id})"
                )
                # Check failure rate
                stats = self.agent_stats[agent]
                total = stats['completed'] + stats['failed']
                if total >= 3:
                    rate = stats['failed'] / total
                    if rate >= self.failure_rate_threshold:
                        await self._raise_anomaly('high_failure_rate', {
                            'agent': agent, 'failure_rate': round(rate, 2),
                            'completed': stats['completed'], 'failed': stats['failed'],
                        })

    def _record_duration(self, task_id: str, agent: str, action: str) -> float:
        start = self.task_starts.pop(task_id, None)
        if start is None:
            return 0.0
        duration = time.monotonic() - start
        TASK_DURATION.labels(agent=agent, operation=action).observe(duration)
        self.agent_stats[agent]['total_time'] += duration
        return duration

    async def _llm_analyze(self, kind: str, details: dict) -> str:
        """Ask Ollama for a brief anomaly analysis."""
        if not self.ollama_available:
            return ""
        prompt = (
            f"You are an infrastructure monitoring agent. Analyze this anomaly briefly (2-3 sentences).\n"
            f"Anomaly type: {kind}\nDetails: {json.dumps(details)}\n"
            f"What is the likely cause and recommended action?"
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f'{self.ollama_url}/api/generate', json={
                    'model': self.ollama_model, 'prompt': prompt, 'stream': False,
                })
                if resp.status_code == 200:
                    import re
                    analysis = resp.json().get('response', '')
                    analysis = re.sub(r'<think>.*?</think>', '', analysis, flags=re.DOTALL).strip()
                    self.logger.info(f"LLM analysis [{kind}]: {analysis}")
                    return analysis
        except Exception as e:
            self.logger.warning(f"Ollama analysis failed: {e}")
        return ""

    async def _raise_anomaly(self, kind: str, details: dict):
        """Publish an anomaly alert, optionally enriched with LLM analysis."""
        ANOMALIES_RAISED.labels(kind=kind).inc()
        self.logger.warning(f"ANOMALY [{kind}]: {details}")

        # Enrich with LLM analysis if available
        llm_analysis = await self._llm_analyze(kind, details)
        if llm_analysis:
            details['llm_analysis'] = llm_analysis

        alert_msg = make_envelope(
            message_type='ANOMALY_DETECTED',
            sender='monitor',
            body={'kind': kind, 'details': details},
        )
        await self.alert_exchange.publish(
            aio_pika.Message(
                body=json.dumps(alert_msg).encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=f'agent.alert.anomaly.{kind}',
        )

        # Email notification
        agent_name = details.get('agent', 'unknown')
        analysis = details.get('llm_analysis', '')
        body_text = (
            f"Anomaly Type: {kind}\n"
            f"Agent: {agent_name}\n"
            f"Details: {json.dumps(details, indent=2)}\n"
        )
        if analysis:
            body_text += f"\nLLM Analysis:\n{analysis}\n"
        await self.send_email(f"Anomaly detected: {kind} on {agent_name}", body_text)

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        """Monitor can also respond to direct queries."""
        if operation == 'agent_stats':
            return {
                'agents': {
                    name: {
                        'completed': s['completed'],
                        'failed': s['failed'],
                        'avg_duration': round(s['total_time'] / max(s['completed'] + s['failed'], 1), 2),
                    }
                    for name, s in self.agent_stats.items()
                }
            }
        raise ValueError(f"Unknown operation: {operation}")

    def create_app(self):
        app = super().create_app()
        metrics_app = make_asgi_app(registry=METRICS)
        app.mount("/metrics", metrics_app)

        @app.get("/stats")
        async def stats():
            return {
                name: {
                    'completed': s['completed'],
                    'failed': s['failed'],
                    'avg_duration': round(s['total_time'] / max(s['completed'] + s['failed'], 1), 2),
                }
                for name, s in self.agent_stats.items()
            }

        return app


agent = MonitorAgent()
app = agent.create_app()

if __name__ == '__main__':
    agent.run()
