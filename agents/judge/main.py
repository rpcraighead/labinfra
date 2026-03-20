# Judge — Arbitration & Constraint Enforcement Agent
# Watches for anomalies and constraint violations, decides on escalation/halt.

import os
import json
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import aio_pika
import httpx
from base import BaseAgent, make_envelope

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


class JudgeAgent(BaseAgent):
    def __init__(self):
        super().__init__('judge', port=8007)
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.2:1b')
        self.ollama_available = False
        self.event_exchange = None
        self.alert_exchange = None

        # Verdicts log
        self.verdicts = []

    async def connect(self):
        await super().connect()

        self.event_exchange = await self.channel.declare_exchange(
            'agent.event', aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.alert_exchange = await self.channel.declare_exchange(
            'agent.alert', aio_pika.ExchangeType.TOPIC, durable=True
        )

        # Subscribe to anomaly and constraint alerts
        judge_queue = await self.channel.declare_queue('judge.alerts', durable=True)
        await judge_queue.bind(self.alert_exchange, routing_key='agent.alert.anomaly.#')
        await judge_queue.bind(self.alert_exchange, routing_key='agent.alert.constraint.#')
        await judge_queue.consume(self._on_alert)
        self.logger.info("Judge subscribed to anomaly and constraint alerts")

        # Check Ollama
        await self._check_ollama()

    async def _check_ollama(self):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f'{self.ollama_url}/api/tags')
                if resp.status_code == 200:
                    self.ollama_available = True
                    self.logger.info("Ollama available for verdict reasoning")
                    return
        except Exception:
            pass
        self.ollama_available = False
        self.logger.info("Ollama not available — using rule-based verdicts only")

    async def _on_alert(self, message: aio_pika.IncomingMessage):
        """Evaluate alerts and issue verdicts."""
        async with message.process():
            msg = json.loads(message.body)
            msg_type = msg.get('message_type', '')
            body = msg.get('body', {})
            kind = body.get('kind', 'unknown')
            details = body.get('details', {})

            self.logger.info(f"JUDGE: evaluating {msg_type} — {kind}")

            verdict = self._evaluate(kind, details)

            # Enrich with LLM reasoning if available
            llm_reasoning = await self._llm_reason(kind, details, verdict)
            if llm_reasoning:
                verdict['llm_reasoning'] = llm_reasoning

            self.verdicts.append(verdict)

            # Keep only last 100 verdicts
            if len(self.verdicts) > 100:
                self.verdicts = self.verdicts[-100:]

            # Publish verdict as event
            verdict_msg = make_envelope(
                message_type='JUDGE_VERDICT',
                sender='judge',
                body=verdict,
                correlation_id=msg.get('correlation_id'),
                intent_id=msg.get('intent_id'),
            )
            await self.event_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(verdict_msg).encode(),
                    content_type='application/json',
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key='agent.event.judge.verdict',
            )
            self.logger.info(f"JUDGE VERDICT: {verdict['decision']} — {verdict['reason']}")

            # Email on halt or quarantine verdicts
            if verdict['decision'] in ('halt', 'quarantine'):
                body_text = (
                    f"Decision: {verdict['decision'].upper()}\n"
                    f"Severity: {verdict['severity']}\n"
                    f"Reason: {verdict['reason']}\n"
                    f"Recommended Action: {verdict.get('recommended_action', 'N/A')}\n"
                )
                if verdict.get('llm_reasoning'):
                    body_text += f"\nLLM Reasoning:\n{verdict['llm_reasoning']}\n"
                await self.send_email(
                    f"VERDICT: {verdict['decision'].upper()} — {kind}",
                    body_text,
                )

    async def _llm_reason(self, kind: str, details: dict, verdict: dict) -> str:
        """Ask Ollama for reasoning about the verdict."""
        if not self.ollama_available:
            return ""
        prompt = (
            f"You are a security arbitration judge for an infrastructure management system. "
            f"An anomaly was detected and a preliminary verdict was issued. "
            f"Provide a brief 2-3 sentence justification.\n"
            f"Anomaly: {kind}\nDetails: {json.dumps(details)}\n"
            f"Preliminary verdict: {verdict['decision']} ({verdict['severity']})\n"
            f"Write only the justification, no preamble."
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f'{self.ollama_url}/api/generate', json={
                    'model': self.ollama_model, 'prompt': prompt, 'stream': False,
                })
                if resp.status_code == 200:
                    import re
                    reasoning = resp.json().get('response', '')
                    reasoning = re.sub(r'<think>.*?</think>', '', reasoning, flags=re.DOTALL).strip()
                    self.logger.info(f"JUDGE LLM: {reasoning}")
                    return reasoning
        except Exception as e:
            self.logger.warning(f"Ollama reasoning failed: {e}")
        return ""

    def _evaluate(self, kind: str, details: dict) -> dict:
        """Rule-based evaluation of anomalies. Returns a verdict."""
        now = datetime.now(timezone.utc).isoformat()

        if kind == 'slow_task':
            duration = details.get('duration_seconds', 0)
            threshold = details.get('threshold_seconds', 120)
            if duration > threshold * 3:
                return {
                    'kind': kind, 'decision': 'halt',
                    'severity': 'critical',
                    'reason': f"Task took {duration}s (3x threshold of {threshold}s) — possible hang",
                    'recommended_action': 'kill_task',
                    'timestamp': now,
                }
            return {
                'kind': kind, 'decision': 'warn',
                'severity': 'warning',
                'reason': f"Task took {duration}s (threshold {threshold}s) — slow but tolerable",
                'recommended_action': 'log_and_continue',
                'timestamp': now,
            }

        if kind == 'high_failure_rate':
            rate = details.get('failure_rate', 0)
            agent = details.get('agent', 'unknown')
            if rate >= 0.8:
                return {
                    'kind': kind, 'decision': 'quarantine',
                    'severity': 'critical',
                    'reason': f"Agent {agent} has {rate*100:.0f}% failure rate — quarantine recommended",
                    'recommended_action': 'disable_agent',
                    'timestamp': now,
                }
            return {
                'kind': kind, 'decision': 'warn',
                'severity': 'warning',
                'reason': f"Agent {agent} has {rate*100:.0f}% failure rate — monitoring",
                'recommended_action': 'increase_monitoring',
                'timestamp': now,
            }

        if kind == 'constraint_violated':
            constraint = details.get('constraint', 'unknown')
            return {
                'kind': kind, 'decision': 'halt',
                'severity': 'critical',
                'reason': f"Constraint '{constraint}' violated — halting execution",
                'recommended_action': 'rollback_and_notify',
                'timestamp': now,
            }

        # Unknown anomaly type
        return {
            'kind': kind, 'decision': 'log',
            'severity': 'info',
            'reason': f"Unknown anomaly type '{kind}' — logged for review",
            'recommended_action': 'manual_review',
            'timestamp': now,
        }

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        if operation == 'recent_verdicts':
            limit = params.get('limit', 10)
            return {'verdicts': self.verdicts[-limit:]}
        raise ValueError(f"Unknown operation: {operation}")

    def create_app(self):
        app = super().create_app()

        @app.get("/verdicts")
        async def verdicts():
            return {'verdicts': self.verdicts[-20:]}

        return app


agent = JudgeAgent()
app = agent.create_app()

if __name__ == '__main__':
    agent.run()
