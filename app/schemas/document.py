from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    title: str
    document_type: str
    file_name: str
    file_size: int
    mime_type: str
    uploaded_at: Optional[datetime] = None
