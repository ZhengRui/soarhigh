from supabase import Client, ClientOptions, create_client

from ..config import SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def create_user_client(user_token: str) -> Client:
    client = create_client(
        SUPABASE_URL, SUPABASE_ANON_KEY, options=ClientOptions(headers={"Authorization": f"Bearer {user_token}"})
    )
    return client
