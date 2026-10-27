"""Bound JSON control requests before FastAPI/dependencies decode their body."""
from starlette.responses import JSONResponse

MAX_CONTROL_BODY = 4 * 1024 * 1024


class CatalogueJsonLimit:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        headers=dict(scope.get('headers',[]))
        bounded=(scope['type']=='http' and scope.get('method')=='POST'
                 and scope.get('path','').startswith('/api/v1/catalogue/')
                 and (headers.get(b'content-type',b'').startswith(b'application/json')
                      or scope.get('path','').endswith(('/preview','/apply'))))
        if not bounded:
            return await self.app(scope,receive,send)
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            chunk=message.get('body',b'')
            if len(body)+len(chunk)>MAX_CONTROL_BODY:
                return await JSONResponse({'detail':'Catalogue control request exceeds 4 MiB'},status_code=413)(scope,receive,send)
            body.extend(chunk)
            if not message.get('more_body',False):break
        delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)
