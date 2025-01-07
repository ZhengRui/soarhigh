from .supabase import supabase


def get_members():
    return supabase.table("members").select("id, username, full_name").execute().data
