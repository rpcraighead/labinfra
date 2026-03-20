# Scribe — Documentation & Audit Logging Agent
# Watches task completions/failures and writes to Postgres audit trail.
# Optionally uses Ollama to generate human-readable summaries.

import os
import json
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import aio_pika
import httpx
import psycopg
from base import BaseAgent

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)


class ScribeAgent(BaseAgent):
    def __init__(self):
        super().__init__('scribe', port=8006)
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://auditlog@postgres:5432/swarm_audit')
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://ollama:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.2:1b')
        self.ollama_available = False
        self.db_conn = None

    async def connect(self):
        await super().connect()

        # Connect to audit database
        try:
            self.db_conn = await psycopg.AsyncConnection.connect(self.db_url)
            await self.db_conn.set_autocommit(True)
            self.logger.info("Scribe connected to audit database")
        except Exception as e:
            self.logger.warning(f"Audit DB not available ({e}) — logging to stdout only")
            self.db_conn = None

        # Subscribe to event exchange for task completions and failures
        event_exchange = await self.channel.declare_exchange(
            'agent.event', aio_pika.ExchangeType.TOPIC, durable=True
        )
        event_queue = await self.channel.declare_queue('scribe.events', durable=True)
        await event_queue.bind(event_exchange, routing_key='agent.event.task.completed')
        await event_queue.bind(event_exchange, routing_key='agent.event.task.failed')

        # Also subscribe to alerts
        alert_exchange = await self.channel.declare_exchange(
            'agent.alert', aio_pika.ExchangeType.TOPIC, durable=True
        )
        await event_queue.bind(alert_exchange, routing_key='agent.alert.#')

        await event_queue.consume(self._on_event)
        self.logger.info("Scribe subscribed to task completions, failures, and alerts")

        # Check Ollama
        await self._check_ollama()

    async def _check_ollama(self):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f'{self.ollama_url}/api/tags')
                if resp.status_code == 200:
                    self.ollama_available = True
                    self.logger.info("Ollama available for summary generation")
                    return
        except Exception:
            pass
        self.ollama_available = False
        self.logger.info("Ollama not available — writing structured logs only")

    async def _on_event(self, message: aio_pika.IncomingMessage):
        """Log events to audit database and optionally generate summaries."""
        async with message.process():
            msg = json.loads(message.body)
            msg_type = msg.get('message_type', '')
            body = msg.get('body', {})
            agent = body.get('agent', msg.get('sender', 'unknown'))
            action = body.get('action', 'unknown')
            task_id = msg.get('task_id', 'unknown')
            intent_id = msg.get('intent_id', 'unknown')
            status = body.get('status', 'unknown')

            # Build log entry
            entry = {
                'timestamp': msg.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'message_type': msg_type,
                'agent': agent,
                'action': action,
                'task_id': task_id,
                'intent_id': intent_id,
                'status': status,
            }

            if msg_type == 'TASK_COMPLETED':
                result = body.get('result', {})
                entry['result_summary'] = self._summarize_result(result)
                # Enrich with LLM summary if available
                llm_summary = await self._llm_summarize(agent, action, result)
                if llm_summary:
                    entry['llm_summary'] = llm_summary
                self.logger.info(
                    f"SCRIBE: {agent} completed {action} — {entry['result_summary']}"
                )
                if llm_summary:
                    self.logger.info(f"SCRIBE LLM: {llm_summary}")
            elif msg_type == 'TASK_FAILED':
                error = body.get('error', {})
                entry['error'] = error
                self.logger.warning(
                    f"SCRIBE: {agent} FAILED {action} — {error.get('code')}: {error.get('message')}"
                )
            elif msg_type == 'ANOMALY_DETECTED':
                kind = body.get('kind', 'unknown')
                details = body.get('details', {})
                entry['anomaly_kind'] = kind
                entry['anomaly_details'] = details
                self.logger.warning(f"SCRIBE: ANOMALY [{kind}] — {details}")
                # Email the anomaly audit entry
                await self.send_email(
                    f"Audit: Anomaly {kind} recorded",
                    f"Anomaly '{kind}' has been logged to the audit database.\n\n"
                    f"Details:\n{json.dumps(details, indent=2)}",
                )
            else:
                self.logger.info(f"SCRIBE: {msg_type} from {agent}")

            # Write to audit DB
            await self._write_audit(entry)

    async def _llm_summarize(self, agent: str, action: str, result: dict) -> str:
        """Ask Ollama for a natural language summary of the task result."""
        if not self.ollama_available or not result:
            return ""
        prompt = (
            f"You are an infrastructure documentation agent. Write a concise 1-2 sentence "
            f"log entry for this completed task.\n"
            f"Agent: {agent}\nAction: {action}\n"
            f"Result: {json.dumps(result, default=str)[:1000]}\n"
            f"Write only the log entry, no preamble."
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f'{self.ollama_url}/api/generate', json={
                    'model': self.ollama_model, 'prompt': prompt, 'stream': False,
                })
                if resp.status_code == 200:
                    text = resp.json().get('response', '')
                    # Strip <think>...</think> tags from models that emit them
                    import re
                    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
                    return text
        except Exception as e:
            self.logger.warning(f"Ollama summary failed: {e}")
        return ""

    def _summarize_result(self, result: dict) -> str:
        """Generate a brief summary of the task result."""
        if not result:
            return "no data returned"

        # Common patterns
        if 'vms' in result:
            count = len(result['vms'])
            running = sum(1 for v in result['vms'] if v.get('status') == 'running')
            return f"{count} VMs ({running} running)"
        if 'nodes' in result:
            count = len(result['nodes'])
            online = sum(1 for n in result['nodes'] if n.get('status') == 'online')
            return f"{count} nodes ({online} online)"
        if 'cluster_nodes' in result:
            return (f"{result['cluster_nodes']} nodes, "
                    f"{result.get('running_vms', 0)} running / "
                    f"{result.get('stopped_vms', 0)} stopped VMs")
        if 'vmid' in result:
            return f"VM {result['vmid']} — {result.get('status', result.get('message', ''))}"
        if 'status' in result:
            return str(result['status'])

        keys = list(result.keys())[:5]
        return f"result keys: {', '.join(keys)}"

    async def _write_audit(self, entry: dict):
        """Write an audit entry to Postgres."""
        if not self.db_conn:
            return
        try:
            import uuid
            async with self.db_conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO agent_events
                       (event_id, event_type, sender, task_id, intent_id, body, created_at)
                       VALUES (%s, %s, %s, %s::uuid, %s::uuid, %s, NOW())""",
                    (
                        str(uuid.uuid4()),
                        entry.get('message_type', ''),
                        entry.get('agent', ''),
                        entry.get('task_id') if entry.get('task_id', 'unknown') != 'unknown' else None,
                        entry.get('intent_id') if entry.get('intent_id', 'unknown') != 'unknown' else None,
                        json.dumps(entry),
                    )
                )
        except Exception as e:
            self.logger.error(f"Audit write failed: {e}")

    async def handle_task(self, task_id: str, operation: str, params: dict, raw_msg: dict) -> dict:
        """Scribe can respond to audit queries."""
        if operation == 'recent_events':
            limit = params.get('limit', 20)
            return await self._query_recent(limit)
        raise ValueError(f"Unknown operation: {operation}")

    async def _query_recent(self, limit: int = 20) -> dict:
        if not self.db_conn:
            return {'error': 'database not connected'}
        try:
            async with self.db_conn.cursor() as cur:
                await cur.execute(
                    "SELECT event_type, sender, task_id, body, created_at "
                    "FROM agent_events ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                )
                rows = await cur.fetchall()
                return {
                    'events': [
                        {
                            'event_type': r[0], 'agent': r[1], 'task_id': str(r[2]) if r[2] else None,
                            'data': r[3], 'timestamp': r[4].isoformat() if r[4] else None,
                        }
                        for r in rows
                    ]
                }
        except Exception as e:
            return {'error': str(e)}

    async def disconnect(self):
        if self.db_conn:
            await self.db_conn.close()
        await super().disconnect()


agent = ScribeAgent()
app = agent.create_app()

if __name__ == '__main__':
    agent.run()
