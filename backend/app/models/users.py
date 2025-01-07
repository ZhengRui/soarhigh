from pydantic import BaseModel


class User(BaseModel):
    uid: str
    username: str
    full_name: str
