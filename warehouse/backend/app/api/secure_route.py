import json
from fastapi.routing import APIRoute
from app.permissions import redact

class SecureRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            response=await original(request)
            who=getattr(request.state,'identity',None)
            if who and who.user.role!='DIRECTOR' and response.headers.get('content-type','').startswith('application/json') and getattr(response,'body',b''):
                data=json.loads(response.body)
                response.body=json.dumps(redact(data,who.permissions,path=request.url.path),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
                response.headers['content-length']=str(len(response.body))
            return response
        return handle
