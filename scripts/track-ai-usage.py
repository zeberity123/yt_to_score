"""Read-only job token and account quota snapshots; never starts an AI turn.

Account quota changes cannot be attributed solely to a job when other Codex work
is running. A monitor started mid-job cannot reconstruct the job's initial quota.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai_score.providers import cli_environment, codex_executable


def account_limits():
    process = subprocess.Popen([codex_executable(), 'app-server', '--stdio'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', env=cli_environment(),
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    messages = queue.Queue()
    def read():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=read, daemon=True).start()
    def send(value):
        process.stdin.write(json.dumps(value)+'\n')
        process.stdin.flush()
    def response(identifier):
        deadline = time.monotonic()+25
        while time.monotonic() < deadline:
            value = messages.get(timeout=max(.1, deadline-time.monotonic()))
            if value.get('id') == identifier:
                if 'error' in value:
                    raise RuntimeError(value['error'].get('message', 'Account status unavailable'))
                return value['result']
        raise TimeoutError('Account status timed out')
    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'video_score_usage_inspector', 'version': '0.1.0'}}})
        response(1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        result = response(2)
        buckets = result.get('rateLimitsByLimitId') or {'codex': result.get('rateLimits')}
        # Keep only quota metadata, not account identity, credentials or credit IDs.
        return {key: {field: value.get(field) for field in
                      ('limitId', 'limitName', 'primary', 'secondary', 'planType')}
                for key, value in buckets.items() if value}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def load(path):
    # The running job can replace a JSON file during this read. Retry next sample.
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def snapshot(job):
    value = {'observed_at': datetime.now(timezone.utc).isoformat(), 'job': job.name,
             'job_usage': load(job/'responses/usage-latest.json'),
             'quota_scope': 'Entire signed-in Codex account; not this video alone',
             'job_start_quota': None}
    checkpoint = load(job/'checkpoint.json') or {}
    value['saved_bars'] = len(checkpoint.get('bars', []))
    value['preparation'] = checkpoint.get('preparation')
    value['pipeline_finished'] = (job/'review.json').exists()
    value['cancelled_draft_saved'] = (job/'cancelled-draft.aiscore.json').exists()
    try:
        value['account_limits'] = account_limits()
    except Exception as exc:
        value['account_status_error'] = str(exc) or type(exc).__name__
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--max-minutes', type=float, default=120)
    args = parser.parse_args()
    if not (args.job/'responses').is_dir():
        parser.error('Job response folder does not exist')
    if args.interval < 30 or args.max_minutes <= 0:
        parser.error('Use an interval of at least 30 seconds and a positive duration')
    args.output.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic()+args.max_minutes*60
    while True:
        value = snapshot(args.job)
        done = (not args.watch or value['pipeline_finished'] or value['cancelled_draft_saved']
                or time.monotonic() >= deadline)
        value['monitor_finished'] = done
        with (args.output/'snapshots.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False)+'\n')
        temporary = args.output/'latest.tmp'
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(args.output/'latest.json')
        if done:
            return
        time.sleep(min(args.interval, max(0, deadline-time.monotonic())))


if __name__ == '__main__':
    main()
