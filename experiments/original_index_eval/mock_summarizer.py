"""Deterministic OpenAI-compatible summarizer for isolated diagnostic stacks only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/v1/chat/completions':
            self.send_error(404)
            return
        size = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(size))
        if not any(m.get('role') == 'user' for m in body.get('messages', [])):
            self.send_error(400)
            return
        content = next(m['content'] for m in body['messages'] if m.get('role') == 'user')
        digest = hashlib.sha256(content.encode()).hexdigest()[:12]
        data = json.dumps({'id': 'synthetic-summary', 'object': 'chat.completion',
                           'choices': [{'index': 0, 'message': {'role': 'assistant',
                           'content': f'Synthetic record {digest} about routine planning.'},
                           'finish_reason': 'stop'}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
