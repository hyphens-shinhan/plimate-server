from supabase import create_client, Client

from app.core.config import settings

supabase: Client = create_client(settings.SUPERBASE_URL, settings.SERVICE_KEY)
