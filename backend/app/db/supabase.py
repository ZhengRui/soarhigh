from supabase import create_client

from ..config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
