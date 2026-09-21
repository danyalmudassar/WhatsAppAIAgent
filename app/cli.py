import argparse

from app.api import create_app
from app.config import Settings
from app.contracts import IncomingMessage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["chat"])
    args = parser.parse_args()
    if args.command == "chat":
        api = create_app(Settings())
        for index, line in enumerate(iter(input, ""), start=1):
            response = next(route for route in api.routes if getattr(route, "path", None) == "/messages").endpoint(
                IncomingMessage(message_id=f"cli-{index}", sender_id="self", text=line)
            )
            print(response.text)
