from pydantic import BaseModel
from typing import List, Optional

class DiagnosticRequest(BaseModel):
    namespace: str
    pod_name: Optional[str] = None

class CommandExecutionRequest(BaseModel):
    command: str

class PodStatus(BaseModel):
    name: str
    status: str
    restarts: int
    age: str
    is_healthy: bool
