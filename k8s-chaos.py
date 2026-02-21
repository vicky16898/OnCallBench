import sys
from dotenv import load_dotenv
from src.main import app

# Load environment variables from .env
load_dotenv()

if __name__ == "__main__":
    app()
