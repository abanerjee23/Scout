"""Print setup presence only; never credentials and never a claim of connectivity."""
import os

SERVICES = {
    "Supabase (Phase 1)": ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "DATABASE_URL"],
    "OpenAI (Phase 2)": ["OPENAI_API_KEY", "OPENAI_MODEL"],
    "Galileo (Phase 2)": ["GALILEO_API_KEY", "GALILEO_PROJECT"],
    "FX fallback (Phase 2)": ["OPEN_EXCHANGE_RATES_APP_ID"],
}


def main():
    print("Inherited environment only. No secrets are printed. No connections are attempted.")
    for service, keys in SERVICES.items():
        present = [key for key in keys if os.environ.get(key)]
        missing = [key for key in keys if not os.environ.get(key)]
        print(f"{service}: {len(present)}/{len(keys)} configured; connectivity not verified")
        if missing:
            print("  Missing: " + ", ".join(missing))


if __name__ == "__main__":
    main()
