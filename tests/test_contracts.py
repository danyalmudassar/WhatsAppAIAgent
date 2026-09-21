from app.contracts import IncomingMessage, OutgoingMessage


def test_message_contract():
    message = IncomingMessage(message_id="m-1", sender_id="self", text="hello")
    assert message.text == "hello"
    assert OutgoingMessage(message_id="m-1", text="jawab").text == "jawab"
