"""Bounded vision requests, reusable response cache, and explicit usage accounting."""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .contracts import validate_schema
from .prompts import VERSION

PROVIDERS = {
    'OpenAI': {'model': 'gpt-6-luna', 'url': 'https://api.openai.com/v1/responses', 'rates': (.10, .01, .50)},
    'DeepSeek': {'model': 'deepseek-flash', 'url': 'https://api.deepseek.com/chat/completions', 'rates': (.30, .006, 1.20)},
    'Anthropic': {'model': 'claude-haiku-4-5', 'url': 'https://api.anthropic.com/v1/messages', 'rates': (1., .10, 5.)},
    'Codex': {'model': 'gpt-6-astra', 'rates': (0, 0, 0)},
    'Claude CLI': {'model': 'sonnet', 'rates': (0, 0, 0)},
}
RATES = {'gpt-6-astra': (10., 1., 50.), 'gpt-6-sol': (2., .2, 10.),
         'gpt-6-luna': (.10, .01, .50), 'deepseek-flash': (.30, .006, 1.20),
         'claude-haiku-4-5': (1., .10, 5.)}


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled('Cancelled. Completed requests are cached for resuming.')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def codex_executable():
    direct = shutil.which('codex.exe')
    if direct:
        return direct
    roots = [Path(os.environ.get('APPDATA', ''))/'npm', Path.home()/'.npm-global']
    cmd = shutil.which('codex.cmd') or shutil.which('codex')
    if cmd:
        roots.insert(0, Path(cmd).parent)
    for root in roots:
        package = root/'node_modules'/'@openai'/'codex'
        if package.is_dir():
            found = list(package.glob('**/codex.exe'))
            if found:
                return str(found[0])
    if cmd and not str(cmd).lower().endswith(('.cmd', '.ps1', '.bat')):
        return cmd
    raise RuntimeError('Codex CLI was not found. Install the official Codex CLI and run codex login with ChatGPT.')


def cli_environment():
    env = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
        env.pop(key, None)
    return env


def login_status():
    result = subprocess.run([codex_executable(), 'login', 'status'], capture_output=True,
                            timeout=30, env=cli_environment(),
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    status = (result.stdout+result.stderr).decode('utf-8', 'replace').strip()
    if result.returncode or 'chatgpt' not in status.lower():
        raise RuntimeError('Personal edition requires Codex CLI signed in with ChatGPT. Run codex login in a terminal. API-key login is not used by this edition.')
    return 'Signed in with ChatGPT. Requests consume your Codex subscription allowance.'


def claude_executable():
    path = shutil.which('claude.exe') or shutil.which('claude')
    if not path:
        candidate = Path.home()/'.local/bin/claude.exe'
        path = str(candidate) if candidate.exists() else None
    if not path or str(path).lower().endswith(('.cmd', '.bat', '.ps1')):
        raise RuntimeError('Install the native Claude Code CLI and sign in with your Claude subscription.')
    return path


def claude_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('ANTHROPIC_', 'CLAUDE_CODE_USE_', 'CLAUDE_CODE_OAUTH_TOKEN')):
            env.pop(key, None)
    return env


def claude_login_status():
    result = subprocess.run([claude_executable(), 'auth', 'status', '--json'], capture_output=True,
                            timeout=30, env=claude_environment(),
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        status = json.loads(result.stdout)
    except ValueError:
        status = {}
    if result.returncode or not status.get('loggedIn') or status.get('authMethod') != 'claude.ai':
        raise RuntimeError('Sign in to Claude Code with your Claude subscription using claude auth login. API authentication is not used for this connection.')
    return 'Claude subscription login found. Authentication is verified on extraction; account limits and extra-usage settings apply.'


class Client:
    def __init__(self, provider, model, key, folder, cancel=None, log=None, max_requests=100,
                 max_output=12000, budget=2.0):
        if provider not in PROVIDERS:
            raise ValueError('Unknown provider')
        self.provider, self.model, self.key = provider, model, key
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cancel = cancel or threading.Event()
        self.log = log or (lambda message: None)
        self.max_requests, self.max_output, self.budget = max_requests, max_output, budget
        self.usage = dict(requests=0, cache_hits=0, input_tokens=0, cached_input_tokens=0,
                          output_tokens=0, estimated_usd=0., subscription=provider in ('Codex', 'Claude CLI'))
        self.auth_checked = False
        self.gate = None

    def request(self, prompt, schema, images=()):
        if self.gate:
            with self.gate.request(self.cancel):
                return self._request(prompt, schema, images)
        return self._request(prompt, schema, images)

    def cache_path(self, prompt, schema, images):
        digest = hashlib.sha256(json.dumps([VERSION, self.provider, self.model, prompt, schema],
                                         sort_keys=True).encode())
        for path in images:
            digest.update(Path(path).read_bytes())
        return self.folder/(digest.hexdigest()+'.json')

    def cached_request(self, prompt, schema, images=()):
        """Read an exactly matching old response; never falls through to inference."""
        check_cancel(self.cancel)
        if self.gate:
            self.gate.wait(self.cancel)
        cache = self.cache_path(prompt, schema, images)
        if not cache.exists():
            return None
        value = json.loads(cache.read_text(encoding='utf-8'))['result']
        validate_schema(value, schema)
        self.usage['cache_hits'] += 1
        write_json(self.folder/'usage-latest.json', self.usage)
        return value

    def _request(self, prompt, schema, images=()):
        check_cancel(self.cancel)
        blobs = [Path(path).read_bytes() for path in images]
        digest = hashlib.sha256(json.dumps([VERSION, self.provider, self.model, prompt, schema],
                                         sort_keys=True).encode())
        for blob in blobs:
            digest.update(blob)
        cache = self.folder/(digest.hexdigest()+'.json')
        if cache.exists():
            value = json.loads(cache.read_text(encoding='utf-8'))['result']
            validate_schema(value, schema)
            self.usage['cache_hits'] += 1
            self.log('Reusing a completed AI response')
            return value
        if self.max_requests is not None and self.usage['requests'] >= self.max_requests:
            raise RuntimeError('Request limit reached. Resume with a higher request limit; completed work is cached.')
        if not self.usage['subscription']:
            if not self.key.strip():
                raise ValueError('Enter your provider API key. It stays in memory and is never saved.')
            rates = RATES.get(self.model)
            if not rates:
                raise ValueError('This model has no known price estimate. Choose a supported model.')
            # Conservative reservation, not a provider-enforced billing cap. Actual image
            # accounting varies. Stop before the next request if the estimate exceeds budget.
            estimated_input = len(prompt)/2+sum(16000 for _ in blobs)+len(json.dumps(schema))/2
            reservation = (estimated_input*rates[0]+self.max_output*rates[2])/1e6
            if self.budget is not None and self.usage['estimated_usd']+reservation > self.budget:
                raise RuntimeError('Estimated spend guard reached. Resume with a larger budget. This guard is not a provider billing cap.')
        self.usage['requests'] += 1
        try:
            if self.usage['subscription']:
                if not self.auth_checked:
                    self.log(login_status() if self.provider == 'Codex' else claude_login_status())
                    self.auth_checked = True
                value, usage = (self._codex(prompt, schema, images, digest.hexdigest()) if self.provider == 'Codex'
                                else self._claude(prompt, schema, blobs, digest.hexdigest()))
            else:
                value, usage = self._api(prompt, schema, blobs)
            self._record(usage)
            validate_schema(value, schema)
            write_json(cache, {'result': value, 'usage': usage})
            return value
        finally:
            write_json(self.folder/'usage-latest.json', self.usage)

    def _record(self, usage):
        total = int(usage.get('input_tokens', 0))
        cached = min(total, int(usage.get('cached_input_tokens', 0)))
        output = int(usage.get('output_tokens', 0))
        for key, value in [('input_tokens', total), ('cached_input_tokens', cached), ('output_tokens', output)]:
            self.usage[key] += value
        if not self.usage['subscription']:
            rates = RATES[self.model]
            self.usage['estimated_usd'] += ((total-cached)*rates[0]+cached*rates[1]+output*rates[2])/1e6

    def _claude(self, prompt, schema, blobs, identity):
        work = self.folder/'claude'/identity
        work.mkdir(parents=True, exist_ok=True)
        # Images are attached as messages, so the CLI needs no filesystem or shell tools.
        content = [{'type': 'text', 'text': prompt}]+[
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                        'data': base64.b64encode(blob).decode('ascii')}} for blob in blobs]
        payload = json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content}})+'\n'
        command = [claude_executable(), '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
                   '--model', self.model, '--json-schema', json.dumps(schema), '--no-session-persistence',
                   '--restricted', '--safe-mode', '--tools', '', '--disallowedTools', 'mcp__*',
                   '--strict-mcp-config', '--permission-prompts', 'none', '--max-turns', '3']
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        with (work/'output.json').open('wb') as output, (work/'stderr.txt').open('wb') as errors:
            process = subprocess.Popen(command, cwd=work, env=claude_environment(), stdin=subprocess.PIPE,
                                       stdout=output, stderr=errors, creationflags=flags)
            try:
                process.stdin.write(payload.encode('utf-8'))
                process.stdin.close()
                deadline = time.monotonic()+900
                while process.poll() is None:
                    if self.cancel.wait(.2):
                        raise Cancelled('Cancelled. The active CLI request may have consumed allowance.')
                    if time.monotonic() > deadline:
                        raise TimeoutError('Claude Code request timed out after 15 minutes.')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
        events = [json.loads(line) for line in (work/'output.json').read_text(encoding='utf-8').splitlines() if line.strip()]
        result = next((item for item in reversed(events) if item.get('type') == 'result'), {})
        if 'oauth' in str(result.get('result', '')).lower() or 'authenticate' in str(result.get('result', '')).lower():
            raise RuntimeError('Your Claude Code login has expired. Run "claude auth login" in a terminal, sign in with your subscription, then retry. No API fallback was used.')
        if process.returncode:
            raise RuntimeError('Claude Code request failed. Check the job diagnostics and your subscription login/limits.')
        u = result.get('usage', {})
        cached = u.get('cache_read_input_tokens', 0)
        usage = {'input_tokens': u.get('input_tokens', 0)+cached+u.get('cache_creation_input_tokens', 0),
                 'cached_input_tokens': cached, 'output_tokens': u.get('output_tokens', 0)}
        if result.get('is_error') or 'structured_output' not in result:
            self._record(usage)
            raise RuntimeError('Claude Code returned no complete structured score. Check the job diagnostics.')
        return result['structured_output'], usage

    def _codex(self, prompt, schema, images, identity):
        work = self.folder/'cli'/identity
        work.mkdir(parents=True, exist_ok=True)
        schema_path, result_path = work/'schema.json', work/'result.json'
        write_json(schema_path, schema)
        command = [codex_executable(), 'exec', '--ignore-user-config', '--ignore-rules',
                   '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                   '-C', str(work.resolve()), '--model', self.model,
                   '-c', 'model_reasoning_effort="high"', '-c', 'approval_policy="never"', '--json',
                   '--output-schema', str(schema_path.resolve()), '-o', str(result_path.resolve())]
        for image in images:
            command.extend(['--image', str(Path(image).resolve())])
        command.append('-')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        events_path = work/'events.jsonl'
        # Redirect to disk so a chatty process cannot block on a full stdout pipe.
        with events_path.open('wb') as events, (work/'stderr.txt').open('wb') as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=events, stderr=errors,
                                       env=cli_environment(), creationflags=flags)
            try:
                process.stdin.write(prompt.encode('utf-8'))
                process.stdin.close()
                deadline = time.monotonic()+900
                while process.poll() is None:
                    if self.cancel.wait(.2):
                        process.terminate()
                        raise Cancelled('Cancelled. The current request may have consumed subscription allowance.')
                    if time.monotonic() > deadline:
                        process.terminate()
                        raise TimeoutError('Codex did not finish within 15 minutes. Completed requests are cached.')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
        usage, failure = {}, ''
        for line in events_path.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') == 'turn.completed':
                usage = event.get('usage', {})
            if event.get('type') in ('error', 'turn.failed'):
                failure = str(event.get('message') or event.get('error', 'Codex request failed'))[:800]
        if process.returncode or not result_path.exists():
            raise RuntimeError(failure or 'Codex request failed. Check the job cli/stderr.txt diagnostics and your login/quota.')
        return json.loads(result_path.read_text(encoding='utf-8')), usage

    def _payload(self, prompt, schema, blobs):
        images = ['data:image/jpeg;base64,'+base64.b64encode(blob).decode('ascii') for blob in blobs]
        if self.provider == 'OpenAI':
            return {'model': self.model, 'store': False, 'max_output_tokens': self.max_output,
                    'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}]+
                               [{'type': 'input_image', 'image_url': data, 'detail': 'high'} for data in images]}],
                    'text': {'format': {'type': 'json_schema', 'name': 'score_result', 'strict': True, 'schema': schema}}}
        if self.provider == 'DeepSeek':
            return {'model': self.model, 'max_tokens': self.max_output,
                    'response_format': {'type': 'json_object'},
                    'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt+'\nReturn JSON matching this schema:\n'+json.dumps(schema)}]+
                                 [{'type': 'image_url', 'image_url': {'url': data}} for data in images]}]}
        return {'model': self.model, 'max_tokens': self.max_output,
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]+
                             [{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': data.split(',', 1)[1]}} for data in images]}],
                'tools': [{'name': 'score_result', 'description': 'Return the requested music data.', 'input_schema': schema}],
                'tool_choice': {'type': 'tool', 'name': 'score_result'}}

    def _api(self, prompt, schema, blobs):
        headers = {'Content-Type': 'application/json'}
        if self.provider == 'Anthropic':
            headers.update({'x-api-key': self.key, 'anthropic-version': '2023-06-01'})
        else:
            headers['Authorization'] = 'Bearer '+self.key
        request = urllib.request.Request(PROVIDERS[self.provider]['url'],
                                         data=json.dumps(self._payload(prompt, schema, blobs)).encode(), headers=headers)
        # No automatic retries: timeouts may already have been billed.
        result = {}
        def run():
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    result['body'] = json.load(response)
            except Exception as exc:
                result['error'] = exc
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        while thread.is_alive():
            if self.cancel.wait(.2):
                # HTTP work cannot be forcibly unbilled; retain usage if it completes.
                self.log('Cancelling: waiting for the in-flight provider request to finish (it may be billed).')
                thread.join(timeout=185)
                break
        if 'error' in result:
            error = result['error']
            if isinstance(error, urllib.error.HTTPError):
                raise RuntimeError(f'{self.provider} HTTP {error.code}. Check model access, API key, quota and provider status.') from None
            raise RuntimeError('Provider connection failed or timed out; it may have processed the request. No automatic retry was made.') from None
        if 'body' not in result:
            raise Cancelled('Cancelled; provider request status and billing are unknown.')
        body = result['body']
        if self.provider == 'OpenAI':
            u = body.get('usage', {})
            usage = {'input_tokens': u.get('input_tokens', 0), 'cached_input_tokens': u.get('input_tokens_details', {}).get('cached_tokens', 0), 'output_tokens': u.get('output_tokens', 0)}
            if body.get('status') != 'completed':
                self._record(usage)
                raise RuntimeError('OpenAI response was incomplete. Increase the output limit or reduce frames per request.')
            text = ''.join(c.get('text', '') for item in body.get('output', []) for c in item.get('content', []) if c.get('type') == 'output_text')
        elif self.provider == 'DeepSeek':
            u = body.get('usage', {})
            usage = {'input_tokens': u.get('prompt_tokens', 0), 'cached_input_tokens': u.get('prompt_cache_hit_tokens', 0), 'output_tokens': u.get('completion_tokens', 0)}
            if body['choices'][0].get('finish_reason') != 'stop':
                self._record(usage)
                raise RuntimeError('DeepSeek response was truncated. Increase the output limit or reduce frames per request.')
            text = body['choices'][0]['message']['content']
        else:
            u = body.get('usage', {})
            cached = u.get('cache_read_input_tokens', 0)
            usage = {'input_tokens': u.get('input_tokens', 0)+cached+u.get('cache_creation_input_tokens', 0), 'cached_input_tokens': cached, 'output_tokens': u.get('output_tokens', 0)}
            tool = next((c for c in body.get('content', []) if c.get('type') == 'tool_use' and c.get('name') == 'score_result'), None)
            if not tool or body.get('stop_reason') == 'max_tokens':
                self._record(usage)
                raise RuntimeError('Anthropic returned no complete score data. Reduce frames per request.')
            return tool['input'], usage
        try:
            return json.loads(text), usage
        except ValueError:
            self._record(usage)
            raise ValueError('The provider returned invalid JSON; the request may still be billed.') from None
