import time
import httpx
import sys

BASE_URL = "http://127.0.0.1:8000"

def main():
    print("Waiting for server...")
    for i in range(30):
        try:
            with httpx.Client() as client:
                response = client.get(BASE_URL)
                if response.status_code == 200:
                    print(f"Server is up! (took {i+1} seconds)")
                    sys.exit(0)
        except httpx.ConnectError:
            pass
        print(f".", end='', flush=True)
        time.sleep(1)
    
    print("\nServer did not start in 30 seconds.")
    sys.exit(1)

if __name__ == "__main__":
    main()

