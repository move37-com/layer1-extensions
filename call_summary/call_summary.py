import layer1
import asyncio
import json
import uuid

# Create a MessageCenter instance
extension_id = str(uuid.uuid4())
loop = asyncio.get_event_loop()
message_center = layer1.MessageCenter(loop, extension_id)

# Business logic for generating call summaries
async def handleCallDidEnd(msg):
    print('Call ended: ', msg['callID'])
    script_msg = {
        "event": "layerScript.run",
        "data": {
            "scriptName": "Call Summary",
            "scriptInput": str(msg['callID'])
            # "scriptInput": "1693939913"
        }
    }
    print("Sending summary request")
    summary_msg = await message_center.send_message(script_msg)
    print("Got summary result")
    json_obj = json.loads(summary_msg['summary'])
    participants = ", ".join(json_obj['participants'])
    summary = json_obj['summary']
    html = """
    <html><body>
    <h1>Call Summary</h1>
    <h3>Participants</h3>
    {participants}
    <h3>Summary</h3>
    {summary}
    </body></html>
    """.format(participants=participants, summary=summary)
    view_msg = {
        "event": "view.renderHTML",
        "data": {
            "html": html
        }
    }
    print("Sending view render request")
    status = await message_center.send_message(view_msg)
    print("Render status: ", status)

# Handler for incoming events on the 'calls' channel
async def call_handler(channel, event, msg):
    match event:
        case 'callDidEnd':
            await handleCallDidEnd(msg)

# Register event handler and start the message center
message_center.subscribe('calls', call_handler)
message_center.run() # Will run forever