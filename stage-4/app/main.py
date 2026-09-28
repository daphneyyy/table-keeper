"""Explicit HTTP parsing avoids framework coercion and validation envelopes."""
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response, FileResponse
from starlette.staticfiles import StaticFiles

from .rules import Error, require
from . import json_values
from .service import Service

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
service = Service()
STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC, check_dir=False), name='static')


@app.get('/')
@app.get('/signup')
@app.get('/login')
@app.get('/lookup')
async def screen():
    return FileResponse(STATIC / 'index.html', media_type='text/html')


def json_response(value, status):
    return Response(json_values.dumps(value),
                    status_code=status, media_type='application/json; charset=utf-8')


@app.exception_handler(HTTPException)
async def framework_error(request, exc):
    code = 'method_not_allowed' if exc.status_code == 405 else 'not_found'
    return json_response({'error': {'code': code, 'message': str(exc.detail)}}, exc.status_code)


@app.api_route('/{path:path}', methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS', 'HEAD'])
async def endpoint(request: Request, path: str):
    try:
        raw = await request.body()
        body = {}
        if request.method in ('POST', 'PATCH', 'PUT'):
            optional = request.url.path.endswith('/cancel')
            try:
                if raw or not optional:
                    body = json_values.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                raise Error(400, 'malformed_request') from None
            require(type(body) is dict, 400, 'malformed_request')
        status, value = await run_in_threadpool(service.handle, request.method, request.url.path,
                                               body, request.headers, request.query_params)
        return Response(status_code=204) if status == 204 else json_response(value, status)
    except Error as exc:
        return json_response({'error': {'code': exc.code, 'message': exc.message}}, exc.status)
    except (UnicodeError, OverflowError, RecursionError):
        return json_response({'error': {'code': 'validation_failed', 'message': 'Invalid value'}}, 422)
    except Exception:
        logging.exception('Unhandled service failure')
        return json_response({'error': {'code': 'internal_error', 'message': 'Unexpected service failure'}}, 500)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), workers=1)
