import json
from fastapi.routing import APIRoute
from app.permissions import redact

class SecureRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handle(request):
            response=await original(request)
            who=getattr(request.state,'identity',None)
            if who and response.headers.get('content-type','').startswith('application/json') and getattr(response,'body',b''):
                data=json.loads(response.body)
                if who.user.role!='DIRECTOR':data=redact(data,who.permissions,path=request.url.path)
                from app.services.dismantling_access import platform_admin,public_payload,vehicle_payload
                path=request.url.path
                if not platform_admin(who.user) and ('/dismantling-v3' in path or '/assemblies' in path or path.endswith('/global-dismantling')):data=public_payload(data)
                if not platform_admin(who.user) and path.startswith('/api/v1/vehicles'):data=vehicle_payload(data)
                response.body=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
                response.headers['content-length']=str(len(response.body))
            return response
        return handle
