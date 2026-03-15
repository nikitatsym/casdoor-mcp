import httpx

from .config import get_settings


class APIError(Exception):
    def __init__(self, status: int, method: str, path: str, body):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"{method} {path} -> {status}: {body}")


class CasdoorClient:
    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        access_token: str | None = None,
        access_key: str | None = None,
        access_secret: str | None = None,
    ):
        s = get_settings()
        self._base = (base_url or s.casdoor_endpoint).rstrip("/")
        token = access_token or s.casdoor_access_token
        cid = client_id or s.casdoor_client_id
        csecret = client_secret or s.casdoor_client_secret
        akey = access_key or s.casdoor_access_key
        asecret = access_secret or s.casdoor_access_secret

        headers: dict[str, str] = {}
        auth_params: dict[str, str] = {}

        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif cid and csecret:
            auth_params = {"clientId": cid, "clientSecret": csecret}
        elif akey and asecret:
            auth_params = {"accessKey": akey, "accessSecret": asecret}

        self._http = httpx.Client(
            base_url=self._base,
            headers=headers,
            params=auth_params,
            timeout=30.0,
        )

    def _handle(self, r: httpx.Response):
        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = r.text
            raise APIError(r.status_code, r.request.method, str(r.url), body)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def get(self, path: str, **kwargs):
        return self._handle(self._http.get(path, **kwargs))

    def post(self, path: str, **kwargs):
        return self._handle(self._http.post(path, **kwargs))
